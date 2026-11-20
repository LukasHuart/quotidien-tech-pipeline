"""Score d'importance général d'un article (indépendant des goûts de l'utilisateur)."""
import math
import re
from datetime import datetime

# Pages de bons de réduction / promotions : peu d'intérêt pour une édition d'actualité.
_PROMO_TITLE = re.compile(
    r"\b(coupons?|promo(?:tion(?:al)?)? codes?|discount codes?|vouchers?|\d{1,2}% off"
    r"|(?:best|top|early|today'?s|weekend|black friday|cyber monday|prime day)\b.{0,40}\bdeals?)\b",
    re.IGNORECASE,
)
_PROMO_CATEGORIES = {"deals", "coupons", "coupon codes", "promo codes", "shopping deals"}


def is_promo(a: dict) -> bool:
    """Vrai pour les pages de codes promo / bons plans (jamais mises en avant dans une édition)."""
    if _PROMO_TITLE.search(a.get("title", "")):
        return True
    return any(str(c).strip().lower() in _PROMO_CATEGORIES for c in a.get("categories") or [])



def base_score(a: dict, now: datetime) -> float:
    age_h = max((now - a["published"]).total_seconds() / 3600, 0.0)
    recency = math.exp(-age_h / 18)                       # demi-vie ≈ 12 h
    buzz = min(a.get("mentions", 1), 4) / 4               # plusieurs sources = sujet important
    image = 0.08 if a.get("image") else 0.0
    return a.get("weight", 1.0) * (0.6 * recency + 0.4 * buzz) + image
