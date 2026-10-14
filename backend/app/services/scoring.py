from dataclasses import dataclass
from typing import Any

from ..models import Listing
from ..config import get_settings
from .ai import SearchIntent


settings = get_settings()


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
    features = _features(listing)

    def add(key: str, status: str, weight: float, ratio: float, actual: Any, expected: Any, text: str) -> None:
        lines.append(ScoreLine(key, status, weight, round(weight * ratio, 1), str(actual) if actual is not None else None, str(expected) if expected is not None else None, text))

    if intent.transaction_types:
        match = listing.transaction_type in intent.transaction_types
        add("transaction_type", "met" if match else "unmet", 0, 0, listing.transaction_type, ", ".join(intent.transaction_types), "Видът на сделката съвпада." if match else "Обявата е за различен вид сделка.")
        hard_passed &= match

    if intent.construction_ages:
        known = listing.construction_age in {"new", "old"}
        match = known and listing.construction_age in intent.construction_ages
        add("construction_age", "met" if match else ("unmet" if known else "unknown"), 0, 0, listing.construction_age, ", ".join(intent.construction_ages), "Периодът на строителството съвпада." if match else "Периодът на строителството не съвпада или не е уточнен.")
        hard_passed &= match

    if intent.preferred_construction_age:
        preferred = listing.construction_age == intent.preferred_construction_age
        discount = intent.accept_alternative_below_median_pct or 0
        alternative_ok = (
            listing.construction_age in {"new", "old"}
            and listing.construction_age != intent.preferred_construction_age
            and listing.price_per_sqm_eur is not None
            and median_ppm is not None
            and listing.price_per_sqm_eur <= median_ppm * (1 - discount)
            and not features.get("needs_renovation")
        )
        match = preferred or alternative_ok
        expected = f"{intent.preferred_construction_age} или алтернатива поне {discount:.0%} под кварталната медиана"
        add("conditional_construction", "met" if match else ("unknown" if listing.construction_age is None else "unmet"), 0, 0, listing.construction_age, expected, "Предпочитанието за строителство или условието за ценова отстъпка е изпълнено." if match else "Алтернативното строителство не покрива условието за отстъпка.")
        hard_passed &= match

    # Location — 20
    if intent.locations:
        match = bool(listing.district and any(x.lower() in listing.district.lower() for x in intent.locations))
        add("location", "met" if match else "unmet", 20, 1 if match else 0, listing.district, ", ".join(intent.locations), "Локацията съвпада." if match else "Имотът е извън предпочитаните квартали.")
        hard_passed &= match
    else:
        add("location", "met", 20, 1, listing.district, settings.target_city, f"Имотът е в {settings.target_city}.")

    if intent.excluded_locations:
        excluded = bool(listing.district and any(place.lower() in listing.district.lower() for place in intent.excluded_locations))
        add("excluded_location", "unmet" if excluded else "met", 0, 0, listing.district, f"извън {', '.join(intent.excluded_locations)}", "Кварталът е изключен от условието за тиха локация." if excluded else "Кварталът не е сред изключените локации.")
        hard_passed &= not excluded

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

    negative_hits = [key for key in intent.negative_features if features.get(key)]
    if intent.negative_features:
        add("negative_features", "unmet" if negative_hits else "met", 8, -1 if negative_hits else 0, ", ".join(negative_hits) or None, "без голям булевард/шумни фактори", "Описанието подсказва близост до голям булевард, което намалява оценката за спокойна среда." if negative_hits else "Не е открит изричен сигнал за близост до голям булевард.")

    for key in intent.report_missing_features:
        if key == "noise_info":
            known = "quiet_environment" in features or "major_road" in features
            actual = "има информация" if known else None
            label = "шум или спокойна среда"
        else:
            known = key in features
            actual = features.get(key) if known else None
            label = {"elevator": "асансьор", "parking": "паркиране", "near_park": "парк", "near_school": "училище"}.get(key, key)
        add(f"missing_{key}", "met" if known else "unknown", 0, 0, actual, label, f"Има информация за {label}." if known else f"В обявата не е намерена надеждна информация за {label}; това трябва да се провери с брокера.")

    quality = min(1, len(listing.description or "") / 500)
    add("information_quality", "met" if quality >= 0.8 else "partial", 5, quality, f"{len(listing.description or '')} знака", "подробно описание", "По-пълното описание намалява неизвестните.")
    if intent.description_focus == "short_or_unclear":
        add("description_risk", "partial", 0, 0, f"{len(listing.description or '')} знака", "кратко или неясно описание", "Описанието е кратко или използва общи фрази. Провери обзавеждането, състоянието и реалното разпределение с брокера.")

    score = round(sum(line.points for line in lines), 1)
    if not hard_passed:
        score = min(score, 39.0)
    return score, hard_passed, lines
