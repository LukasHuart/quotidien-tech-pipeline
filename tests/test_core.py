import unittest
from datetime import datetime, timedelta, timezone

from quotidien import dedupe, edition, feeds, timeutil, topics

UTC = timezone.utc
NOW = datetime(2026, 11, 16, 6, 0, tzinfo=UTC)
SRC = {"id": "ex", "name": "Exemple", "weight": 1.0}

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel><title>Exemple</title>
<item><title>Mirrorless camera adds a faster sensor</title>
<link>https://exemple.test/camera/?utm_source=rss#top</link>
<pubDate>Mon, 16 Nov 2026 05:30:00 +0000</pubDate>
<description>&lt;p&gt;The new &lt;b&gt;mirrorless&lt;/b&gt; body promises faster readout. &lt;img src="https://exemple.test/i/cam.jpg"&gt;&lt;/p&gt;</description>
<category>Photography</category></item>
<item><title>Chip startup raises funding</title><link>https://exemple.test/chip</link>
<pubDate>Sun, 15 Nov 2026 20:00:00 +0000</pubDate><description>Plain text.</description>
<media:thumbnail url="https://exemple.test/i/chip.png"/></item>
<item><title></title><link>https://exemple.test/vide</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Exemple</title>
<entry><title>Kernel 7.0 released</title><link rel="alternate" href="https://exemple.test/kernel"/>
<updated>2026-11-16T04:00:00Z</updated><summary>Linux gets a big update.</summary>
<category term="Linux"/></entry></feed>"""


def art(i, title, excerpt="", src="a", published=None, **kw):
    d = {"id": f"id{i}", "url": f"https://exemple.test/{i}", "title": title, "excerpt": excerpt, "categories": [], "source_id": src,
         "source": src.upper(), "weight": 1.0, "published": published or NOW - timedelta(hours=2),
         "image": None, "mentions": 1, "words": None, "topics": []}
    d.update(kw)
    return d


class Feeds(unittest.TestCase):
    def test_normalize_url(self):
        self.assertEqual(feeds.normalize_url("HTTPS://Exemple.test/a/?utm_source=x&id=2#frag"),
                         "https://exemple.test/a?id=2")

    def test_rss(self):
        items = feeds.parse_feed(RSS, SRC, NOW)
        self.assertEqual(len(items), 2)  # l'item sans titre est ignoré
        cam = items[0]
        self.assertEqual(cam["url"], "https://exemple.test/camera")
        self.assertEqual(cam["image"], "https://exemple.test/i/cam.jpg")
        self.assertNotIn("<", cam["excerpt"])
        self.assertEqual(cam["categories"], ["Photography"])
        self.assertEqual(cam["published"], datetime(2026, 11, 16, 5, 30, tzinfo=UTC))
        self.assertEqual(items[1]["image"], "https://exemple.test/i/chip.png")

    def test_atom(self):
        (k,) = feeds.parse_feed(ATOM, SRC, NOW)
        self.assertEqual(k["url"], "https://exemple.test/kernel")
        self.assertEqual(k["published"], datetime(2026, 11, 16, 4, 0, tzinfo=UTC))

    def test_truncate(self):
        t = feeds.truncate("mot " * 200, 50)
        self.assertLessEqual(len(t), 51)
        self.assertTrue(t.endswith("…"))

    def test_collect_survives_a_broken_feed(self):
        def fake(url):
            if "bad" in url:
                raise OSError("panne")
            return RSS
        items, errors = feeds.collect_all(
            [{"id": "ok", "name": "OK", "url": "https://ok.test/f"},
             {"id": "bad", "name": "Bad", "url": "https://bad.test/f"}], NOW, fetch=fake)
        self.assertEqual(len(items), 2)
        self.assertEqual(len(errors), 1)


class Dedupe(unittest.TestCase):
    def test_same_story_two_sources(self):
        a = art(1, "Google patches critical Chrome zero-day flaw", src="verge")
        b = art(2, "Critical Chrome zero-day patched by Google", src="ars")
        c = art(3, "Camera maker unveils new lens", src="verge")
        create, update = dedupe.merge_batches([], [a, b, c])
        self.assertEqual(len(create), 2)
        story = next(x for x in create if "Chrome" in x["title"])
        self.assertEqual(story["mentions"], 2)

    def test_existing_story_is_updated_not_duplicated(self):
        old = art(1, "Google patches critical Chrome zero-day flaw", src="verge", mentions=1, sources=["verge"])
        new = art(2, "Critical Chrome zero-day patched by Google", src="ars")
        create, update = dedupe.merge_batches([old], [new])
        self.assertEqual(create, [])
        self.assertEqual(update, [{"id": "id1", "mentions": 2, "sources": ["ars", "verge"]}])

    def test_rerun_is_idempotent(self):
        old = art(1, "Google patches critical Chrome zero-day flaw", src="verge", mentions=1, sources=["verge"])
        again = art(1, "Google patches critical Chrome zero-day flaw", src="verge")
        self.assertEqual(dedupe.merge_batches([old], [again]), ([], []))


class Topics(unittest.TestCase):
    def test_ai_is_case_sensitive_and_word_bounded(self):
        a = art(1, "He said the mail arrived", "A story about a train.")
        self.assertEqual(topics.strength(a, ["AI"]), 0)
        b = art(2, "New AI model released")
        self.assertGreater(topics.strength(b, ["AI"]), 0)

    def test_tag(self):
        a = topics.tag(art(1, "Android update brings new battery controls", "The Android release..."))
        self.assertEqual(a["topics"][0], "mobile")

    def test_plural_and_phrase(self):
        a = art(1, "Photographers love the new lenses")
        self.assertGreater(topics.strength(a, ["photographer", "lens"]), 0)

    def test_resolve_custom_topic(self):
        r = topics.resolve_user_topics([
            {"id": "ia"}, {"id": "custom:astro", "label": "Astrophotographie", "keywords": ["astrophotography"]},
            {"id": "inconnu"}])
        self.assertEqual([t["id"] for t in r], ["ia", "custom:astro"])


class Edition(unittest.TestCase):
    def setUp(self):
        self.arts = [
            art(1, "AI model beats benchmark", src="a", mentions=3),
            art(2, "Another AI breakthrough announced", src="a"),
            art(3, "Third AI story of the day", src="a"),
            art(4, "Fourth AI story of the day", src="a"),
            art(5, "Mirrorless camera with new sensor", src="b"),
            art(6, "Quarterly results for a chipmaker", src="c"),
            art(7, "Old AI story", src="d", published=NOW - timedelta(hours=60)),
        ]

    def test_coverage_cap_and_age(self):
        ed = edition.build_edition([{"id": "ia"}, {"id": "photo"}], self.arts, set(), NOW)
        ids = ed["articleIds"]
        self.assertIn("id5", ids)            # le thème « photo » est couvert malgré 4 articles IA
        self.assertNotIn("id7", ids)         # trop ancien
        self.assertLessEqual(ids.count("id1") + ids.count("id2") + ids.count("id3") + ids.count("id4"), 3)  # max 3/source
        self.assertEqual(ed["une"]["id"], ids[0])
        self.assertEqual(ed["date"], "2026-11-16")

    def test_seen_articles_are_skipped(self):
        ed = edition.build_edition([{"id": "ia"}], self.arts, {"id1", "id2"}, NOW)
        self.assertNotIn("id1", ed["articleIds"])

    def test_no_topics_still_works_and_empty_returns_none(self):
        self.assertIsNotNone(edition.build_edition([], self.arts, set(), NOW))
        self.assertIsNone(edition.build_edition([], [], set(), NOW))

    def test_layout_sizes(self):
        many = [art(i, f"Story number {i} about thing{i}", src=f"s{i}") for i in range(30)]
        ed = edition.build_edition([], many, set(), NOW)
        self.assertEqual((1 + len(ed["more"]) + len(ed["brefs"])), 12)
        self.assertEqual(len(ed["more"]), 4)
        self.assertNotIn("excerpt", ed["brefs"][0])


class Delivery(unittest.TestCase):
    def test_daily_with_dst_change(self):
        # Paris passe à l'heure d'été le 29/03/2026 : 08:00 locale = 06:00 UTC ensuite (07:00 UTC avant)
        n = timeutil.next_delivery_utc(datetime(2026, 3, 28, 7, 0, 1, tzinfo=UTC), "Europe/Paris", "08:00")
        self.assertEqual(n, datetime(2026, 3, 29, 6, 0, tzinfo=UTC))

    def test_strictly_after(self):
        n = timeutil.next_delivery_utc(datetime(2026, 11, 16, 7, 0, tzinfo=UTC), "Europe/Paris", "08:00")
        self.assertEqual(n, datetime(2026, 11, 17, 7, 0, tzinfo=UTC))

    def test_weekdays_only_skips_weekend(self):
        # samedi 14/11/2026 -> lundi 16/11/2026
        n = timeutil.next_delivery_utc(datetime(2026, 11, 14, 8, 0, tzinfo=UTC), "Europe/Paris", "08:00", "weekdays")
        self.assertEqual(n, datetime(2026, 11, 16, 7, 0, tzinfo=UTC))

    def test_other_timezone(self):
        n = timeutil.next_delivery_utc(datetime(2026, 11, 16, 0, 0, tzinfo=UTC), "America/Montreal", "08:00")
        self.assertEqual(n, datetime(2026, 11, 16, 13, 0, tzinfo=UTC))

    def test_nonexistent_local_time_does_not_crash(self):
        timeutil.next_delivery_utc(datetime(2026, 3, 28, 12, 0, tzinfo=UTC), "Europe/Paris", "02:30")


if __name__ == "__main__":
    unittest.main()
