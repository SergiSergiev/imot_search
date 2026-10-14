from __future__ import annotations

import asyncio
import re
import ssl
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal
from ..models import Agency, ImportJob, Listing, ListingChangeHistory, ListingFeature, ListingImage, ListingSnapshot
from ..schemas import ManualListing
from .normalizer import content_hash, extract_features, normalize_price


TRACKED_FIELDS = (
    "title", "description", "transaction_type", "price_eur", "area_sqm",
    "district", "floor_number", "condition", "construction_type",
    "construction_age", "construction_year",
)


def _validate_imot_url(url: str) -> None:
    host = (urlparse(url).hostname or "").lower()
    if host != "imot.bg" and not host.endswith(".imot.bg"):
        raise ValueError("Разрешени са само URL адреси от imot.bg")


def _tls_verify_for_imot_url(url: str) -> bool | ssl.SSLContext:
    """Keep CA verification, but support legacy imot subdomains containing `_`.

    RFC hostname matching rejects underscores even when the server presents the
    valid ``*.imot.bg`` certificate. The relaxed context is narrowly scoped to
    an already allow-listed direct child of imot.bg; CA-chain verification
    remains enabled.
    """
    host = (urlparse(url).hostname or "").lower()
    if "_" in host and host.endswith(".imot.bg") and host.count(".") == 2:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_REQUIRED
        return context
    return True


def _response_html(response: httpx.Response) -> str:
    """Decode legacy imot pages using their HTML meta charset."""
    head = response.content[:1000].lower()
    if b"windows-1251" in head or b"cp1251" in head:
        return response.content.decode("cp1251", errors="replace")
    return response.text


def upsert_listing(db: Session, agency: Agency, payload: ManualListing) -> tuple[Listing, bool, bool]:
    existing = db.scalar(select(Listing).where(Listing.agency_id == agency.id, Listing.source_listing_id == payload.source_listing_id))
    data = payload.model_dump(exclude={"images", "features"})
    data["price_per_sqm_eur"] = round(payload.price_eur / payload.area_sqm, 2) if payload.price_eur and payload.area_sqm else None
    data["content_hash"] = content_hash(data)
    now = datetime.now(timezone.utc)
    created = existing is None
    changed = False
    if existing is None:
        existing = Listing(agency_id=agency.id, **data)
        db.add(existing)
        db.flush()
    else:
        for field in TRACKED_FIELDS:
            old, new = getattr(existing, field), data.get(field)
            if old != new:
                db.add(ListingChangeHistory(listing_id=existing.id, field_name=field, old_value=str(old) if old is not None else None, new_value=str(new) if new is not None else None))
                changed = True
        for key, value in data.items():
            setattr(existing, key, value)
        existing.last_seen_at = now
        existing.status = "active"

    existing.images.clear()
    for index, url in enumerate(payload.images):
        existing.images.append(ListingImage(source_url=url, position=index, is_primary=index == 0))
    existing.features.clear()
    combined = extract_features(payload.description)
    combined.update({key: {"value": value, "source": "manual", "confidence": 1.0, "evidence": None} for key, value in payload.features.items()})
    for key, item in combined.items():
        existing.features.append(ListingFeature(key=key, normalized_value=item["value"], source=item["source"], confidence=item["confidence"], evidence_text=item.get("evidence")))
    db.add(ListingSnapshot(listing_id=existing.id, raw_data=payload.model_dump()))
    return existing, created, changed


def _extract_number(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return float(match.group(1).replace(" ", "").replace(",", ".")) if match else None


def _classify_transaction(url: str, title: str, page_text: str) -> str:
    """Use the strongest page signals and avoid rental words in free-form copy."""
    decisive = f"{url} {title}".lower()
    if re.search(r"под[\s_-]*наем|dava[\s_-]*pod[\s_-]*naem|(?:^|[\W_])naem(?:[\W_]|$)", decisive):
        return "rent"
    if re.search(r"продава|продажба|prodava|sale", decisive):
        return "sale"
    heading_text = page_text[:1500].lower()
    return "rent" if re.search(r"дава\s+под\s+наем|оферта\s+под\s+наем", heading_text) else "sale"


def _classify_construction(text: str, year: int | None) -> str | None:
    lower = text.lower()
    if re.search(r"старо\s+строителство|стара\s+(?:тухла|сграда)|гредоред", lower):
        return "old"
    if re.search(r"ново\s+строителство|новопостроен|нова\s+сграда|в\s+строеж|стартирало\s+строителство|ще\s+бъде\s+въведен\s+в\s+експлоатация|акт\s*(?:14|15|16)", lower):
        return "new"
    if year:
        return "new" if year >= 2000 else "old"
    return None


def classify_property_type(url: str, title: str) -> str:
    """Classify from the listing heading/slug; never default unknown assets to apartment."""
    text = f"{title} {url}".lower()
    title_lower = title.lower()
    specific_types = (
        (r"паркомясто", "паркомясто"),
        (r"гараж", "гараж"),
        (r"магазин", "магазин"),
        (r"склад", "склад"),
        (r"пром\.?\s*помещение|промишлено помещение", "промишлено помещение"),
        (r"фризьорски|козметичен салон|салон", "салон"),
        (r"заведение|ресторант|кафе", "заведение"),
        (r"самостоятелна сграда", "сграда"),
        (r"етаж от къща", "етаж от къща"),
        (r"мезонет", "мезонет"),
        (r"ателие|таван", "ателие"),
        (r"къща|вила", "къща"),
        (r"офис", "офис"),
        (r"парцел", "парцел"),
    )
    for pattern, value in specific_types:
        if re.search(pattern, title_lower):
            return value
    if re.search(r"(?:^|\D)\d+-стаен|едностаен|двустаен|тристаен|четиристаен|многостаен|апартамент", text):
        return "апартамент"
    return "друго"


def parse_listing_page(url: str, html: str) -> ManualListing:
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.select_one(".advHeader .title") or soup.select_one(".galleryInfo .title") or soup.select_one("h1") or soup.select_one("title"))
    title_text = title.get_text(" ", strip=True) if title else "Обява от imot.bg"
    description_node = soup.select_one(".moreInfo .text, [class*='description'], #description, .more-descr")
    description = description_node.get_text(" ", strip=True) if description_node else " ".join(p.get_text(" ", strip=True) for p in soup.select("p"))
    page_text = soup.get_text(" ", strip=True)
    price_text = soup.select_one(".adPrice .cena")
    price_match = re.search(r"([\d\s]+)\s*(EUR|€|лв\.?|BGN)", price_text.get_text(" ", strip=True) if price_text else page_text, re.IGNORECASE)
    price = normalize_price(price_match.group(1), "BGN" if price_match and re.search(r"лв|BGN", price_match.group(2), re.I) else "EUR") if price_match else None
    params_text = (soup.select_one(".adParams") or soup).get_text(" ", strip=True)
    area = _extract_number(r"([\d\s]+(?:[.,]\d+)?)\s*(?:кв\.?\s*м|m²|m\s*2|м\s*2)", params_text)
    floor = re.search(r"Етаж:\s*(\d+)\s*[- ]?(?:ви|ри|ти|ми)?\s*(?:ет\.?)?\s*(?:от\s*(\d+))?", params_text, re.I)
    source_id_match = re.search(r"obiava-([a-z0-9]+)", url, re.I) or re.search(r"(?:adv|id)[=/_-]?([a-z0-9]{5,})", url, re.I)
    source_id = source_id_match.group(1) if source_id_match else url.rstrip("/")
    images = []
    for image in soup.select("meta[property='og:image'], img"):
        src = image.get("content") or image.get("data-src") or image.get("src")
        if src and not src.startswith("data:"):
            absolute = urljoin(url, src)
            if absolute not in images:
                images.append(absolute)
    property_type = classify_property_type(url, title_text)
    room_map = {"едностаен": 1, "двустаен": 2, "тристаен": 3, "четиристаен": 4}
    rooms = next((count for word, count in room_map.items() if word in title_text.lower()), None)
    numeric_rooms = re.search(r"(\d+)-СТАЕН", title_text, re.I)
    if rooms is None and numeric_rooms:
        rooms = int(numeric_rooms.group(1))
    location_node = soup.select_one(".advHeader .location")
    location_text = location_node.get_text(" ", strip=True) if location_node else page_text
    district = None
    loc = re.search(r"(?:град|гр\.)\s+[^,]+,\s*([^,|]+)", location_text, re.I)
    if loc:
        district = loc.group(1).strip()[:150]
    city_match = re.search(r"(?:град|гр\.)\s+([А-ЯA-Z][А-Яа-яA-Za-z -]+?)(?:\s*,|\s+-|$)", location_text)
    year_match = re.search(r"(?:година(?:\s+на\s+строителство)?|построен[ао]?)\s*[:\-]?\s*((?:18|19|20)\d{2})", params_text, re.I)
    if not year_match:
        year_match = re.search(r"((?:18|19|20)\d{2})\s*г\.?", params_text, re.I)
    construction_year = int(year_match.group(1)) if year_match else None
    construction_type = next((label for pattern, label in (
        (r"\bтухла\b", "тухла"), (r"\bпанел\b", "панел"),
        (r"\bепк\b", "ЕПК"), (r"\bпк\b", "ПК"), (r"\bгредоред\b", "гредоред"),
    ) if re.search(pattern, params_text, re.I)), None)
    construction_age = _classify_construction(f"{params_text} {description}", construction_year)
    full_property_text = f"{params_text} {description}"
    condition = next((label for pattern, label in (
        (r"за\s+основен\s+ремонт|нуждае\s+се\s+от\s+ремонт", "за ремонт"),
        (r"до\s+ключ|готов\s+за\s+нанасяне", "готов за нанасяне"),
        (r"напълно\s+обзаведен", "напълно обзаведен"),
        (r"необзаведен", "необзаведен"),
        (r"обзаведен", "обзаведен"),
    ) if re.search(pattern, full_property_text, re.I)), None)
    phone_match = re.search(r"(?:\+359|0)[\d\s()-]{7,16}\d", page_text)
    contact_node = soup.select_one(".contactInfo .name, .brokerName, [class*='contact-name']")
    scraped_features = {key: item["value"] for key, item in extract_features(full_property_text).items()}
    return ManualListing(
        source_listing_id=source_id,
        source_url=url,
        title=title_text[:500],
        description=description[:15000],
        transaction_type=_classify_transaction(url, title_text, page_text),
        property_type=property_type,
        room_count=rooms,
        price_eur=price,
        area_sqm=area,
        city=city_match.group(1).strip()[:100] if city_match else "София",
        district=district,
        floor_number=int(floor.group(1)) if floor else None,
        total_floors=int(floor.group(2)) if floor and floor.group(2) else None,
        condition=condition,
        construction_type=construction_type,
        construction_age=construction_age,
        construction_year=construction_year,
        contact_name=contact_node.get_text(" ", strip=True)[:200] if contact_node else None,
        contact_phone=re.sub(r"\s+", " ", phone_match.group(0)).strip() if phone_match else None,
        images=images[:30],
        features=scraped_features,
    )


def _listing_links(page_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for anchor in soup.select("a[href]"):
        href = urljoin(page_url, anchor["href"])
        if urlparse(href).hostname and (urlparse(href).hostname == "imot.bg" or urlparse(href).hostname.endswith(".imot.bg")):
            if re.search(r"(?:view|adv|obiava|act=5|act=8)", href, re.I) and href not in links:
                links.append(href)
    return links


def _pagination_links(page_url: str, html: str) -> list[str]:
    """Return only agency-list pagination URLs, never listing or global-search URLs."""
    soup = BeautifulSoup(html, "html.parser")
    current_host = (urlparse(page_url).hostname or "").lower()
    links: list[str] = []
    for anchor in soup.select("a[href]"):
        href = urljoin(page_url, anchor["href"])
        parsed = urlparse(href)
        if (parsed.hostname or "").lower() != current_host:
            continue
        clean = href.split("#", 1)[0].split("?", 1)[0].rstrip("/")
        if re.search(r"/obiavi/p-\d+$", clean, re.I) and clean not in links:
            links.append(clean)
    return links


async def _discover_all_listing_links(client: httpx.AsyncClient, start_url: str, job: ImportJob, db: Session) -> list[str]:
    """Walk pagination breadth-first and return stable, de-duplicated listing URLs."""
    settings = get_settings()
    queue = [start_url]
    visited_pages: set[str] = set()
    listing_urls: list[str] = []
    seen_listings: set[str] = set()

    while queue and len(visited_pages) < settings.import_max_pages and len(listing_urls) < settings.import_max_listings:
        page_url = queue.pop(0)
        canonical_page = page_url.rstrip("/")
        if canonical_page in visited_pages:
            continue
        if visited_pages:
            await asyncio.sleep(settings.import_delay_seconds)
        response = await client.get(page_url)
        if response.status_code in {403, 429}:
            raise RuntimeError(f"Импортът е спрян безопасно след HTTP {response.status_code}")
        response.raise_for_status()
        visited_pages.add(canonical_page)

        html = _response_html(response)
        for link in _listing_links(str(response.url), html):
            canonical_listing = link.split("#", 1)[0]
            if settings.target_city_url_token and settings.target_city_url_token not in canonical_listing.lower():
                continue
            if canonical_listing not in seen_listings:
                seen_listings.add(canonical_listing)
                listing_urls.append(canonical_listing)
                if len(listing_urls) >= settings.import_max_listings:
                    break

        for next_page in _pagination_links(str(response.url), html):
            if next_page not in visited_pages and next_page not in queue:
                queue.append(next_page)

        job.discovered = len(listing_urls)
        db.commit()

    return listing_urls


async def run_authorized_import(job_id: int) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        job = db.get(ImportJob, job_id)
        agency = db.get(Agency, job.agency_id) if job else None
        if not job or not agency:
            return
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        agency.import_status = "running"
        db.commit()
        try:
            _validate_imot_url(agency.source_url)
            headers = {"User-Agent": "ImotInsightPersonalResearch/0.1 (authorized agency import; contact site owner)"}
            verify = _tls_verify_for_imot_url(agency.source_url)
            async with httpx.AsyncClient(headers=headers, timeout=30, follow_redirects=True, verify=verify) as client:
                links = await _discover_all_listing_links(client, agency.source_url, job, db)
                job.discovered = len(links)
                db.commit()
                for link in links:
                    try:
                        await asyncio.sleep(settings.import_delay_seconds)
                        detail = await client.get(link)
                        if detail.status_code in {403, 429}:
                            raise RuntimeError(f"Импортът е спрян безопасно след HTTP {detail.status_code}")
                        detail.raise_for_status()
                        payload = parse_listing_page(str(detail.url), _response_html(detail))
                        _, created, changed = upsert_listing(db, agency, payload)
                        job.created += int(created)
                        job.updated += int(changed)
                    except RuntimeError:
                        raise
                    except Exception:
                        job.failed += 1
                    job.processed += 1
                    db.commit()
            job.status = "completed"
            agency.import_status = "completed"
            agency.last_successful_import_at = datetime.now(timezone.utc)
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)[:2000]
            agency.import_status = "failed"
        finally:
            job.finished_at = datetime.now(timezone.utc)
            agency.last_imported_at = job.finished_at
            db.commit()
