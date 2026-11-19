"""Regroupe les articles qui racontent la même histoire (même URL ou titres très proches)."""
from __future__ import annotations

import re

_STOP = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was", "new", "its", "has", "have",
    "will", "after", "over", "into", "how", "why", "what", "who", "your", "you", "can", "more",
    "than", "but", "not", "out", "about", "says", "say",
}


def title_tokens(title: str) -> frozenset[str]:
    return frozenset(t for t in re.findall(r"[a-z0-9]+", title.lower()) if len(t) >= 3 and t not in _STOP)


def similar(a: frozenset[str], b: frozenset[str], threshold: float = 0.5) -> bool:
    inter = len(a & b)
    return inter >= 3 and inter / len(a | b) >= threshold


def cluster(items: list[dict]) -> list[list[int]]:
    parent = list(range(len(items)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    toks = [title_tokens(a["title"]) for a in items]
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i]["id"] == items[j]["id"] or similar(toks[i], toks[j]):
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(len(items)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _best(group: list[dict]) -> dict:
    return max(group, key=lambda g: (g.get("weight", 1.0), bool(g.get("image")), len(g.get("excerpt", ""))))


def merge_batches(existing: list[dict], fetched: list[dict]) -> tuple[list[dict], list[dict]]:
    """Retourne (à_créer, à_mettre_à_jour).

    - Une histoire déjà en base garde son document ; on met seulement à jour `mentions`/`sources`.
    - Une nouvelle histoire n'est créée qu'une fois, avec la meilleure version parmi les sources.
    `mentions` = nombre de sources distinctes qui en parlent (signal d'importance).
    """
    items = [{**a, "_existing": True, "sources": list(a.get("sources") or [a["source_id"]])} for a in existing]
    items += [{**a, "_existing": False, "sources": [a["source_id"]]} for a in fetched]
    to_create: list[dict] = []
    to_update: list[dict] = []
    for idxs in cluster(items):
        group = [items[i] for i in idxs]
        sources = sorted({s for g in group for s in g["sources"]})
        old = [g for g in group if g["_existing"]]
        if old:
            rep = min(old, key=lambda g: g["published"])
            if set(rep["sources"]) != set(sources):
                to_update.append({"id": rep["id"], "mentions": len(sources), "sources": sources})
        else:
            rep = {k: v for k, v in _best(group).items() if k != "_existing"}
            rep["mentions"] = len(sources)
            rep["sources"] = sources
            to_create.append(rep)
    return to_create, to_update
