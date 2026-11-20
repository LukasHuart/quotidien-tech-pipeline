import unittest
from datetime import datetime, timedelta, timezone

from quotidien import edition, feeds, scoring

UTC = timezone.utc
NOW = datetime(2026, 11, 16, 6, 0, tzinfo=UTC)


def art(i, title, **kw):
    d = {"id": f"id{i}", "url": f"https://exemple.test/{i}", "title": title, "excerpt": "", "categories": [],
         "source_id": f"s{i}", "source": "S", "weight": 1.0, "published": NOW - timedelta(hours=2),
         "image": None, "mentions": 1, "words": None, "topics": []}
    d.update(kw)
    return d


class Promo(unittest.TestCase):
    def test_detects_promo_pages(self):
        for t in ["Adorama Camera Coupon Codes & Promo Codes: November 2026",
                  "Best Black Friday camera deals right now",
                  "Save 30% off the new headphones",
                  "Apple discount codes for students"]:
            self.assertTrue(scoring.is_promo(art(1, t)), t)

    def test_keeps_real_news(self):
        for t in ["Microsoft strikes deal to buy a chipmaker",
                  "Google rolls out AI homepage redesign with Gemini chats",
                  "Linux kernel 7.0 released"]:
            self.assertFalse(scoring.is_promo(art(1, t)), t)

    def test_category_deals(self):
        self.assertTrue(scoring.is_promo(art(1, "Nice laptop", categories=["Deals"])))

    def test_promo_never_in_edition(self):
        arts = [art(1, "Adorama Coupon Codes: November 2026", mentions=4), art(2, "Kernel 7.0 released")]
        ed = edition.build_edition([], arts, set(), NOW)
        self.assertEqual(ed["articleIds"], ["id2"])


class Truncate(unittest.TestCase):
    def test_cuts_at_sentence_end(self):
        s = "First sentence is here. Second sentence is also here. Third one goes on and on and on forever."
        out = feeds.truncate(s, 60)
        self.assertEqual(out, "First sentence is here. Second sentence is also here.")

    def test_falls_back_to_word_cut(self):
        out = feeds.truncate("mot " * 200, 50)
        self.assertTrue(out.endswith("…"))
        self.assertLessEqual(len(out), 51)

    def test_short_text_untouched(self):
        self.assertEqual(feeds.truncate("Short.", 50), "Short.")


if __name__ == "__main__":
    unittest.main()
