from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Agency(Base):
    __tablename__ = "agencies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str] = mapped_column(String(1000), unique=True)
    source_type: Mapped[str] = mapped_column(String(30), default="imot_bg")
    external_id: Mapped[str | None] = mapped_column(String(120))
    import_status: Mapped[str] = mapped_column(String(30), default="idle")
    last_imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_import_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    listings: Mapped[list[Listing]] = relationship(back_populates="agency", cascade="all, delete-orphan")


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (UniqueConstraint("agency_id", "source_listing_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    agency_id: Mapped[int] = mapped_column(ForeignKey("agencies.id"), index=True)
    source_listing_id: Mapped[str] = mapped_column(String(160))
    source_url: Mapped[str] = mapped_column(String(1200))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str | None] = mapped_column(Text)
    transaction_type: Mapped[str] = mapped_column(String(30), default="sale")
    property_type: Mapped[str | None] = mapped_column(String(80), index=True)
    room_count: Mapped[int | None] = mapped_column(Integer)
    price_eur: Mapped[float | None] = mapped_column(Float, index=True)
    original_price: Mapped[float | None] = mapped_column(Float)
    original_currency: Mapped[str] = mapped_column(String(5), default="EUR")
    area_sqm: Mapped[float | None] = mapped_column(Float, index=True)
    price_per_sqm_eur: Mapped[float | None] = mapped_column(Float)
    city: Mapped[str] = mapped_column(String(100), default="София")
    district: Mapped[str | None] = mapped_column(String(150), index=True)
    address_text: Mapped[str | None] = mapped_column(String(500))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    floor_number: Mapped[int | None] = mapped_column(Integer)
    floor_label: Mapped[str | None] = mapped_column(String(50))
    total_floors: Mapped[int | None] = mapped_column(Integer)
    condition: Mapped[str | None] = mapped_column(String(100))
    construction_type: Mapped[str | None] = mapped_column(String(100))
    construction_age: Mapped[str | None] = mapped_column(String(20), index=True)
    construction_year: Mapped[int | None] = mapped_column(Integer)
    contact_name: Mapped[str | None] = mapped_column(String(200))
    contact_phone: Mapped[str | None] = mapped_column(String(80))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    agency: Mapped[Agency] = relationship(back_populates="listings")
    images: Mapped[list[ListingImage]] = relationship(cascade="all, delete-orphan")
    features: Mapped[list[ListingFeature]] = relationship(cascade="all, delete-orphan")
    notes: Mapped[list[UserNote]] = relationship(cascade="all, delete-orphan")
    changes: Mapped[list[ListingChangeHistory]] = relationship(cascade="all, delete-orphan")
    favorite: Mapped[FavoriteListing | None] = relationship(cascade="all, delete-orphan")


class ListingImage(Base):
    __tablename__ = "listing_images"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    source_url: Mapped[str] = mapped_column(String(1500))
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    image_hash: Mapped[str | None] = mapped_column(String(64))


class ListingFeature(Base):
    __tablename__ = "listing_features"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    key: Mapped[str] = mapped_column(String(100), index=True)
    normalized_value: Mapped[Any] = mapped_column(JSON)
    raw_value: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(30), default="description")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    evidence_text: Mapped[str | None] = mapped_column(Text)


class UserSearch(Base):
    __tablename__ = "user_searches"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(200))
    natural_language_query: Mapped[str] = mapped_column(Text)
    parsed_criteria: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    parser_version: Mapped[str] = mapped_column(String(30), default="rules-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MatchScore(Base):
    __tablename__ = "match_scores"
    __table_args__ = (UniqueConstraint("listing_id", "user_search_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    user_search_id: Mapped[int] = mapped_column(ForeignKey("user_searches.id"), index=True)
    score: Mapped[float] = mapped_column(Float)
    hard_criteria_passed: Mapped[bool] = mapped_column(Boolean, default=True)
    scoring_version: Mapped[str] = mapped_column(String(30), default="v1")
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    explanations: Mapped[list[MatchScoreExplanation]] = relationship(cascade="all, delete-orphan")


class MatchScoreExplanation(Base):
    __tablename__ = "match_score_explanations"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_score_id: Mapped[int] = mapped_column(ForeignKey("match_scores.id"), index=True)
    criterion: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))
    weight: Mapped[float] = mapped_column(Float)
    points: Mapped[float] = mapped_column(Float)
    actual_value: Mapped[str | None] = mapped_column(Text)
    expected_value: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)


class UserNote(Base):
    __tablename__ = "user_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class FavoriteListing(Base):
    __tablename__ = "favorite_listings"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ListingChangeHistory(Base):
    __tablename__ = "listing_change_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(100))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ListingSnapshot(Base):
    __tablename__ = "listing_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ImportJob(Base):
    __tablename__ = "import_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    agency_id: Mapped[int] = mapped_column(ForeignKey("agencies.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    discovered: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
