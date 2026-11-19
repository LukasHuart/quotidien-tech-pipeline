"""Score d'importance général d'un article (indépendant des goûts de l'utilisateur)."""
import math
from datetime import datetime


def base_score(a: dict, now: datetime) -> float:
    age_h = max((now - a["published"]).total_seconds() / 3600, 0.0)
    recency = math.exp(-age_h / 18)                       # demi-vie ≈ 12 h
    buzz = min(a.get("mentions", 1), 4) / 4               # plusieurs sources = sujet important
    image = 0.08 if a.get("image") else 0.0
    return a.get("weight", 1.0) * (0.6 * recency + 0.4 * buzz) + image
