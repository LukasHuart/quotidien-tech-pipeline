"""Orchestration d'une exécution du pipeline (appelée toutes les ~20 min par GitHub Actions).

Une exécution fait, dans l'ordre :
  1. lit les utilisateurs et (re)calcule `nextDeliveryAt` quand leurs réglages ont changé ;
  2. collecte les flux si la dernière collecte est trop ancienne ;
  3. compose l'édition des utilisateurs dont l'heure de livraison approche ;
  4. nettoie les vieilles données (une fois par jour).

Ce module ne connaît pas Firebase : il parle à un « store » (voir store.py) → testable hors ligne.
Les journaux sont publics (dépôt public) : on n'y écrit JAMAIS d'identifiant ni de donnée d'utilisateur.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from . import config, dedupe, edition as editionlib, feeds, newsapi, timeutil
from . import topics as topiclib
from .sources import SOURCES

log = logging.getLogger("quotidien")


def schedule_sig(data: dict) -> str:
    """Empreinte des réglages de livraison : si elle change, on recalcule `nextDeliveryAt`."""
    custom = ",".join(str(int(d)) for d in sorted(data.get("deliveryCustomDays") or []))
    return "|".join([
        str(data.get("timezone", "Europe/Paris")), str(data.get("deliveryTime", "08:00")),
        str(data.get("deliveryDays", "all")), custom,
    ])


def _next(after: datetime, data: dict) -> datetime:
    return timeutil.next_delivery_utc(
        after, data.get("timezone", "Europe/Paris"), data.get("deliveryTime", "08:00"),
        data.get("deliveryDays", "all"), data.get("deliveryCustomDays") or [])


def _older_than(state: dict, key: str, now: datetime, delta: timedelta) -> bool:
    last = state.get(key)
    return last is None or now - last >= delta


# ---------------------------------------------------------------- collecte

def collect(store, now: datetime, newsapi_key: str | None = None, fetch=feeds.fetch_bytes) -> dict:
    fetched, errors = feeds.collect_all(SOURCES, now, fetch=fetch)
    if newsapi_key:
        try:
            fetched += newsapi.fetch_top_headlines(newsapi_key, now)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"newsapi: {type(exc).__name__}")
    for e in errors:
        log.warning("collecte : %s", e)
    since = now - timedelta(hours=48)
    fetched = [topiclib.tag(a) for a in fetched if a["published"] >= since]
    existing = store.recent_articles(since)
    to_create, to_update = dedupe.merge_batches(existing, fetched)
    store.write_articles(to_create, to_update, now)
    log.info("collecte : %d nouveaux, %d mis à jour, %d flux en erreur", len(to_create), len(to_update), len(errors))
    return {"created": len(to_create), "updated": len(to_update), "feed_errors": len(errors)}


# ---------------------------------------------------------------- livraison

def _deliver(store, user: dict, articles: list[dict], now: datetime, first: bool) -> dict:
    """Compose et enregistre l'édition ; renvoie les champs à écrire sur le profil."""
    data = user["data"]
    tz = data.get("timezone", "Europe/Paris")
    target = data.get("nextDeliveryAt")
    update: dict = {}
    # Date de l'édition = jour local de l'heure visée (sauf rattrapage tardif / première édition).
    ref = target if (target is not None and not first and now - target < timedelta(hours=12)) else now
    try:
        ed = editionlib.build_edition(data.get("topics", []), articles, store.seen_ids(user["id"], now - timedelta(days=config.SEEN_WINDOW_DAYS)), now, tz)
        if ed:
            ed["date"] = ref.astimezone(timeutil.ZoneInfo(tz)).date().isoformat()
            store.save_edition(user["id"], ed)
            update["lastEditionDate"] = ed["date"]
            store.notify(user["id"], data, ed)
        else:
            log.info("aucun article disponible pour une édition")
    except Exception:  # noqa: BLE001
        log.exception("échec de composition d'une édition")
    return update


def run(store, now: datetime, newsapi_key: str | None = None, fetch=feeds.fetch_bytes) -> dict:
    stats = {"users": 0, "scheduled": 0, "delivered": 0, "collected": False, "cleaned": False}
    state = store.get_state()
    new_state: dict = {}
    users = store.list_users()
    stats["users"] = len(users)

    # 1) planification : nouveaux utilisateurs et réglages modifiés
    updates: dict[str, dict] = {}
    first_ids: set[str] = set()
    for u in users:
        d = u["data"]
        sig = schedule_sig(d)
        if d.get("nextDeliveryAt") is None or d.get("scheduleSig") != sig:
            try:
                nxt = _next(now, d)
            except Exception:  # noqa: BLE001 - réglage invalide : on ignore cet utilisateur
                log.warning("réglages de livraison invalides pour un utilisateur")
                d["nextDeliveryAt"] = None
                continue
            if d.get("nextDeliveryAt") is None and not d.get("lastEditionDate"):
                first_ids.add(u["id"])  # tout nouveau : première édition tout de suite
            d["nextDeliveryAt"], d["scheduleSig"] = nxt, sig
            updates[u["id"]] = {"nextDeliveryAt": nxt, "scheduleSig": sig}
            stats["scheduled"] += 1

    # 2) qui est servi maintenant ?
    horizon = now + timedelta(minutes=config.DELIVERY_LEAD_MINUTES)
    due = [u for u in users
           if u["id"] in first_ids or (u["data"].get("nextDeliveryAt") is not None and u["data"]["nextDeliveryAt"] <= horizon)]

    # 3) collecte (fraîche avant de composer)
    max_age = config.COLLECT_BEFORE_DELIVERY_MIN if due else config.COLLECT_EVERY_MIN
    if _older_than(state, "lastCollectAt", now, timedelta(minutes=max_age)):
        try:
            collect(store, now, newsapi_key, fetch)
            new_state["lastCollectAt"] = now
            stats["collected"] = True
        except Exception:  # noqa: BLE001
            log.exception("échec de la collecte")

    # 4) livraison
    if due:
        articles = store.recent_articles(now - timedelta(hours=config.CANDIDATE_WINDOW_HOURS))
        for u in due:
            d = u["data"]
            first = u["id"] in first_ids
            upd = _deliver(store, u, articles, now, first)
            if not first:  # première édition : la prochaine (déjà planifiée) reste celle de demain
                try:  # toujours avancer : sinon on retenterait à chaque exécution
                    upd["nextDeliveryAt"] = _next(max(now, d["nextDeliveryAt"]), d)
                    upd["scheduleSig"] = schedule_sig(d)
                except Exception:  # noqa: BLE001
                    log.warning("impossible de planifier la prochaine édition d'un utilisateur")
            updates.setdefault(u["id"], {}).update(upd)
            stats["delivered"] += 1 if "lastEditionDate" in upd else 0

    for uid, upd in updates.items():
        try:
            store.update_user(uid, upd)
        except Exception:  # noqa: BLE001 - ex. compte supprimé entre-temps
            log.warning("mise à jour impossible d'un profil")

    # 5) nettoyage quotidien
    if _older_than(state, "lastCleanupAt", now, timedelta(hours=config.CLEANUP_EVERY_H)):
        try:
            store.cleanup(now)
            new_state["lastCleanupAt"] = now
            stats["cleaned"] = True
        except Exception:  # noqa: BLE001
            log.exception("échec du nettoyage")

    if new_state:
        store.set_state(new_state)
    return stats
