import unittest
from datetime import date

from aps_update.changelog import clean_bullet, parse_changelog
from aps_update.ranges import Window


CHANGELOG = """
# Changelog

## [Unreleased]

## [1.222.0](https://example.com/1.222.0) (2026-10-30)

### Features

* event registration deadlines ([67513b9](https://example.com/commit)), closes [#266](https://example.com/issues/266)
* event registration deadlines ([67513b9](https://example.com/commit)), closes [#266](https://example.com/issues/266)

### Content

* additional october events ([06dd714](https://example.com/commit))

### [1.219.2](https://example.com/1.219.2) (2026-10-10)

## [1.209.0](https://example.com/1.209.0) (2026-08-16)

### Features

* october talk ([1570aba](https://example.com/commit))
"""


class ChangelogTests(unittest.TestCase):
    def test_clean_bullet_drops_commit_links_and_keeps_issues(self):
        text = "event registration deadlines ([67513b9](https://example.com)), closes [#266](https://example.com)"
        self.assertEqual(clean_bullet(text), "event registration deadlines, closes #266")

    def test_parse_keeps_releases_inside_the_window(self):
        releases = parse_changelog(CHANGELOG, Window(date(2026, 10, 1), date(2026, 11, 1)))
        self.assertEqual([release["version"] for release in releases], ["1.222.0"])
        self.assertEqual(
            releases[0]["sections"]["Features"],
            ["event registration deadlines, closes #266"],
        )
        self.assertNotIn("1.219.2", [release["version"] for release in releases])


if __name__ == "__main__":
    unittest.main()
