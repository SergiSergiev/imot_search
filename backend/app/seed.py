from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Agency, Listing
from .schemas import ManualListing
from .services.importer import upsert_listing


DEMO_LISTINGS = [
    ManualListing(source_listing_id="demo-1", source_url="https://www.imot.bg/", title="Светъл тристаен апартамент в Лозенец", description="Напълно обзаведен апартамент с асансьор, южно изложение и функционално разпределение. На 7 минути от метро. Има възможност за паркомясто.", property_type="апартамент", room_count=3, price_eur=238000, area_sqm=96, district="Лозенец", floor_number=4, total_floors=7, condition="обзаведен", construction_type="тухла", construction_year=2012, images=["https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?auto=format&fit=crop&w=1200&q=80"]),
    ManualListing(source_listing_id="demo-2", source_url="https://www.imot.bg/", title="Тристаен до Южен парк, Иван Вазов", description="Просторен имот с отлична локация и гледка към зеленина. Сградата е без асансьор. Жилището има нужда от освежителен ремонт.", property_type="апартамент", room_count=3, price_eur=245000, area_sqm=102, district="Иван Вазов", floor_number=5, total_floors=5, condition="за освежаване", construction_type="тухла", construction_year=1980, images=["https://images.unsplash.com/photo-1600566753086-00f18fb6b3ea?auto=format&fit=crop&w=1200&q=80"]),
    ManualListing(source_listing_id="demo-3", source_url="https://www.imot.bg/", title="Нов двустаен апартамент в Кръстова вада", description="Ново строителство с Акт 16, асансьор и подземно паркомясто. Метростанция Витоша е на пешеходно разстояние. Необзаведен.", property_type="апартамент", room_count=2, price_eur=189000, area_sqm=72, district="Кръстова вада", floor_number=3, total_floors=6, condition="необзаведен", construction_type="тухла", construction_year=2024, images=["https://images.unsplash.com/photo-1600607687920-4e2a09cf159d?auto=format&fit=crop&w=1200&q=80"]),
    ManualListing(source_listing_id="demo-4", source_url="https://www.imot.bg/", title="Инвестиционен двустаен в Младост 1", description="Обзаведен апартамент близо до метро и бизнес парк. Стабилен потенциал за отдаване под наем, асансьор и ниски общи части.", property_type="апартамент", room_count=2, price_eur=164000, area_sqm=65, district="Младост 1", floor_number=6, total_floors=8, condition="обзаведен", construction_type="ЕПК", construction_year=1992, images=["https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?auto=format&fit=crop&w=1200&q=80"]),
]


def seed_demo(db: Session) -> None:
    if db.scalar(select(func.count(Listing.id))):
        return
    agency = Agency(name="Демо агенция", source_url="https://demo.imot.bg/", import_status="demo")
    db.add(agency)
    db.flush()
    for item in DEMO_LISTINGS:
        upsert_listing(db, agency, item)
    db.commit()
