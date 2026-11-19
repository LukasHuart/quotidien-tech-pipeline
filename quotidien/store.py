"""Accès à Firestore (Firebase Admin SDK). Seul module qui dépend de firebase-admin.

Interface utilisée par runner.py :
  get_state / set_state, list_users, update_user, recent_articles, write_articles,
  seen_ids, save_edition, notify, cleanup
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from . import config

log = logging.getLogger("quotidien")

_ARTICLE_FIELDS = (
    "id", "url", "title", "excerpt", "image", "categories", "published", "source_id",
    "source", "weight", "words", "topics", "mentions", "sources",
)
_STATE_DOC = ("config", "pipeline")


class FirestoreStore:
    def __init__(self, service_account_json: str):
        import firebase_admin
        from firebase_admin import credentials, firestore

        firebase_admin.initialize_app(credentials.Certificate(json.loads(service_account_json)))
        self.db = firestore.client()
        self._firestore = firestore

    # -- état technique du pipeline (dernière collecte, dernier nettoyage)
    def _state_ref(self):
        return self.db.collection(_STATE_DOC[0]).document(_STATE_DOC[1])

    def get_state(self) -> dict:
        snap = self._state_ref().get()
        return snap.to_dict() or {} if snap.exists else {}

    def set_state(self, values: dict) -> None:
        self._state_ref().set(values, merge=True)

    # -- utilisateurs
    def list_users(self) -> list[dict]:
        return [{"id": d.id, "data": d.to_dict() or {}} for d in self.db.collection("users").stream()]

    def update_user(self, uid: str, values: dict) -> None:
        self.db.collection("users").document(uid).update(values)

    # -- articles
    def recent_articles(self, since: datetime) -> list[dict]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        q = self.db.collection("articles").where(filter=FieldFilter("published", ">=", since))
        out = []
        for d in q.stream():
            a = d.to_dict()
            a["id"] = d.id
            out.append(a)
        return out

    def _commit(self, ops, size: int = 400) -> None:
        for i in range(0, len(ops), size):
            batch = self.db.batch()
            for ref, data, merge in ops[i:i + size]:
                batch.set(ref, data, merge=merge)
            batch.commit()

    def write_articles(self, to_create: list[dict], to_update: list[dict], now: datetime) -> None:
        col = self.db.collection("articles")
        ops = []
        for a in to_create:
            data = {k: a.get(k) for k in _ARTICLE_FIELDS}
            data["fetchedAt"] = now
            ops.append((col.document(a["id"]), data, False))
        for u in to_update:
            ops.append((col.document(u["id"]), {"mentions": u["mentions"], "sources": u["sources"]}, True))
        self._commit(ops)

    # -- éditions
    def seen_ids(self, uid: str, since: datetime) -> set[str]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        q = self.db.collection("users").document(uid).collection("editions").where(
            filter=FieldFilter("createdAt", ">=", since))
        return {i for d in q.stream() for i in (d.to_dict().get("articleIds") or [])}

    def save_edition(self, uid: str, ed: dict) -> None:
        self.db.collection("users").document(uid).collection("editions").document(ed["date"]).set(ed)

    def notify(self, uid: str, data: dict, ed: dict) -> None:
        tokens = list(data.get("fcmTokens") or [])
        if not tokens:
            return
        try:
            from firebase_admin import messaging

            msg = messaging.MulticastMessage(
                tokens=tokens,
                notification=messaging.Notification(title="Votre édition du matin est prête", body=ed["une"]["title"]),
                data={"editionDate": ed["date"]},
                android=messaging.AndroidConfig(
                    priority="high", notification=messaging.AndroidNotification(channel_id="edition")),
            )
            resp = messaging.send_each_for_multicast(msg)
            dead = [t for t, r in zip(tokens, resp.responses)
                    if r.exception is not None
                    and isinstance(r.exception, (messaging.UnregisteredError, messaging.SenderIdMismatchError))]
            if dead:
                self.db.collection("users").document(uid).update({"fcmTokens": self._firestore.ArrayRemove(dead)})
        except Exception:  # noqa: BLE001 - une notification ratée ne doit pas casser l'édition
            log.warning("notification non envoyée")

    # -- nettoyage
    def _delete_query(self, query, size: int = 400) -> None:
        while True:
            docs = list(query.limit(size).stream())
            if not docs:
                return
            batch = self.db.batch()
            for d in docs:
                batch.delete(d.reference)
            batch.commit()

    def cleanup(self, now: datetime) -> None:
        from google.cloud.firestore_v1.base_query import FieldFilter

        self._delete_query(self.db.collection("articles").where(
            filter=FieldFilter("published", "<", now - timedelta(days=config.ARTICLE_RETENTION_DAYS))))
        cutoff = now - timedelta(days=config.EDITION_RETENTION_DAYS)
        for u in self.db.collection("users").select([]).stream():
            self._delete_query(u.reference.collection("editions").where(filter=FieldFilter("createdAt", "<", cutoff)))
