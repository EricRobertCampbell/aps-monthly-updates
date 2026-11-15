import unittest
from datetime import datetime

from aps_update.aggregate import build_report
from aps_update.render import render
from aps_update.site_inventory import count_inventory


class InventoryCountTests(unittest.TestCase):
    def test_counts_calendar_entries_and_visitor_pages(self):
        counts = count_inventory(
            [
                "src/content/events/2026-11-20-monthlyMeeting.md",
                "src/content/events/notes.txt",
                "src/content/fossilFriday/2026-05-01.md",
                "src/pages/index.astro",
                "src/pages/events/index.astro",
                "src/pages/404.astro",
                "src/pages/api/events.ts",
                "src/pages/events/stable/[slug].astro",
                "src/pages/resources/fossilfriday/[date].astro",
                "src/pages/interstitial/20251121.astro",
            ]
        )
        self.assertEqual(counts["events"], 1)
        self.assertEqual(counts["static_pages"], 3)
        self.assertEqual(counts["fossil_friday_pages"], 1)
        self.assertEqual(counts["pages"], 4)


class InventoryReportTests(unittest.TestCase):
    def test_report_uses_the_site_at_the_end_of_the_period(self):
        early = _collection("2026-05-01", "2026-06-01", events=100, pages=40)
        late = _collection("2026-06-01", "2026-07-01", events=112, pages=43)
        report = build_report([early, late], "America/Edmonton", datetime(2026, 7, 1, 12, 0))
        self.assertEqual(report["inventory"], {"events": 112, "pages": 43, "committed_at": "2026-06-30T00:00:00Z"})
        text = render(report, {"inventory": {"events": 100, "pages": 40}, "start": "2026-04-01", "end": "2026-05-01"})
        self.assertIn("| Events | 112 | 100 | +12 (+12%) |", text)
        self.assertIn("| Pages | 43 | 40 | +3 (+8%) |", text)


def _collection(start: str, end: str, *, events: int, pages: int) -> dict:
    return {
        "id": f"{start}_{end}",
        "start": start,
        "end": end,
        "timezone": "America/Edmonton",
        "changelog": {"releases": []},
        "inventory": {"events": events, "pages": pages, "committed_at": "2026-06-30T00:00:00Z"},
        "traffic": {
            "requests": 1,
            "page_views": 1,
            "bytes": 1,
            "uniques": 1,
            "countries": [],
            "top_pages": [],
            "top_pages_note": None,
        },
        "socials": {"available": False, "reason": "none", "channels": []},
    }


if __name__ == "__main__":
    unittest.main()
