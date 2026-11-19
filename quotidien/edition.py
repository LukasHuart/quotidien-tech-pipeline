"""Compose l'édition du jour d'un utilisateur : 1 Une, 4 secondaires, le reste en brèves."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config, scoring, topics as topiclib


def _tags(x: dict) -> list[str]:
    if x["labels"]:
        return x["labels"][:2]
    return [topiclib.CATALOGUE[t]["label"] for t in x["a"].get("topics", [])[:1] if t in topiclib.CATALOGUE]


def _snapshot(x: dict, full: bool) -> dict:
    a = x["a"]
    d = {
        "id": a["id"], "title": a["title"], "url": a["url"], "source": a["source"],
        "publishedAt": a["published"].isoformat(), "tags": _tags(x),
    }
    if full:
        d["excerpt"] = a.get("excerpt", "")
        d["image"] = a.get("image")
    if a.get("words"):
        d["readMinutes"] = max(1, round(a["words"] / 220))
    return d


def build_edition(user_topics, articles, seen_ids, now: datetime, tz_name: str = "Europe/Paris",
                  size: int = config.EDITION_SIZE, n_more: int = config.N_MORE) -> dict | None:
    topics = topiclib.resolve_user_topics(user_topics)
    cutoff = now - timedelta(hours=config.CANDIDATE_WINDOW_HOURS)
    scored = []
    for a in articles:
        if a["published"] < cutoff or a["id"] in seen_ids:
            continue
        st = {t["id"]: topiclib.strength(a, t["keywords"]) for t in topics}
        st = {k: v for k, v in st.items() if v > 0}
        best = max(st.values(), default=0.0)
        base = scoring.base_score(a, now)
        if not topics:
            score = base
        else:
            score = base + 1.5 * best if best > 0 else base * 0.5
        labels = [t["label"] for t in sorted(topics, key=lambda t: -st.get(t["id"], 0)) if t["id"] in st]
        scored.append({"a": a, "score": score, "st": st, "matched": best > 0, "labels": labels})
    if not scored:
        return None
    scored.sort(key=lambda x: -x["score"])

    chosen, ids, per_source = [], set(), Counter()

    def room(x):
        return x["a"]["id"] not in ids and per_source[x["a"]["source_id"]] < config.MAX_PER_SOURCE

    def add(x):
        chosen.append(x)
        ids.add(x["a"]["id"])
        per_source[x["a"]["source_id"]] += 1

    # 1) couverture : au moins un article pour chaque thème choisi (dans l'ordre de l'utilisateur)
    coverage_cap = max(1, size - 4)
    for t in topics:
        if len(chosen) >= coverage_cap:
            break
        for x in scored:
            if t["id"] in x["st"] and room(x):
                add(x)
                break
    # 2) complément : d'abord les articles qui correspondent aux thèmes, puis le reste
    for want_matched in (True, False):
        for x in scored:
            if len(chosen) >= size:
                break
            if x["matched"] == want_matched and room(x):
                add(x)

    chosen.sort(key=lambda x: -x["score"])
    une, more, brefs = chosen[0], chosen[1:1 + n_more], chosen[1 + n_more:]
    return {
        "date": now.astimezone(ZoneInfo(tz_name)).date().isoformat(),
        "createdAt": now,
        "une": _snapshot(une, True),
        "more": [_snapshot(x, True) for x in more],
        "brefs": [_snapshot(x, False) for x in brefs],
        "articleIds": [x["a"]["id"] for x in chosen],
        "count": len(chosen),
    }
