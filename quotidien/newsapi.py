"""Source optionnelle : API d'actualités (format NewsAPI.org).

Désactivée tant que la variable d'environnement NEWSAPI_KEY n'est pas définie.
Vérifiez les conditions du forfait choisi (usage non commercial, délai, quotas).
"""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime

from . import config, feeds

URL = "https://newsapi.org/v2/top-headlines?category=technology&language=en&pageSize=50"


def parse_response(payload: dict, now: datetime) -> list[dict]:
    out = []
    for item in payload.get("articles", []):
        name = (item.get("source") or {}).get("name") or "Presse"
        source = {"id": "newsapi:" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"), "name": name, "weight": 0.8}
        a = feeds._build(
            source, now, item.get("title"), item.get("url"), item.get("publishedAt"),
            item.get("description") or "", "", feeds._https(item.get("urlToImage")), [],
        )
        if a:
            out.append(a)
    return out


def fetch_top_headlines(api_key: str, now: datetime) -> list[dict]:
    req = urllib.request.Request(URL, headers={"X-Api-Key": api_key, "User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(req, timeout=config.FETCH_TIMEOUT_S) as r:
        return parse_response(json.loads(r.read(config.FETCH_MAX_BYTES)), now)
