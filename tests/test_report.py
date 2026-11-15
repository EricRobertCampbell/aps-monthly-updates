import unittest
from datetime import date, datetime

from aps_update.aggregate import build_report, select_collections
from aps_update.ranges import Window, default_window, split_for_storage
from aps_update.render import render


def collection(start, end, *, requests, uniques, posts, socials=True):
    return {
        "id": f"{start}_{end}",
        "start": start,
        "end": end,
        "timezone": "America/Edmonton",
        "changelog": {
            "releases": [
                {
                    "version": f"v{start}",
                    "date": start,
                    "url": "https://example.com",
                    "sections": {"Features": [f"change {start}"]},
                }
            ]
        },
        "traffic": {
            "requests": requests,
            "page_views": requests // 5,
            "bytes": requests * 1000,
            "uniques": uniques,
            "countries": [{"name": "Canada", "requests": requests}],
            "top_pages": [{"path": "/", "requests": requests // 2}],
            "top_pages_note": None,
        },
        "socials": {
            "available": socials,
            "reason": None if socials else "Buffer insights were outside the 31-day history.",
            "channels": []
            if not socials
            else [
                {
                    "id": "facebook",
                    "service": "facebook",
                    "name": "Alberta Palaeontological Society",
                    "metrics": {
                        "postCount": {"name": "Posts", "value": posts, "unit": "count"},
                        "reactions": {"name": "Reactions", "value": posts * 10, "unit": "count"},
                        "impressions": {"name": "Impressions", "value": posts * 100, "unit": "count"},
                        "engagementRate": {"name": "Eng. Rate", "value": 5.0, "unit": "percentage"},
                        "reach": {"name": "Reach", "value": posts * 80, "unit": "count"},
                    },
                    "posts": [
                        {
                            "id": f"post-{start}",
                            "text": f"Post from {start}",
                            "sent_on": start,
                            "url": None,
                            "reactions": posts * 10,
                            "comments": 1,
                        }
                    ],
                }
            ],
        },
    }


class RangeTests(unittest.TestCase):
    def test_first_collect_is_thirty_days_through_yesterday(self):
        window = default_window(date(2026, 11, 15), None)
        self.assertEqual(window, Window(date(2026, 10, 16), date(2026, 11, 15)))

    def test_long_gap_splits_on_calendar_months(self):
        chunks = split_for_storage(Window(date(2026, 5, 1), date(2026, 7, 15)))
        self.assertEqual(
            [(chunk.start, chunk.end) for chunk in chunks],
            [
                (date(2026, 5, 1), date(2026, 6, 1)),
                (date(2026, 6, 1), date(2026, 7, 1)),
                (date(2026, 7, 1), date(2026, 7, 15)),
            ],
        )


class ReportTests(unittest.TestCase):
    def test_report_includes_every_collection_since_the_last_delivered_one(self):
        may = collection("2026-05-01", "2026-06-01", requests=100, uniques=40, posts=2, socials=False)
        june = collection("2026-06-01", "2026-07-01", requests=200, uniques=50, posts=3, socials=False)
        july = collection("2026-07-01", "2026-07-15", requests=80, uniques=20, posts=1, socials=True)
        selected = select_collections([may, june, july], "2026-06-01")
        self.assertEqual([item["id"] for item in selected], [june["id"], july["id"]])

        report = build_report([may, june, july], "America/Edmonton", datetime(2026, 7, 15, 12, 0))
        self.assertEqual(report["traffic"]["requests"], 380)
        self.assertIsNone(report["traffic"]["uniques"])
        self.assertEqual(len(report["traffic"]["uniques_by_collection"]), 3)
        facebook = report["socials"][0]
        self.assertEqual(facebook["metrics"]["reactions"]["value"], 10)
        self.assertEqual(len(facebook["missing"]), 2)
        self.assertIsNone(facebook["metrics"].get("reach"))

        text = render(report, None)
        self.assertIn("# Report", text)
        self.assertIn("## Website", text)
        self.assertIn("## Socials", text)
        self.assertIn("## Field Trips", text)
        self.assertTrue(text.endswith("## Field Trips\n"))
        self.assertIn("change 2026-05-01", text)
        self.assertIn("not added together", text)
        self.assertIn("No earlier report has been finalized", text)


if __name__ == "__main__":
    unittest.main()
