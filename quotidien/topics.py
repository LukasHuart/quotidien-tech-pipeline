"""Catalogue de thèmes et association article ↔ thème par mots-clés (sans IA, gratuit)."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

CATALOGUE: dict[str, dict] = {
    t["id"]: t for t in json.loads((Path(__file__).with_name("topics.json")).read_text("utf-8"))
}


@lru_cache(maxsize=512)
def _compile(keyword: str) -> re.Pattern:
    esc = re.escape(keyword)
    short_caps = keyword.isupper() and len(keyword) <= 4  # « AI », « CPU »… : sensibles à la casse
    suffix = "" if short_caps or not re.fullmatch(r"[A-Za-z][A-Za-z \-]*", keyword) else "(?:s|es)?"
    return re.compile(rf"(?<!\w){esc}{suffix}(?!\w)", 0 if short_caps else re.I)


def keyword_hits(title: str, body: str, keywords: list[str]) -> int:
    """Titre : 3 points par mot-clé ; corps (extrait + catégories) : 1 point par mot-clé."""
    score = 0
    for kw in keywords:
        pat = _compile(kw)
        if pat.search(title):
            score += 3
        if pat.search(body):
            score += 1
    return score


def _body(a: dict) -> str:
    return (a.get("excerpt") or "") + " " + " ".join(a.get("categories") or [])


def strength(a: dict, keywords: list[str]) -> float:
    """0 si le lien est trop faible, sinon une valeur entre 0,25 et 1."""
    raw = keyword_hits(a["title"], _body(a), keywords)
    return 0.0 if raw < 2 else min(raw, 8) / 8


def tag(a: dict) -> dict:
    """Ajoute `topics` (ids du catalogue, max 3) pour l'affichage et les filtres."""
    found = [(strength(a, t["keywords_en"]), tid) for tid, t in CATALOGUE.items()]
    found = sorted([f for f in found if f[0] > 0], reverse=True)[:3]
    a["topics"] = [tid for _, tid in found]
    return a


def resolve_user_topics(user_topics: list[dict]) -> list[dict]:
    """Thèmes d'un utilisateur → [{id, label, keywords}].

    - Thème du catalogue : on peut ne donner que `id`.
    - Thème libre (ex. « Astrophotographie ») : l'appli fournit `label` + `keywords` (en anglais).
    """
    out, seen = [], set()
    for t in user_topics or []:
        tid = t.get("id")
        if not tid or tid in seen:
            continue
        cat = CATALOGUE.get(tid)
        keywords = list(t.get("keywords") or (cat or {}).get("keywords_en") or [])
        if not keywords:
            continue
        seen.add(tid)
        out.append({"id": tid, "label": t.get("label") or (cat or {}).get("label") or tid, "keywords": keywords})
    return out
