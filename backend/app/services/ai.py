import re

from openai import OpenAI
from pydantic import BaseModel, Field

from ..config import get_settings


KNOWN_LOCATIONS = [
    "Лозенец", "Иван Вазов", "Младост", "Изток", "Изгрев", "Дианабад",
    "Манастирски ливади", "Кръстова вада", "Хладилника", "Стрелбище",
    "Борово", "Гоце Делчев", "Овча купел", "Център", "Докторски паметник",
    "Колю Фичето", "Бузлуджа", "Акация", "Картала", "Варуша", "Зона Б",
    "Чолаковци", "Света гора", "Стара част",
]


class SearchIntent(BaseModel):
    max_price_eur: float | None = None
    min_area_sqm: float | None = None
    max_price_per_sqm_eur: float | None = None
    property_types: list[str] = Field(default_factory=list)
    room_counts: list[int] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    exclude_last_floor: bool = False
    exclude_ground_floor: bool = False
    exclude_needs_renovation: bool = False
    required_features: list[str] = Field(default_factory=list)
    preferred_features: list[str] = Field(default_factory=list)
    investment_focus: bool = False


def _number(text: str) -> float:
    return float(text.replace(" ", "").replace(",", "."))


def parse_with_rules(query: str) -> SearchIntent:
    lower = query.lower()
    intent = SearchIntent()
    price = re.search(r"(?:до|max(?:imum)?)[^\d]{0,15}([\d\s]+(?:[.,]\d+)?)\s*(?:евро|eur|€)", lower)
    area = re.search(r"(?:поне|над|минимум)[^\d]{0,15}([\d\s]+(?:[.,]\d+)?)\s*(?:кв|m²|м2)", lower)
    ppm = re.search(r"(?:до|max)[^\d]{0,12}([\d\s]+)\s*(?:евро|eur|€)?\s*(?:\/|на)\s*(?:кв|m²|м2)", lower)
    if price:
        intent.max_price_eur = _number(price.group(1))
    if area:
        intent.min_area_sqm = _number(area.group(1))
    if ppm:
        intent.max_price_per_sqm_eur = _number(ppm.group(1))
    room_words = {"едностаен": 1, "двустаен": 2, "тристаен": 3, "четиристаен": 4, "многостаен": 5}
    intent.room_counts = [count for word, count in room_words.items() if word in lower]
    if intent.room_counts:
        intent.property_types = ["апартамент"]
    for kind in ("къща", "офис", "парцел", "мезонет", "ателие"):
        if kind in lower:
            intent.property_types.append(kind)
    intent.locations = [place for place in KNOWN_LOCATIONS if place.lower() in lower]
    intent.exclude_last_floor = bool(re.search(r"не (?:(?:е|бъде) )?последен|без последен", lower))
    intent.exclude_ground_floor = bool(re.search(r"не (?:(?:е|бъде) )?партер|без партер", lower))
    intent.exclude_needs_renovation = bool(re.search(r"не.*(?:основен )?ремонт|без ремонт|готов за нанасяне", lower))
    feature_map = {"асансьор": "elevator", "паркомясто": "parking", "гараж": "parking", "метро": "near_metro", "южно": "south_exposure"}
    for word, feature in feature_map.items():
        if word in lower:
            intent.preferred_features.append(feature)
    intent.investment_focus = "инвестици" in lower or "подценен" in lower
    return intent


def parse_search_query(query: str) -> tuple[SearchIntent, str]:
    settings = get_settings()
    if not settings.openai_api_key:
        return parse_with_rules(query), "rules-v1"
    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.responses.parse(
            model=settings.openai_model,
            store=False,
            input=[
                {"role": "system", "content": f"Извлечи критерии за имот в {settings.target_city}. Не измисляй липсващи ограничения. property_types използва стойности апартамент, къща, офис, парцел, мезонет или ателие. Features: elevator, parking, near_metro, south_exposure."},
                {"role": "user", "content": query},
            ],
            text_format=SearchIntent,
        )
        if response.output_parsed:
            return response.output_parsed, f"openai:{settings.openai_model}"
    except Exception:
        pass
    return parse_with_rules(query), "rules-v1-fallback"
