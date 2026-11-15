from __future__ import annotations

from urllib.parse import quote
from zoneinfo import ZoneInfo

from aps_update.http_json import get_json
from aps_update.ranges import Window, utc_stamp


def count_inventory(paths: list[str]) -> dict[str, int]:
    """Calendar entries, and pages a visitor can open.

    An event page is counted as an event, not again as a page. Fossil Friday
    entries each have their own page, so they are included in the page count.
    """
    events = 0
    static_pages = 0
    fossil_friday_pages = 0
    for path in paths:
        if path.startswith("src/content/events/") and path.endswith((".md", ".mdx")):
            events += 1
        elif path.startswith("src/content/fossilFriday/") and path.endswith((".md", ".mdx")):
            fossil_friday_pages += 1
        elif _is_static_page(path):
            static_pages += 1
    return {
        "events": events,
        "pages": static_pages + fossil_friday_pages,
        "static_pages": static_pages,
        "fossil_friday_pages": fossil_friday_pages,
    }


def fetch_inventory(repo: str, window: Window, tz: ZoneInfo) -> dict:
    slug = _github_slug(repo)
    until = quote(utc_stamp(window.end, tz), safe="")
    commits = get_json(f"https://api.github.com/repos/{slug}/commits?sha=main&until={until}&per_page=1")
    if not commits:
        raise RuntimeError(f"No commits on main before {window.end.isoformat()}")
    commit = commits[0]
    sha = commit["sha"]
    tree = get_json(f"https://api.github.com/repos/{slug}/git/trees/{sha}?recursive=1")
    if tree.get("truncated"):
        raise RuntimeError("The website file list was truncated, so the page and event counts would be short.")
    paths = [item["path"] for item in tree.get("tree", []) if item.get("type") == "blob"]
    counts = count_inventory(paths)
    counts["commit"] = sha
    counts["committed_at"] = commit["commit"]["committer"]["date"]
    return counts


def _is_static_page(path: str) -> bool:
    if not path.startswith("src/pages/") or not path.endswith(".astro"):
        return False
    if path.startswith("src/pages/api/"):
        return False
    name = path.rsplit("/", 1)[-1]
    if name == "404.astro" or "[" in name:
        return False
    return True


def _github_slug(repo: str) -> str:
    slug = repo.strip().rstrip("/")
    if slug.endswith(".git"):
        slug = slug[:-4]
    prefix = "https://github.com/"
    if not slug.startswith(prefix):
        raise RuntimeError(f"WEBSITE_GIT_REPO must be a GitHub URL, got {repo!r}")
    return slug[len(prefix) :]
