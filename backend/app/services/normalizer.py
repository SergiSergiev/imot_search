import hashlib
import re
from typing import Any


EUR_RATE = 1.95583


def normalize_price(value: str | float | int | None, currency: str = "EUR") -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = re.sub(r"[^\d.,]", "", value).replace(" ", "")
        if not cleaned:
            return None
        if "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
        number = float(cleaned)
    else:
        number = float(value)
    return round(number / EUR_RATE, 2) if currency.upper() in {"BGN", "ЛВ"} else round(number, 2)


def content_hash(data: dict[str, Any]) -> str:
    parts = [str(data.get(key, "")) for key in ("title", "price_eur", "area_sqm", "description")]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def extract_features(text: str) -> dict[str, dict[str, Any]]:
    lower = text.lower()
    patterns = {
        "elevator": (r"\bасансьор", True),
        "parking": (r"паркомясто|гараж|паркинг", True),
        "south_exposure": (r"южно изложение|югозапад|югоизток", True),
        "near_metro": (r"метро|метростанц", True),
        "needs_renovation": (r"за ремонт|основен ремонт|нуждае се от ремонт", True),
        "furnished": (r"напълно обзаведен|обзаведен", True),
        "new_construction": (r"ново строителство|акт 16|новопостроен", True),
    }
    result: dict[str, dict[str, Any]] = {}
    for key, (pattern, value) in patterns.items():
        match = re.search(pattern, lower)
        if match:
            result[key] = {
                "value": value,
                "source": "description",
                "confidence": 0.9,
                "evidence": match.group(0),
            }
    if "без асансьор" in lower or "няма асансьор" in lower:
        result["elevator"] = {"value": False, "source": "description", "confidence": 0.95, "evidence": "без асансьор"}
    return result
