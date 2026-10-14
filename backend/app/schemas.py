from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class AgencyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    source_url: HttpUrl


class AgencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    source_url: str
    import_status: str
    last_successful_import_at: datetime | None
    created_at: datetime
    listing_count: int = 0


class ImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_url: str
    position: int
    is_primary: bool


class FeatureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    normalized_value: Any
    source: str
    confidence: float
    evidence_text: str | None


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    body: str
    created_at: datetime
    updated_at: datetime


class ChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    field_name: str
    old_value: str | None
    new_value: str | None
    detected_at: datetime


class ListingBaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    agency_id: int
    source_url: str
    status: str
    title: str
    description: str
    summary: str | None
    property_type: str | None
    room_count: int | None
    price_eur: float | None
    area_sqm: float | None
    price_per_sqm_eur: float | None
    city: str
    district: str | None
    floor_number: int | None
    floor_label: str | None
    total_floors: int | None
    condition: str | None
    construction_type: str | None
    construction_year: int | None
    first_seen_at: datetime
    last_seen_at: datetime


class ListingCardOut(ListingBaseOut):
    primary_image: str | None = None
    is_favorite: bool = False
    notes_count: int = 0


class ListingDetailOut(ListingBaseOut):
    address_text: str | None
    contact_name: str | None
    contact_phone: str | None
    images: list[ImageOut]
    features: list[FeatureOut]
    notes: list[NoteOut]
    changes: list[ChangeOut]
    is_favorite: bool = False


class NoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=3000)


class ManualListing(BaseModel):
    source_listing_id: str
    source_url: str
    title: str
    description: str = ""
    property_type: str | None = None
    room_count: int | None = None
    price_eur: float | None = None
    area_sqm: float | None = None
    city: str = "София"
    district: str | None = None
    floor_number: int | None = None
    total_floors: int | None = None
    condition: str | None = None
    construction_type: str | None = None
    construction_year: int | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    images: list[str] = []
    features: dict[str, Any] = {}


class ManualImport(BaseModel):
    listings: list[ManualListing] = Field(min_length=1, max_length=1000)


class SearchCreate(BaseModel):
    query: str = Field(min_length=3, max_length=3000)
    favorites_only: bool = False
    notes_only: bool = False
    min_score: float = Field(default=0, ge=0, le=100)


class CriterionExplanation(BaseModel):
    criterion: str
    status: str
    weight: float
    points: float
    actual_value: str | None
    expected_value: str | None
    explanation: str


class SearchResult(BaseModel):
    listing: ListingCardOut
    score: float
    hard_criteria_passed: bool
    explanations: list[CriterionExplanation]


class SearchResponse(BaseModel):
    search_id: int
    query: str
    parsed_criteria: dict[str, Any]
    parser: str
    results: list[SearchResult]


class ImportJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    agency_id: int
    status: str
    discovered: int
    processed: int
    created: int
    updated: int
    failed: int
    error: str | None
