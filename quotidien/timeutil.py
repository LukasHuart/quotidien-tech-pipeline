"""Calcul de l'heure de livraison (fuseau horaire et changement d'heure inclus)."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc


def parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    t = time(int(h), int(m))
    return t


def allowed_weekdays(mode: str = "all", custom=()) -> set[int]:
    """0 = lundi … 6 = dimanche."""
    if mode == "weekdays":
        return {0, 1, 2, 3, 4}
    if mode == "custom" and custom:
        return {int(d) for d in custom}
    return set(range(7))


def next_delivery_utc(after: datetime, tz_name: str, hhmm: str, mode: str = "all", custom=()) -> datetime:
    """Prochaine livraison STRICTEMENT après `after` (datetime avec fuseau)."""
    tz = ZoneInfo(tz_name)
    t = parse_hhmm(hhmm)
    days = allowed_weekdays(mode, custom)
    start = after.astimezone(tz).date()
    for i in range(9):
        d = start + timedelta(days=i)
        if d.weekday() not in days:
            continue
        cand = datetime.combine(d, t, tzinfo=tz).astimezone(UTC)
        if cand > after:
            return cand
    raise ValueError("aucun jour de livraison valide")
