"""Paramètres centraux du pipeline (un seul endroit pour tout régler)."""

EDITION_SIZE = 12            # 1 Une + N_MORE secondaires + le reste en brèves
N_MORE = 4
MAX_PER_SOURCE = 3           # diversité : pas plus de 3 articles d'une même source
CANDIDATE_WINDOW_HOURS = 36  # un article reste « éligible » 36 h
SEEN_WINDOW_DAYS = 7         # on ne repropose pas un article vu dans les 7 derniers jours
ARTICLE_RETENTION_DAYS = 7
EDITION_RETENTION_DAYS = 60
DELIVERY_LEAD_MINUTES = 45   # l'édition est préparée jusqu'à 45 min avant l'heure choisie : GitHub peut
                             # retarder une exécution de 5 à 30 min, l'édition est ainsi prête à temps
COLLECT_EVERY_MIN = 110      # relire les flux au plus toutes les ~2 h
COLLECT_BEFORE_DELIVERY_MIN = 30  # ... mais s'assurer que la collecte a moins de 30 min avant de composer
CLEANUP_EVERY_H = 23         # nettoyage une fois par jour
EXCERPT_MAX_CHARS = 280      # extrait court + lien vers la source (pas de reprise d'articles entiers)
FETCH_TIMEOUT_S = 15
FETCH_MAX_BYTES = 5_000_000
MAX_ITEMS_PER_FEED = 40
USER_AGENT = "LeQuotidienTech/0.1 (projet personnel)"
