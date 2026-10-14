import re

from openai import OpenAI
from pydantic import BaseModel, Field

from ..config import get_settings


KNOWN_LOCATIONS = [
    "Лозенец", "Иван Вазов", "Младост", "Изток", "Изгрев", "Дианабад",
    "Манастирски ливади", "Кръстова вада", "Хладилника", "Стрелбище",
    "Борово", "Гоце Делчев", "Овча купел", "Център", "Докторски паметник",
    "Витоша", "Драгалевци", "Симеоново", "Бояна", "Обеля", "Надежда",
    "Люлин", "Красно село", "Белите брези", "Хиподрума", "Яворов", "Оборище",
    "Левски", "Слатина", "Редута", "Гео Милев", "Дружба", "Студентски град",
]


class SearchIntent(BaseModel):
    max_price_eur: float | None = None
    min_area_sqm: float | None = None
    max_price_per_sqm_eur: float | None = None
    transaction_types: list[str] = Field(default_factory=list)
    construction_ages: list[str] = Field(default_factory=list)
    preferred_construction_age: str | None = None
    accept_alternative_below_median_pct: float | None = None
    property_types: list[str] = Field(default_factory=list)
    room_counts: list[int] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    excluded_locations: list[str] = Field(default_factory=list)
    exclude_last_floor: bool = False
    exclude_ground_floor: bool = False
    exclude_needs_renovation: bool = False
    required_features: list[str] = Field(default_factory=list)
    preferred_features: list[str] = Field(default_factory=list)
    negative_features: list[str] = Field(default_factory=list)
    report_missing_features: list[str] = Field(default_factory=list)
    quiet_area: bool = False
    description_focus: str | None = None
    investment_focus: bool = False
    sort_by: str = "match"
    missing_fields: list[str] = Field(default_factory=list)
    missing_features: list[str] = Field(default_factory=list)


def _number(text: str) -> float:
    return float(text.replace(" ", "").replace(",", "."))


def parse_with_rules(query: str) -> SearchIntent:
    lower = query.lower()
    intent = SearchIntent()
    if re.search(r"под\s+наем|наема|наемане", lower):
        intent.transaction_types = ["rent"]
    elif re.search(r"купя|покупка|продажба|продава", lower):
        intent.transaction_types = ["sale"]
    if re.search(r"ново\s+строителство|нова\s+сграда|новопостроен", lower):
        intent.construction_ages = ["new"]
    elif re.search(r"старо\s+строителство|стара\s+сграда|стара\s+тухла", lower):
        intent.construction_ages = ["old"]
    price = re.search(r"(?:до|max(?:imum)?)[^\d]{0,15}([\d\s]+(?:[.,]\d+)?)\s*(?:евро|eur|€)", lower)
    area = re.search(r"(?:поне|над|минимум)[^\d]{0,15}([\d\s]+(?:[.,]\d+)?)\s*(?:кв|m²|м2)", lower)
    ppm = re.search(r"(?:до|max)[^\d]{0,12}([\d\s]+)\s*(?:евро|eur|€)?\s*(?:\/|на)\s*(?:кв|m²|м2)", lower)
    if price:
        intent.max_price_eur = _number(price.group(1))
    if not intent.transaction_types and ("семеен" in lower or (intent.max_price_eur or 0) >= 20_000):
        intent.transaction_types = ["sale"]
    if area:
        intent.min_area_sqm = _number(area.group(1))
    if ppm:
        intent.max_price_per_sqm_eur = _number(ppm.group(1))
    room_patterns = {
        r"\bедноста\w*": 1,
        r"\bдвуста\w*": 2,
        r"\bтриста\w*": 3,
        r"\bчетириста\w*": 4,
        r"\bмногоста\w*": 5,
    }
    intent.room_counts = [count for pattern, count in room_patterns.items() if re.search(pattern, lower)]
    if intent.room_counts:
        intent.property_types = ["апартамент"]
    elif "апартамент" in lower:
        intent.property_types = ["апартамент"]
    for kind in ("къща", "офис", "парцел", "мезонет", "ателие"):
        if kind in lower:
            intent.property_types.append(kind)
    intent.locations = [place for place in KNOWN_LOCATIONS if place.lower() in lower]
    intent.exclude_last_floor = bool(re.search(r"не (?:(?:е|бъде) )?последен|без последен|изключи[^.]{0,80}последен", lower))
    intent.exclude_ground_floor = bool(re.search(r"не (?:(?:е|бъде) )?партер|без партер|изключи[^.]{0,80}партер", lower))
    intent.exclude_needs_renovation = bool(re.search(r"не.*(?:основен )?ремонт|без ремонт|готов за нанасяне", lower))
    feature_map = {
        "асансьор": "elevator", "паркомясто": "parking", "паркиране": "parking",
        "гараж": "parking", "метро": "near_metro", "южно": "south_exposure",
        "парк": "near_park", "училище": "near_school", "шум": "noise_info",
    }
    for word, feature in feature_map.items():
        if re.search(rf"\b{re.escape(word)}\b", lower):
            intent.preferred_features.append(feature)
    intent.investment_focus = "инвестици" in lower or "подценен" in lower
    if re.search(r"кратк[оаи]|неясн[оаи]|оскъдно описание", lower):
        intent.description_focus = "short_or_unclear"
    if intent.investment_focus and not intent.transaction_types:
        intent.transaction_types = ["sale"]
    intent.quiet_area = bool(re.search(r"тих\s+(?:район|квартал)|спокоен\s+(?:район|квартал)", lower))
    if intent.quiet_area:
        if not any(place.lower() == "център" for place in intent.locations):
            intent.excluded_locations.append("Център")
        intent.negative_features.append("major_road")
    conditional_construction = re.search(
        r"предпочитам\s+ново[^.]{0,160}(?:приемам|допускам)\s+старо",
        lower,
    )
    if conditional_construction:
        discount = re.search(r"(\d+(?:[.,]\d+)?)\s*%\s*под\s+(?:кварталната\s+)?медиан", lower)
        intent.construction_ages = []
        intent.preferred_construction_age = "new"
        intent.accept_alternative_below_median_pct = _number(discount.group(1)) / 100 if discount else 0.15
    richer_features = {
        "тераса": "terrace", "балкон": "terrace", "двор": "yard",
        "мазе": "basement", "склад": "storage", "климатик": "air_conditioning",
        "камина": "fireplace", "басейн": "pool", "панорам": "panoramic_view",
    }
    for word, feature in richer_features.items():
        if word in lower and feature not in intent.preferred_features:
            intent.preferred_features.append(feature)

    if re.search(r"най-евтин|евтини|ниска цена(?! на квадрат)", lower):
        intent.sort_by = "price_asc"
    elif re.search(r"най-скъп|скъпи", lower):
        intent.sort_by = "price_desc"
    elif re.search(r"най-голям|най-простор|голяма квадратура", lower):
        intent.sort_by = "area_desc"
    elif re.search(r"най-много снимки|много снимки", lower):
        intent.sort_by = "images_desc"
    elif re.search(r"най-нов|скоро добавен", lower):
        intent.sort_by = "newest"
    elif re.search(r"цена на квадрат|изгодн|подценен|за парите", lower):
        intent.sort_by = "price_per_sqm_asc"
        intent.investment_focus = True

    field_words = {
        "цена": "price_eur", "квадратура": "area_sqm", "площ": "area_sqm",
        "етаж": "floor_number", "година": "construction_year", "снимки": "images",
        "описание": "description",
    }
    if re.search(r"липсва|не (?:е )?(?:посочен|уточнен)|не казва", lower):
        missing_start = re.search(r"липсва|не (?:е )?(?:посочен|уточнен)|не казва", lower)
        missing_clause = lower[missing_start.start():] if missing_start else lower
        mentioned_fields = list(dict.fromkeys(value for word, value in field_words.items() if word in missing_clause))
        mentioned_features = list(dict.fromkeys(
            [value for word, value in feature_map.items() if re.search(rf"\b{re.escape(word)}\b", missing_clause)]
            + [value for word, value in richer_features.items() if word in missing_clause]
        ))
        if re.search(r"отбележи|посочи|обясни", lower):
            intent.report_missing_features = mentioned_features
            intent.preferred_features = [key for key in intent.preferred_features if key not in mentioned_features]
        else:
            intent.missing_fields = mentioned_fields
            intent.missing_features = mentioned_features
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
                {"role": "system", "content": f"Извлечи критерии за имот в {settings.target_city}. Не измисляй липсващи ограничения. property_types: апартамент, къща, офис, парцел, мезонет или ателие. transaction_types: sale или rent. construction_ages: new или old. Features: elevator, parking, near_metro, south_exposure."},
                {"role": "user", "content": query},
            ],
            text_format=SearchIntent,
        )
        if response.output_parsed:
            return response.output_parsed, f"openai:{settings.openai_model}"
    except Exception:
        pass
    return parse_with_rules(query), "rules-v1-fallback"
