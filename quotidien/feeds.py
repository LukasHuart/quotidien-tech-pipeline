"""Collecte et analyse des flux RSS 2.0 / Atom (bibliothèque standard + defusedxml)."""
from __future__ import annotations

import hashlib
import html
import logging
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

try:
    from defusedxml import ElementTree as ET  # protège contre les flux XML malveillants
except ImportError:  # pragma: no cover
    import xml.etree.ElementTree as ET

from . import config

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
}
_SCRIPT = re.compile(r"(?is)<(script|style)\b.*?</\1>")
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_IMG = re.compile(r"""(?i)<img[^>]+src=["']([^"']+)["']""")
_TRACKING = {"fbclid", "gclid", "ref", "ref_src", "mc_cid", "mc_eid"}


def normalize_url(url: str) -> str:
    p = urllib.parse.urlsplit(url.strip())
    query = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
        if k.lower() not in _TRACKING and not k.lower().startswith("utm_")
    ]
    path = p.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit(
        ((p.scheme or "https").lower(), p.netloc.lower(), path, urllib.parse.urlencode(query), "")
    )


def article_id(url: str) -> str:
    return hashlib.sha1(normalize_url(url).encode("utf-8")).hexdigest()[:20]


def clean_text(s: str | None) -> str:
    s = _SCRIPT.sub(" ", s or "")
    s = _TAG.sub(" ", s)
    return _WS.sub(" ", html.unescape(s)).strip()


def truncate(s: str, limit: int = config.EXCERPT_MAX_CHARS) -> str:
    if len(s) <= limit:
        return s
    head = s[:limit]
    # Si possible, couper à la fin d'une phrase : une phrase entière se traduit bien mieux qu'un morceau.
    ends = [m.end() for m in re.finditer(r"[.!?](?=\s)", head)]
    if ends and ends[-1] >= limit * 0.5:
        return head[: ends[-1]]
    cut = head.rsplit(" ", 1)[0].rstrip(" ,;:.-")
    return cut + "…"


def parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def _https(url: str | None) -> str | None:
    url = (url or "").strip()
    return url if url.lower().startswith("https://") else None


def _image_from_html(markup: str) -> str | None:
    m = _IMG.search(markup or "")
    return _https(m.group(1)) if m else None


def _rss_image(item, markup: str) -> str | None:
    for el in item.findall("media:thumbnail", NS):
        if _https(el.get("url")):
            return _https(el.get("url"))
    for el in item.findall("media:content", NS):
        kind = (el.get("medium") or el.get("type") or "")
        if kind.startswith("image") and _https(el.get("url")):
            return _https(el.get("url"))
    for el in item.findall("enclosure"):
        if (el.get("type") or "").startswith("image") and _https(el.get("url")):
            return _https(el.get("url"))
    return _image_from_html(markup)


def _build(source: dict, now: datetime, title, link, date, summary, content, image, cats) -> dict | None:
    title = clean_text(title)
    link = (link or "").strip()
    if not title or not link.lower().startswith(("http://", "https://")):
        return None
    body = clean_text(content) if content else ""
    return {
        "id": article_id(link),
        "url": normalize_url(link),
        "title": title,
        "excerpt": truncate(clean_text(summary) or body),
        "image": image,
        "categories": [c for c in cats if c][:6],
        "published": parse_date(date) or now,
        "source_id": source["id"],
        "source": source["name"],
        "weight": float(source.get("weight", 1.0)),
        "words": len(body.split()) if body else None,
    }


def parse_feed(data: bytes, source: dict, now: datetime) -> list[dict]:
    root = ET.fromstring(data)
    out: list[dict] = []
    if root.tag.endswith("}feed") or root.tag == "feed":  # Atom
        for e in root.findall("atom:entry", NS):
            link = ""
            for l in e.findall("atom:link", NS):
                if l.get("rel", "alternate") == "alternate" and l.get("href"):
                    link = l.get("href")
                    break
            summary = e.findtext("atom:summary", namespaces=NS) or ""
            content = e.findtext("atom:content", namespaces=NS) or ""
            image = _rss_image(e, content or summary)
            cats = [clean_text(c.get("term")) for c in e.findall("atom:category", NS)]
            date = e.findtext("atom:published", namespaces=NS) or e.findtext("atom:updated", namespaces=NS)
            a = _build(source, now, e.findtext("atom:title", namespaces=NS), link, date, summary, content, image, cats)
            if a:
                out.append(a)
    else:  # RSS 2.0
        for it in root.iter("item"):
            link = (it.findtext("link") or "").strip()
            guid = it.find("guid")
            if not link and guid is not None and guid.get("isPermaLink", "true") != "false":
                link = (guid.text or "").strip()
            desc = it.findtext("description") or ""
            content = it.findtext("content:encoded", namespaces=NS) or ""
            date = it.findtext("pubDate") or it.findtext("dc:date", namespaces=NS)
            image = _rss_image(it, content or desc)
            cats = [clean_text(c.text) for c in it.findall("category")]
            a = _build(source, now, it.findtext("title"), link, date, desc, content, image, cats)
            if a:
                out.append(a)
    out.sort(key=lambda a: a["published"], reverse=True)
    return out[: config.MAX_ITEMS_PER_FEED]


def fetch_bytes(url: str) -> bytes:
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise ValueError("schéma d'URL non autorisé")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": config.USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=config.FETCH_TIMEOUT_S) as r:
        data = r.read(config.FETCH_MAX_BYTES + 1)
    if len(data) > config.FETCH_MAX_BYTES:
        raise ValueError("flux trop volumineux")
    return data


def collect_all(sources: list[dict], now: datetime, fetch=fetch_bytes) -> tuple[list[dict], list[str]]:
    """Récupère tous les flux en parallèle. Un flux en panne n'empêche pas les autres."""
    errors: list[str] = []

    def one(src: dict) -> list[dict]:
        try:
            return parse_feed(fetch(src["url"]), src, now)
        except Exception as exc:  # noqa: BLE001 - on veut tout attraper ici
            errors.append(f'{src["id"]}: {type(exc).__name__}: {exc}')
            logging.warning("Flux %s en échec : %s", src["id"], exc)
            return []

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(one, sources))
    return [a for r in results for a in r], errors
