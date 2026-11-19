import unittest
from datetime import datetime, timedelta, timezone

from quotidien import config, runner

UTC = timezone.utc
# 16 nov 2026 = lundi ; 06:00 UTC = 07:00 à Paris (heure d'hiver)
NOW = datetime(2026, 11, 16, 6, 0, tzinfo=UTC)

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
<item><title>Mirrorless camera adds a faster sensor</title><link>https://ex.test/cam</link>
<pubDate>Mon, 16 Nov 2026 05:00:00 +0000</pubDate><description>New camera body.</description></item>
<item><title>Kernel 7.0 released with new scheduler</title><link>https://ex.test/kernel</link>
<pubDate>Mon, 16 Nov 2026 04:00:00 +0000</pubDate><description>Linux update.</description></item>
</channel></rss>"""


def fake_fetch(url):
    return RSS


def failing_fetch(url):
    raise OSError("réseau coupé")


class MemoryStore:
    """Même interface que FirestoreStore, tout en mémoire."""

    def __init__(self, users=None):
        self.users = {u["id"]: u["data"] for u in (users or [])}
        self.articles, self.editions, self.state = {}, {}, {}
        self.notified, self.cleaned = [], []

    def get_state(self): return dict(self.state)
    def set_state(self, v): self.state.update(v)
    def list_users(self): return [{"id": k, "data": dict(v)} for k, v in self.users.items()]
    def update_user(self, uid, v): self.users[uid].update(v)
    def recent_articles(self, since): return [dict(a) for a in self.articles.values() if a["published"] >= since]

    def write_articles(self, to_create, to_update, now):
        for a in to_create:
            self.articles[a["id"]] = dict(a)
        for u in to_update:
            self.articles[u["id"]].update(mentions=u["mentions"], sources=u["sources"])

    def seen_ids(self, uid, since):
        return {i for (u, _), e in self.editions.items() if u == uid and e["createdAt"] >= since for i in e["articleIds"]}

    def save_edition(self, uid, ed): self.editions[(uid, ed["date"])] = ed
    def notify(self, uid, data, ed): self.notified.append(uid)
    def cleanup(self, now): self.cleaned.append(now)


def user(uid="u1", **kw):
    d = {"topics": [{"id": "photo"}], "timezone": "Europe/Paris", "deliveryTime": "08:00", "deliveryDays": "all"}
    d.update(kw)
    return {"id": uid, "data": d}


class Runner(unittest.TestCase):
    def test_new_user_gets_scheduled_and_first_edition_now(self):
        s = MemoryStore([user()])
        st = runner.run(s, NOW, fetch=fake_fetch)
        self.assertEqual(st["delivered"], 1)
        self.assertEqual(len(s.editions), 1)
        d = s.users["u1"]
        # prochaine = demain... non : aujourd'hui 08:00 Paris = 07:00 UTC est dans le futur (NOW = 07:00 Paris)
        self.assertEqual(d["nextDeliveryAt"], datetime(2026, 11, 16, 7, 0, tzinfo=UTC))
        self.assertEqual(d["lastEditionDate"], "2026-11-16")
        self.assertTrue(d["scheduleSig"])

    def test_first_edition_does_not_skip_next_day(self):
        s = MemoryStore([user(deliveryTime="06:00")])  # 06:00 Paris = 05:00 UTC, déjà passé → demain
        runner.run(s, NOW, fetch=fake_fetch)
        self.assertEqual(s.users["u1"]["nextDeliveryAt"], datetime(2026, 11, 17, 5, 0, tzinfo=UTC))

    def test_due_user_is_served_in_advance_and_advanced(self):
        s = MemoryStore([user(lastEditionDate="2026-11-15")])
        runner.run(s, NOW - timedelta(days=1), fetch=fake_fetch)  # planifie (dimanche 07:00 UTC → lundi)
        s.users["u1"]["nextDeliveryAt"] = datetime(2026, 11, 16, 7, 0, tzinfo=UTC)
        s.articles.clear(); s.editions.clear(); s.state.clear()
        now = datetime(2026, 11, 16, 6, 30, tzinfo=UTC)  # 30 min avant l'heure → dans la fenêtre de 45 min
        st = runner.run(s, now, fetch=fake_fetch)
        self.assertEqual(st["delivered"], 1)
        ed = s.editions[("u1", "2026-11-16")]
        self.assertGreaterEqual(ed["count"], 2)
        self.assertEqual(s.users["u1"]["nextDeliveryAt"], datetime(2026, 11, 17, 7, 0, tzinfo=UTC))
        self.assertEqual(s.notified, ["u1"])

    def test_not_due_user_is_left_alone(self):
        s = MemoryStore([user(lastEditionDate="2026-11-15")])
        runner.run(s, NOW - timedelta(hours=5), fetch=fake_fetch)
        s.editions.clear()
        st = runner.run(s, NOW - timedelta(hours=4), fetch=fake_fetch)  # 03:00 UTC, livraison à 07:00 UTC
        self.assertEqual(st["delivered"], 0)
        self.assertFalse(s.editions)

    def test_changed_settings_reschedule(self):
        s = MemoryStore([user(lastEditionDate="2026-11-15")])
        runner.run(s, NOW - timedelta(hours=5), fetch=fake_fetch)
        s.users["u1"]["deliveryTime"] = "21:30"  # l'utilisateur change l'heure
        runner.run(s, NOW - timedelta(hours=5), fetch=fake_fetch)
        self.assertEqual(s.users["u1"]["nextDeliveryAt"], datetime(2026, 11, 16, 20, 30, tzinfo=UTC))

    def test_collect_is_throttled(self):
        s = MemoryStore([])
        self.assertTrue(runner.run(s, NOW, fetch=fake_fetch)["collected"])
        self.assertFalse(runner.run(s, NOW + timedelta(minutes=20), fetch=fake_fetch)["collected"])
        self.assertTrue(runner.run(s, NOW + timedelta(minutes=config.COLLECT_EVERY_MIN + 1), fetch=fake_fetch)["collected"])

    def test_cleanup_once_a_day(self):
        s = MemoryStore([])
        runner.run(s, NOW, fetch=fake_fetch)
        runner.run(s, NOW + timedelta(hours=2), fetch=fake_fetch)
        self.assertEqual(len(s.cleaned), 1)
        runner.run(s, NOW + timedelta(hours=24), fetch=fake_fetch)
        self.assertEqual(len(s.cleaned), 2)

    def test_all_feeds_down_does_not_crash_and_user_still_advances(self):
        s = MemoryStore([user(lastEditionDate="2026-11-15")])
        runner.run(s, NOW - timedelta(days=1), fetch=failing_fetch)
        s.users["u1"]["nextDeliveryAt"] = datetime(2026, 11, 16, 7, 0, tzinfo=UTC)
        st = runner.run(s, datetime(2026, 11, 16, 6, 30, tzinfo=UTC), fetch=failing_fetch)
        self.assertEqual(st["delivered"], 0)
        self.assertEqual(s.users["u1"]["nextDeliveryAt"], datetime(2026, 11, 17, 7, 0, tzinfo=UTC))

    def test_bad_settings_of_one_user_do_not_block_others(self):
        s = MemoryStore([user("bad", deliveryTime="pas-une-heure"), user("ok")])
        st = runner.run(s, NOW, fetch=fake_fetch)
        self.assertEqual(st["delivered"], 1)
        self.assertIn(("ok", "2026-11-16"), s.editions)

    def test_late_target_across_midnight_uses_target_date(self):
        # livraison à 00:10 Paris, composée la veille à 22:50 UTC... → l'édition porte la date du jour visé
        s = MemoryStore([user(deliveryTime="00:10", lastEditionDate="2026-11-15")])
        t0 = datetime(2026, 11, 16, 22, 40, tzinfo=UTC)  # 23:40 Paris le 16
        runner.run(s, t0 - timedelta(hours=3), fetch=fake_fetch)
        s.editions.clear()
        st = runner.run(s, t0, fetch=fake_fetch)
        self.assertEqual(st["delivered"], 1)
        self.assertIn(("u1", "2026-11-17"), s.editions)

    def test_sig_ignores_order_of_custom_days(self):
        a = runner.schedule_sig({"deliveryCustomDays": [4, 0, 2]})
        b = runner.schedule_sig({"deliveryCustomDays": [0, 2, 4]})
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
