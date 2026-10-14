from contextlib import asynccontextmanager
from statistics import median

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete, func, or_, select
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
from .seed import seed_demo
from .services.ai import parse_search_query
from .services.importer import run_authorized_import, upsert_listing
from .services.scoring import score_listing


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    from .db import SessionLocal
    with SessionLocal() as db:
        seed_demo(db)
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
    search_row = UserSearch(natural_language_query=payload.query, parsed_criteria=intent.model_dump(), parser_version=parser, last_run_at=utcnow())
    db.add(search_row)
    db.flush()
    query = listing_query().where(Listing.status == "active", Listing.city == settings.target_city)
    if payload.favorites_only:
        query = query.join(FavoriteListing)
    if payload.notes_only:
        query = query.join(UserNote).distinct()
    listings = db.scalars(query).all()
    ppm_values = [item.price_per_sqm_eur for item in listings if item.price_per_sqm_eur]
    median_ppm = median(ppm_values) if ppm_values else None
    results: list[SearchResult] = []
    for listing in listings:
        score, hard_passed, lines = score_listing(listing, intent, median_ppm)
        score_row = MatchScore(listing_id=listing.id, user_search_id=search_row.id, score=score, hard_criteria_passed=hard_passed)
        db.add(score_row)
        db.flush()
        explanations = []
        for line in lines:
            data = line.__dict__
            db.add(MatchScoreExplanation(match_score_id=score_row.id, **data))
            explanations.append(CriterionExplanation(**data))
        if score >= payload.min_score:
            results.append(SearchResult(listing=card(listing), score=score, hard_criteria_passed=hard_passed, explanations=explanations))
    db.commit()
    results.sort(key=lambda item: item.score, reverse=True)
    return SearchResponse(search_id=search_row.id, query=payload.query, parsed_criteria=intent.model_dump(), parser=parser, results=results)
