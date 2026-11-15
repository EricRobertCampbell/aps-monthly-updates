from __future__ import annotations

import re

from aps_update.http_json import get_text
from aps_update.ranges import Window

_VERSION = re.compile(
    r"^#{2,3} \[(?P<version>[^\]]+)\]\((?P<url>[^)]+)\) \((?P<date>\d{4}-\d{2}-\d{2})\)\s*$"
)
_SECTION = re.compile(r"^### (?P<section>[A-Za-z][^[\]]*?)\s*$")
_BULLET = re.compile(r"^[\*\-] (?P<text>.+)$")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")


def changelog_url(repo: str) -> str:
    slug = repo.strip().rstrip("/")
    if slug.endswith(".git"):
        slug = slug[:-4]
    prefix = "https://github.com/"
    if not slug.startswith(prefix):
        raise RuntimeError(f"WEBSITE_GIT_REPO must be a GitHub URL, got {repo!r}")
    return f"https://raw.githubusercontent.com/{slug[len(prefix):]}/main/CHANGELOG.md"


def clean_bullet(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        label = match.group(1)
        return "" if _COMMIT.fullmatch(label) else label

    text = _LINK.sub(replace, text)
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" ,")


def parse_changelog(markdown: str, window: Window) -> list[dict]:
    releases: list[dict] = []
    current: dict | None = None
    section: str | None = None

    def finish() -> None:
        nonlocal current, section
        if current and current["sections"]:
            releases.append(current)
        current = None
        section = None

    for line in markdown.splitlines():
        version = _VERSION.match(line)
        if version:
            finish()
            released = version.group("date")
            if window.start.isoformat() <= released < window.end.isoformat():
                current = {
                    "version": version.group("version"),
                    "date": released,
                    "url": version.group("url"),
                    "sections": {},
                }
            continue
        if current is None:
            continue
        heading = _SECTION.match(line)
        if heading:
            section = heading.group("section").strip()
            continue
        bullet = _BULLET.match(line)
        if bullet and section:
            text = clean_bullet(bullet.group("text"))
            if not text:
                continue
            items: list[str] = current["sections"].setdefault(section, [])
            if text not in items:
                items.append(text)
    finish()
    return releases


def fetch_changelog(repo: str, window: Window) -> dict:
    markdown = get_text(changelog_url(repo))
    return {"releases": parse_changelog(markdown, window)}
