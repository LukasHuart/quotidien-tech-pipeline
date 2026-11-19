"""Flux RSS/Atom suivis. `weight` (≈0,8 à 1,3) pondère la fiabilité/importance d'une source.

À VÉRIFIER avant la mise en production : les adresses de flux changent parfois,
et chaque site a ses propres conditions d'utilisation.
"""

SOURCES = [
    {"id": "ars", "name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "weight": 1.2},
    {"id": "verge", "name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "weight": 1.0},
    {"id": "techcrunch", "name": "TechCrunch", "url": "https://techcrunch.com/feed/", "weight": 1.0},
    {"id": "wired", "name": "Wired", "url": "https://www.wired.com/feed/rss", "weight": 1.0},
    {"id": "register", "name": "The Register", "url": "https://www.theregister.com/headlines.atom", "weight": 0.9},
    {"id": "hn", "name": "Hacker News", "url": "https://hnrss.org/frontpage", "weight": 0.9},
    {"id": "krebs", "name": "Krebs on Security", "url": "https://krebsonsecurity.com/feed/", "weight": 1.0},
    {"id": "bleeping", "name": "BleepingComputer", "url": "https://www.bleepingcomputer.com/feed/", "weight": 1.0},
    {"id": "androidauthority", "name": "Android Authority", "url": "https://www.androidauthority.com/feed/", "weight": 0.9},
    {"id": "9to5google", "name": "9to5Google", "url": "https://9to5google.com/feed/", "weight": 0.9},
    {"id": "petapixel", "name": "PetaPixel", "url": "https://petapixel.com/feed/", "weight": 0.9},
    {"id": "phoronix", "name": "Phoronix", "url": "https://www.phoronix.com/rss.php", "weight": 0.8},
]
