"""Point d'entrée : lancé toutes les ~20 min par GitHub Actions (voir .github/workflows/daily.yml).

Variables d'environnement :
  FIREBASE_SERVICE_ACCOUNT  (obligatoire) contenu JSON de la clé du compte de service, via un « secret » GitHub
  NEWSAPI_KEY               (facultatif)  clé d'une API d'actualités
"""
import logging
import os
import sys
from datetime import datetime, timezone

from quotidien import runner


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "").strip()
    if not raw:
        logging.error("Secret FIREBASE_SERVICE_ACCOUNT absent : voir README, étape « secret ».")
        return 2
    from quotidien.store import FirestoreStore

    store = FirestoreStore(raw)
    stats = runner.run(store, datetime.now(timezone.utc), os.environ.get("NEWSAPI_KEY") or None)
    logging.info("terminé : %s", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
