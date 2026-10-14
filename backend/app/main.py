from contextlib import asynccontextmanager
from statistics import median

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete, func, inspect, or_, select, text, update
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .db import Base, engine, get_db
from .models import (
    Agency, FavoriteListing, ImportJob, Listing, ListingChangeHistory, ListingFeature,
    ListingImage, ListingSnapshot, MatchScore, MatchScoreExplanation, UserNote,
    UserSearch, utcnow,
)
from .schemas import (
    AgencyCreate, AgencyOut, CriterionExplanation, ImportJobOut, ListingCardOut,
    ListingDetailOut, ManualImport, NoteCreate, NoteOut, SearchCreate, SearchResponse,
    SearchResult,
)
from .services.ai import parse_search_query
from .services.importer import run_authorized_import, upsert_listing
from .services.scoring import score_listing


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    # Lightweight local migration for databases created before construction_age.
    if "construction_age" not in {column["name"] for column in inspect(engine).get_columns("listings")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE listings ADD COLUMN construction_age VARCHAR(20)"))
    from .db import SessionLocal
    with SessionLocal() as db:
        db.execute(update(ImportJob).where(ImportJob.status.in_(["queued", "running"])).values(status="interrupted", error="Импортът е прекъснат при рестарт.", finished_at=utcnow()))
        db.execute(update(Agency).where(Agency.import_status == "running").values(import_status="idle"))
        db.commit()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list({
        settings.frontend_origin.rstrip("/"),
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    }),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def listing_query():
    return select(Listing).options(
        selectinload(Listing.images), selectinload(Listing.features),
        selectinload(Listing.notes), selectinload(Listing.changes), selectinload(Listing.favorite),
    )


def card(listing: Listing) -> ListingCardOut:
    primary = next((image.source_url for image in listing.images if image.is_primary), listing.images[0].source_url if listing.images else None)
    return ListingCardOut.model_validate(listing).model_copy(update={
        "description": (listing.description or "")[:600],
        "primary_image": primary,
        "is_favorite": listing.favorite is not None,
        "notes_count": len(listing.notes),
    })


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "ai": "openai" if settings.openai_api_key else "rules-fallback"}


@app.get("/api/agencies", response_model=list[AgencyOut])
def list_agencies(db: Session = Depends(get_db)):
    agencies = db.scalars(select(Agency).order_by(Agency.created_at.desc())).all()
    counts = dict(db.execute(select(Listing.agency_id, func.count(Listing.id)).where(Listing.city == settings.target_city).group_by(Listing.agency_id)).all())
    return [AgencyOut.model_validate(item).model_copy(update={"listing_count": counts.get(item.id, 0)}) for item in agencies]


@app.post("/api/agencies", response_model=AgencyOut, status_code=201)
def create_agency(payload: AgencyCreate, db: Session = Depends(get_db)):
    url = str(payload.source_url)
    if "imot.bg" not in (payload.source_url.host or ""):
        raise HTTPException(400, "URL адресът трябва да бъде от imot.bg")
    if db.scalar(select(Agency).where(Agency.source_url == url)):
        raise HTTPException(409, "Агенцията вече е добавена")
    agency = Agency(name=payload.name, source_url=url)
    db.add(agency)
    db.commit()
    db.refresh(agency)
    return AgencyOut.model_validate(agency)


@app.delete("/api/agencies/{agency_id}", status_code=204)
def delete_agency(agency_id: int, db: Session = Depends(get_db)):
    agency = db.get(Agency, agency_id)
    if not agency:
        raise HTTPException(404, "Агенцията не е намерена")
    listing_ids = list(db.scalars(select(Listing.id).where(Listing.agency_id == agency_id)).all())
    if listing_ids:
        score_ids = list(db.scalars(select(MatchScore.id).where(MatchScore.listing_id.in_(listing_ids))).all())
        if score_ids:
            db.execute(delete(MatchScoreExplanation).where(MatchScoreExplanation.match_score_id.in_(score_ids)))
        db.execute(delete(MatchScore).where(MatchScore.listing_id.in_(listing_ids)))
        for model in (ListingSnapshot, ListingChangeHistory, ListingFeature, ListingImage, UserNote, FavoriteListing):
            db.execute(delete(model).where(model.listing_id.in_(listing_ids)))
        db.execute(delete(Listing).where(Listing.id.in_(listing_ids)))
    db.execute(delete(ImportJob).where(ImportJob.agency_id == agency_id))
    db.delete(agency)
    db.commit()
    return Response(status_code=204)


@app.post("/api/agencies/{agency_id}/imports", response_model=ImportJobOut, status_code=202)
def start_import(agency_id: int, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    agency = db.get(Agency, agency_id)
    if not agency:
        raise HTTPException(404, "Агенцията не е намерена")
    if agency.import_status == "running":
        raise HTTPException(409, "Вече има активен импорт")
    job = ImportJob(agency_id=agency_id)
    db.add(job)
    db.commit()
    db.refresh(job)
    tasks.add_task(run_authorized_import, job.id)
    return job


@app.get("/api/imports/{job_id}", response_model=ImportJobOut)
def import_status(job_id: int, db: Session = Depends(get_db)):
    job = db.get(ImportJob, job_id)
    if not job:
        raise HTTPException(404, "Импортът не е намерен")
    return job


@app.post("/api/agencies/{agency_id}/manual-import", response_model=ImportJobOut)
def manual_import(agency_id: int, payload: ManualImport, db: Session = Depends(get_db)):
    agency = db.get(Agency, agency_id)
    if not agency:
        raise HTTPException(404, "Агенцията не е намерена")
    job = ImportJob(agency_id=agency_id, status="running", discovered=len(payload.listings), started_at=utcnow())
    db.add(job)
    db.flush()
    for item in payload.listings:
        _, created, changed = upsert_listing(db, agency, item)
        job.processed += 1
        job.created += int(created)
        job.updated += int(changed)
    job.status = "completed"
    job.finished_at = utcnow()
    agency.import_status = "completed"
    agency.last_imported_at = job.finished_at
    agency.last_successful_import_at = job.finished_at
    db.commit()
    return job


@app.get("/api/listings", response_model=list[ListingCardOut])
def list_listings(
    district: str | None = None,
    property_type: str | None = None,
    transaction_type: str | None = Query(default=None, pattern="^(sale|rent)$"),
    construction_age: str | None = Query(default=None, pattern="^(new|old)$"),
    min_price: float | None = None,
    max_price: float | None = None,
    favorites_only: bool = False,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = listing_query().where(Listing.status == "active", Listing.city == settings.target_city)
    if district:
        query = query.where(Listing.district.ilike(f"%{district}%"))
    if property_type:
        query = query.where(Listing.property_type.ilike(f"%{property_type}%"))
    if transaction_type:
        query = query.where(Listing.transaction_type == transaction_type)
    if construction_age:
        query = query.where(Listing.construction_age == construction_age)
    if min_price is not None:
        query = query.where(Listing.price_eur >= min_price)
    if max_price is not None:
        query = query.where(Listing.price_eur <= max_price)
    if favorites_only:
        query = query.join(FavoriteListing)
    return [card(item) for item in db.scalars(query.order_by(Listing.last_seen_at.desc()).limit(limit)).all()]


@app.get("/api/listings/{listing_id}", response_model=ListingDetailOut)
def get_listing(listing_id: int, db: Session = Depends(get_db)):
    listing = db.scalar(listing_query().where(Listing.id == listing_id))
    if not listing:
        raise HTTPException(404, "Обявата не е намерена")
    return ListingDetailOut.model_validate(listing).model_copy(update={"is_favorite": listing.favorite is not None})


@app.get("/api/listings/{listing_id}/similar", response_model=list[ListingCardOut])
def similar_listings(listing_id: int, db: Session = Depends(get_db)):
    target = db.get(Listing, listing_id)
    if not target:
        raise HTTPException(404, "Обявата не е намерена")
    candidates = db.scalars(listing_query().where(Listing.id != listing_id, Listing.agency_id == target.agency_id, or_(Listing.district == target.district, Listing.property_type == target.property_type)).limit(4)).all()
    return [card(item) for item in candidates]


@app.post("/api/listings/{listing_id}/notes", response_model=NoteOut, status_code=201)
def create_note(listing_id: int, payload: NoteCreate, db: Session = Depends(get_db)):
    if not db.get(Listing, listing_id):
        raise HTTPException(404, "Обявата не е намерена")
    note = UserNote(listing_id=listing_id, body=payload.body.strip())
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@app.delete("/api/notes/{note_id}", status_code=204)
def delete_note(note_id: int, db: Session = Depends(get_db)):
    note = db.get(UserNote, note_id)
    if not note:
        raise HTTPException(404, "Бележката не е намерена")
    db.delete(note)
    db.commit()
    return Response(status_code=204)


@app.put("/api/listings/{listing_id}/favorite", status_code=204)
def add_favorite(listing_id: int, db: Session = Depends(get_db)):
    if not db.get(Listing, listing_id):
        raise HTTPException(404, "Обявата не е намерена")
    if not db.scalar(select(FavoriteListing).where(FavoriteListing.listing_id == listing_id)):
        db.add(FavoriteListing(listing_id=listing_id))
        db.commit()
    return Response(status_code=204)


@app.delete("/api/listings/{listing_id}/favorite", status_code=204)
def remove_favorite(listing_id: int, db: Session = Depends(get_db)):
    db.execute(delete(FavoriteListing).where(FavoriteListing.listing_id == listing_id))
    db.commit()
    return Response(status_code=204)


@app.post("/api/searches", response_model=SearchResponse)
def search(payload: SearchCreate, db: Session = Depends(get_db)):
    intent, parser = parse_search_query(payload.query)
    if payload.transaction_type:
        intent.transaction_types = [payload.transaction_type]
    if payload.construction_age:
        intent.construction_ages = [payload.construction_age]
    search_row = UserSearch(natural_language_query=payload.query, parsed_criteria=intent.model_dump(), parser_version=parser, last_run_at=utcnow())
    db.add(search_row)
    db.flush()
    query = listing_query().where(Listing.status == "active", Listing.city == settings.target_city)
    if payload.listing_id:
        query = query.where(Listing.id == payload.listing_id)
    if intent.transaction_types:
        query = query.where(Listing.transaction_type.in_(intent.transaction_types))
    if intent.construction_ages:
        query = query.where(Listing.construction_age.in_(intent.construction_ages))
    if intent.excluded_locations:
        query = query.where(~or_(*(Listing.district.ilike(f"%{place}%") for place in intent.excluded_locations)))
    if intent.property_types:
        query = query.where(or_(*(Listing.property_type.ilike(f"%{kind}%") for kind in intent.property_types)))
    if intent.room_counts:
        query = query.where(Listing.room_count.in_(intent.room_counts))
    if payload.favorites_only:
        query = query.join(FavoriteListing)
    if payload.notes_only:
        query = query.join(UserNote).distinct()
    listings = db.scalars(query).all()
    if intent.excluded_locations:
        listings = [
            item for item in listings
            if not any(place.casefold() in (item.district or "").casefold() for place in intent.excluded_locations)
        ]
    if intent.missing_fields:
        def field_is_missing(item: Listing, field: str) -> bool:
            if field == "images":
                return not item.images
            value = getattr(item, field, None)
            return value is None or value == ""
        listings = [item for item in listings if all(field_is_missing(item, field) for field in intent.missing_fields)]
    if intent.missing_features:
        listings = [item for item in listings if all(not any(feature.key == key for feature in item.features) for key in intent.missing_features)]
    if intent.description_focus == "short_or_unclear":
        vague_phrases = ("топ локация", "уникален имот", "луксозен имот", "отлична оферта", "повече информация")
        listings = [
            item for item in listings
            if len((item.description or "").strip()) < 500
            or any(phrase in (item.description or "").casefold() for phrase in vague_phrases)
        ]
    ppm_values = [item.price_per_sqm_eur for item in listings if item.price_per_sqm_eur]
    median_ppm = median(ppm_values) if ppm_values else None
    comparable_groups: dict[tuple[str, str, str], list[float]] = {}
    broad_groups: dict[tuple[str, str], list[float]] = {}
    for item in listings:
        if not item.price_per_sqm_eur:
            continue
        district_key = (item.district or "").casefold()
        type_key = (item.property_type or "").casefold()
        comparable_groups.setdefault((district_key, item.transaction_type, type_key), []).append(item.price_per_sqm_eur)
        broad_groups.setdefault((item.transaction_type, type_key), []).append(item.price_per_sqm_eur)
    results: list[SearchResult] = []
    for listing in listings:
        group = comparable_groups.get(((listing.district or "").casefold(), listing.transaction_type, (listing.property_type or "").casefold()), [])
        fallback_group = broad_groups.get((listing.transaction_type, (listing.property_type or "").casefold()), [])
        comparable_median = median(group) if len(group) >= 3 else (median(fallback_group) if fallback_group else median_ppm)
        score, hard_passed, lines = score_listing(listing, intent, comparable_median)
        explanations = []
        for line in lines:
            data = line.__dict__
            explanations.append(CriterionExplanation(**data))
        if score >= payload.min_score:
            results.append(SearchResult(listing=card(listing), score=score, hard_criteria_passed=hard_passed, explanations=explanations))
    results.sort(key=lambda item: (
        not item.hard_criteria_passed,
        -item.score,
        item.listing.price_per_sqm_eur is None,
        item.listing.price_per_sqm_eur or float("inf"),
    ))
    total_count = len(results)
    results = results[:payload.limit]

    for result in results:
        score_row = MatchScore(listing_id=result.listing.id, user_search_id=search_row.id, score=result.score, hard_criteria_passed=result.hard_criteria_passed)
        db.add(score_row)
        db.flush()
        for explanation in result.explanations:
            db.add(MatchScoreExplanation(match_score_id=score_row.id, **explanation.model_dump()))
    db.commit()

    priced = [item.listing.price_eur for item in results if item.listing.price_eur is not None]
    if not results:
        answer = "Локалният анализ не намери обяви, които покриват въпроса. Опитай с по-широки условия."
    else:
        answer = f"Локален demo анализ: намерих {total_count} обяви и показвам най-добрите {len(results)} по match score"
        if priced:
            answer += f"; цените са от {min(priced):,.0f} до {max(priced):,.0f} EUR, медиана {median(priced):,.0f} EUR"
        answer += ". Подреждането и обясненията са изчислени локално — без изпращане на данни към външен AI."
    return SearchResponse(search_id=search_row.id, query=payload.query, parsed_criteria=intent.model_dump(), parser="local-demo-v2" if parser.startswith("rules") else parser, answer=answer, total_count=total_count, results=results)
