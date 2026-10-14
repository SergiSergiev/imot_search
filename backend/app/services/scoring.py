from dataclasses import dataclass
from typing import Any

from ..models import Listing
from .ai import SearchIntent


@dataclass
class ScoreLine:
    criterion: str
    status: str
    weight: float
    points: float
    actual_value: str | None
    expected_value: str | None
    explanation: str


def _features(listing: Listing) -> dict[str, Any]:
    return {feature.key: feature.normalized_value for feature in listing.features}


def score_listing(listing: Listing, intent: SearchIntent, median_ppm: float | None) -> tuple[float, bool, list[ScoreLine]]:
    lines: list[ScoreLine] = []
    hard_passed = True

    def add(key: str, status: str, weight: float, ratio: float, actual: Any, expected: Any, text: str) -> None:
        lines.append(ScoreLine(key, status, weight, round(weight * ratio, 1), str(actual) if actual is not None else None, str(expected) if expected is not None else None, text))

    # Location — 20
    if intent.locations:
        match = bool(listing.district and any(x.lower() in listing.district.lower() for x in intent.locations))
        add("location", "met" if match else "unmet", 20, 1 if match else 0, listing.district, ", ".join(intent.locations), "Локацията съвпада." if match else "Имотът е извън предпочитаните квартали.")
        hard_passed &= match
    else:
        add("location", "met", 20, 1, listing.district, "Велико Търново", "Имотът е във Велико Търново.")

    # Budget — 15
    if intent.max_price_eur:
        if listing.price_eur is None:
            add("price", "unknown", 15, 0.35, None, intent.max_price_eur, "Цената липсва и трябва да се провери.")
        else:
            match = listing.price_eur <= intent.max_price_eur
            ratio = 1 if match else max(0, 1 - (listing.price_eur / intent.max_price_eur - 1) * 3)
            add("price", "met" if match else "unmet", 15, ratio, listing.price_eur, intent.max_price_eur, "Цената е в бюджета." if match else "Цената надвишава бюджета.")
            hard_passed &= match
    else:
        add("price", "met", 15, 0.8, listing.price_eur, None, "Няма зададен максимален бюджет.")

    # Type and rooms — 15
    type_match = not intent.property_types or any(x.lower() in (listing.property_type or "").lower() for x in intent.property_types)
    room_match = not intent.room_counts or listing.room_count in intent.room_counts
    add("type_rooms", "met" if type_match and room_match else "unmet", 15, 1 if type_match and room_match else 0, f"{listing.property_type}, {listing.room_count} стаи", f"{intent.property_types}, {intent.room_counts}", "Типът и броят стаи съвпадат." if type_match and room_match else "Типът или броят стаи не съвпада.")
    hard_passed &= type_match and room_match

    # Area — 10
    if intent.min_area_sqm:
        match = listing.area_sqm is not None and listing.area_sqm >= intent.min_area_sqm
        ratio = 0.35 if listing.area_sqm is None else min(1, listing.area_sqm / intent.min_area_sqm)
        add("area", "met" if match else ("unknown" if listing.area_sqm is None else "unmet"), 10, ratio, listing.area_sqm, intent.min_area_sqm, "Площта покрива минимума." if match else "Площта не покрива минимума или липсва.")
        hard_passed &= match
    else:
        add("area", "met", 10, 0.8, listing.area_sqm, None, "Няма зададена минимална площ.")

    # Relative price/m² — 15
    if listing.price_per_sqm_eur and median_ppm:
        delta = (listing.price_per_sqm_eur - median_ppm) / median_ppm
        ratio = max(0, min(1, 0.75 - delta))
        status = "met" if delta <= 0 else ("partial" if delta <= 0.12 else "unmet")
        add("price_per_sqm", status, 15, ratio, round(listing.price_per_sqm_eur), round(median_ppm), "Цената на кв.м. е спрямо медианата на наличните сравними обяви.")
    else:
        add("price_per_sqm", "unknown", 15, 0.4, listing.price_per_sqm_eur, median_ppm, "Няма достатъчно данни за сравнение на цена на кв.м.")

    features = _features(listing)
    floor_bad = (intent.exclude_last_floor and listing.floor_number is not None and listing.total_floors is not None and listing.floor_number >= listing.total_floors) or (intent.exclude_ground_floor and (listing.floor_number == 0 or (listing.floor_label or "").lower() == "партер"))
    add("floor", "unmet" if floor_bad else ("unknown" if listing.floor_number is None else "met"), 8, 0 if floor_bad else (0.5 if listing.floor_number is None else 1), listing.floor_number, "не последен/партер", "Етажът нарушава изрично условие." if floor_bad else "Няма установен конфликт с етажа.")
    hard_passed &= not floor_bad

    renovation_bad = intent.exclude_needs_renovation and bool(features.get("needs_renovation"))
    condition_ratio = 0 if renovation_bad else (1 if listing.condition or features.get("furnished") or features.get("new_construction") else 0.5)
    add("condition", "unmet" if renovation_bad else ("met" if condition_ratio == 1 else "unknown"), 7, condition_ratio, listing.condition, "без основен ремонт", "Имотът е описан като нуждаещ се от ремонт." if renovation_bad else "Няма установен конфликт със състоянието.")
    hard_passed &= not renovation_bad

    preferred = set(intent.preferred_features + intent.required_features)
    hits = [key for key in preferred if features.get(key)]
    feature_ratio = len(hits) / len(preferred) if preferred else 0.7
    add("features", "met" if preferred and len(hits) == len(preferred) else ("partial" if hits else "unknown"), 5, feature_ratio, ", ".join(hits) or None, ", ".join(sorted(preferred)) or None, "Предпочитаните удобства са отчетени от описанието.")

    quality = min(1, len(listing.description or "") / 500)
    add("information_quality", "met" if quality >= 0.8 else "partial", 5, quality, f"{len(listing.description or '')} знака", "подробно описание", "По-пълното описание намалява неизвестните.")

    score = round(sum(line.points for line in lines), 1)
    if not hard_passed:
        score = min(score, 39.0)
    return score, hard_passed, lines
