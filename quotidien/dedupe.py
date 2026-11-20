"""Regroupe les articles qui racontent la même histoire (même URL ou titres très proches)."""
from __future__ import annotations

import logging
import re

log = logging.getLogger("quotidien")

_STOP = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was", "new", "its", "has", "have",
    "will", "after", "over", "into", "how", "why", "what", "who", "your", "you", "can", "more",
    "than", "but", "not", "out", "about", "says", "say",
}


def _stem(t: str) -> str:
    """Racine grossière : « patches / patched / patching » → « patch »."""
    for suf, rep in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if t.endswith(suf) and len(t) - len(suf) >= 4:
            t = t[: -len(suf)] + rep
            break
    return t[:-1] if t.endswith("e") and len(t) > 4 else t


def tokens(text: str) -> frozenset[str]:
    return frozenset(_stem(t) for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) >= 3 and t not in _STOP)


def title_tokens(title: str) -> frozenset[str]:
    return tokens(title)


def body_tokens(a: dict) -> frozenset[str]:
    """Titre + extrait : deux articles sur le même sujet partagent beaucoup de mots même si les titres diffèrent."""
    return tokens(f'{a.get("title", "")} {a.get("excerpt", "")}')


def similar(a: frozenset[str], b: frozenset[str], threshold: float = 0.5) -> bool:
    """Même histoire (regroupement strict, à la collecte) : titres très proches."""
    inter = len(a & b)
    if inter < 3:
        return False
    return inter / len(a | b) >= threshold or inter / min(len(a), len(b)) >= 0.6


def same_story(x: dict, y: dict) -> bool:
    """Garde-fou plus large, utilisé à la composition d'une édition : ne pas montrer deux fois l'histoire.
    Écarter à tort un article coûte peu (il est remplacé par le suivant) ; en montrer deux fois gêne."""
    ta, tb = title_tokens(x["title"]), title_tokens(y["title"])
    inter = len(ta & tb)
    small = min(len(ta), len(tb)) or 1
    if (inter >= 3 and inter / small >= 0.5) or (inter >= 2 and inter / small >= 0.75):
        return True
    ba, bb = body_tokens(x), body_tokens(y)
    shared = len(ba & bb)
    return shared >= 5 and shared / (min(len(ba), len(bb)) or 1) >= 0.4


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
            if items[i]["id"] == items[j]["id"]:
                parent[find(i)] = find(j)
            elif similar(toks[i], toks[j]):
                parent[find(i)] = find(j)
                if not (items[i].get("_existing") and items[j].get("_existing")):
                    log.info("doublon regroupé : « %.70s » ≈ « %.70s »", items[i]["title"], items[j]["title"])
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
