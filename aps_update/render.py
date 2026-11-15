from __future__ import annotations

from datetime import date
from urllib.parse import unquote

from aps_update.ranges import Window, format_day, format_window

_SERVICE_LABELS = {
    "facebook": "Facebook",
    "instagram": "Instagram",
    "mastodon": "Mastodon",
}
_METRIC_ORDER = (
    "postCount",
    "reactions",
    "comments",
    "impressions",
    "reach",
    "shares",
    "reposts",
    "clicks",
    "saves",
    "views",
    "follows",
)


def render(report: dict, previous: dict | None) -> str:
    window = Window(date.fromisoformat(report["start"]), date.fromisoformat(report["end"]))
    lines = ["# Report", "", _intro(window, report, previous), "", "## Website", ""]
    lines.extend(_changes(report["changelog"]))
    if report.get("inventory"):
        lines.extend(["", "### Site", ""])
        lines.extend(_site(report["inventory"], previous))
    lines.extend(["", "### Traffic", ""])
    lines.extend(_traffic(report["traffic"], previous))
    lines.extend(["", "## Socials", ""])
    lines.extend(_socials(report["socials"], previous))
    lines.extend(["", "## Field Trips", ""])
    return "\n".join(lines).rstrip() + "\n"


def _intro(window: Window, report: dict, previous: dict | None) -> str:
    parts = [format_window(window) + "."]
    labels = [item["label"] for item in report["collection_labels"]]
    if len(labels) > 1:
        parts.append("Collected as " + _join(labels) + ".")
    for gap in report["gaps"]:
        missing = Window(date.fromisoformat(gap["start"]), date.fromisoformat(gap["end"]))
        parts.append(f"No collection was saved for {format_window(missing)}.")
    if previous:
        prior = Window(date.fromisoformat(previous["start"]), date.fromisoformat(previous["end"]))
        parts.append(f"Compared with {format_window(prior)}.")
    else:
        parts.append("No earlier report has been finalized, so there is no comparison.")
    return " ".join(parts)


def _changes(releases: list[dict]) -> list[str]:
    lines = ["### Changes", ""]
    if not releases:
        lines.append("No website releases in this period.")
        return lines
    for release in releases:
        lines.append(f"#### {release['version']} ({format_day(date.fromisoformat(release['date']))})")
        lines.append("")
        for section, items in release["sections"].items():
            for item in items:
                lines.append(f"- **{section}:** {item}")
        lines.append("")
    return lines[:-1] if lines[-1] == "" else lines


def _site(inventory: dict, previous: dict | None) -> list[str]:
    prior = (previous or {}).get("inventory") or {}
    compared = previous is not None
    rows = [
        _count_row("Events", inventory["events"], prior.get("events"), compared=compared),
        _count_row("Pages", inventory["pages"], prior.get("pages"), compared=compared),
    ]
    headers = ["Metric", "This period", "Previous period", "Change"] if compared else ["Metric", "This period"]
    return [
        "Events are entries on the calendar. Pages are the site's own pages, including each Fossil Friday, "
        "and not those calendar entries. Both are the site at the end of this period.",
        "",
        _table(headers, rows),
    ]


def _traffic(traffic: dict, previous: dict | None) -> list[str]:
    prior = (previous or {}).get("traffic") or {}
    compared = previous is not None
    rows = [
        _count_row("Requests", traffic["requests"], prior.get("requests"), compared=compared),
        _count_row("Page views", traffic["page_views"], prior.get("page_views"), compared=compared),
        _bytes_row(traffic["bytes"], prior.get("bytes"), compared=compared),
    ]
    if traffic["uniques"] is not None and (not compared or prior.get("uniques") is not None):
        rows.append(
            _count_row(
                "Unique visitors",
                traffic["uniques"],
                prior.get("uniques"),
                compared=compared,
            )
        )
    lines = [
        "Requests count every file Cloudflare served, including images, scripts, and automated clients. "
        "Page views are successful HTML responses. Unique visitors are distinct client addresses "
        "for one collection window, not confirmed people.",
        "",
        _table(["Metric", "This period", "Previous period", "Change"] if previous else ["Metric", "This period"], rows),
    ]
    if traffic["uniques"] is None:
        lines.extend(["", "Unique visitors are counted inside each collection and are not added together.", ""])
        lines.append(
            _table(
                ["Collection", "Unique visitors"],
                [[item["label"], _integer(item["uniques"])] for item in traffic["uniques_by_collection"]],
            )
        )
    if traffic["top_pages"]:
        lines.extend(["", "#### Top pages", ""])
        if traffic["top_pages_notes"]:
            lines.extend(traffic["top_pages_notes"])
            lines.append("")
        lines.append(
            _table(
                ["Page", "Requests"],
                [[_page(page["path"]), _integer(page["requests"])] for page in traffic["top_pages"]],
            )
        )
        lines.extend(
            [
                "",
                "These are requests for the page, so a single visit can count more than once.",
            ]
        )
        if len(traffic["uniques_by_collection"]) > 1:
            lines.append("Each collection keeps its busiest pages, and this list adds those.")
    if traffic["countries"]:
        lines.extend(["", "#### Countries", ""])
        lines.append(
            _table(
                ["Country", "Requests"],
                [[_country(country["name"]), _integer(country["requests"])] for country in traffic["countries"]],
            )
        )
    return lines


def _socials(channels: list[dict], previous: dict | None) -> list[str]:
    prior_channels = (previous or {}).get("socials") or {}
    if len(channels) == 1 and channels[0]["service"] is None:
        reason = channels[0]["missing"][0]["reason"] if channels[0]["missing"] else "Social metrics were not collected."
        return [reason]
    lines: list[str] = []
    for channel in channels:
        if lines:
            lines.append("")
        label = _SERVICE_LABELS.get(channel["service"], channel["service"].title())
        lines.append(f"### {label}")
        lines.append("")
        lines.append(channel["name"])
        lines.append("")
        for missing in channel["missing"]:
            lines.append(f"{missing['label']}: {missing['reason']}")
            lines.append("")
        prior = (prior_channels.get(channel["service"]) or {}).get("metrics") or {}
        rows = []
        for key in _METRIC_ORDER:
            metric = channel["metrics"].get(key)
            if not metric or metric["value"] is None:
                continue
            rows.append(_count_row(metric["name"], metric["value"], prior.get(key), compared=previous is not None))
        if channel["engagement_rate"] is not None:
            rows.append(
                _rate_row(
                    "Engagement rate",
                    channel["engagement_rate"],
                    prior.get("engagementRate"),
                    compared=previous is not None,
                )
            )
        if rows:
            headers = ["Metric", "This period", "Previous period", "Change"] if previous else ["Metric", "This period"]
            lines.append(_table(headers, rows))
        reach_rows = channel["reach_by_collection"]
        if len(reach_rows) > 1:
            lines.extend(
                [
                    "",
                    "Reach is not added across collections, because the same person can be counted in each one.",
                    "",
                    _table(["Collection", "Reach"], [[item["label"], _integer(item["value"])] for item in reach_rows]),
                ]
            )
        if channel["posts"]:
            lines.extend(["", "#### Posts with the most reactions", ""])
            for post in channel["posts"]:
                text = post["text"] or "(no text)"
                if len(text) > 180:
                    text = text[:177].rstrip() + "..."
                when = format_day(date.fromisoformat(post["sent_on"])) if post.get("sent_on") else "Undated"
                detail = (
                    f"{when}: {text} — {_integer(post['reactions'])} {_noun(post['reactions'], 'reaction')}, "
                    f"{_integer(post['comments'])} {_noun(post['comments'], 'comment')}"
                )
                if post.get("url"):
                    lines.append(f"- [{detail}]({post['url']})")
                else:
                    lines.append(f"- {detail}")
    if not lines:
        return ["No social metrics in this period."]
    return lines


def _count_row(label: str, current: float, previous: float | None, *, compared: bool) -> list[str]:
    current_text = _integer(current)
    if not compared:
        return [label, current_text]
    if previous is None:
        return [label, current_text, "—", "—"]
    return [label, current_text, _integer(previous), _delta(current, previous, _integer)]


def _bytes_row(current: float, previous: float | None, *, compared: bool) -> list[str]:
    if not compared:
        return ["Data transfer", _bytes(current)]
    if previous is None:
        return ["Data transfer", _bytes(current), "—", "—"]
    return ["Data transfer", _bytes(current), _bytes(previous), _delta(current, previous, _bytes)]


def _rate_row(label: str, current: float, previous: float | None, *, compared: bool) -> list[str]:
    current_text = _percent(current)
    if not compared:
        return [label, current_text]
    if previous is None:
        return [label, current_text, "—", "—"]
    delta = current - previous
    sign = "+" if delta > 0 else ""
    return [label, current_text, _percent(previous), f"{sign}{delta:.1f} pp"]


def _delta(current: float, previous: float, render_amount) -> str:
    diff = current - previous
    sign = "+" if diff > 0 else ""
    amount = render_amount(abs(diff))
    if diff < 0:
        amount = f"-{amount}"
    else:
        amount = f"{sign}{amount}"
    if previous == 0:
        return amount
    percent = diff / previous * 100
    percent_sign = "+" if percent > 0 else ""
    return f"{amount} ({percent_sign}{percent:.0f}%)"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    clean = [[_cell(value) for value in row] for row in rows]
    head = "| " + " | ".join(headers) + " |"
    rule = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(row) + " |" for row in clean]
    return "\n".join([head, rule, *body])


def _cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _integer(value: float) -> str:
    return f"{int(round(value)):,}"


def _percent(value: float) -> str:
    return f"{value:.1f}%"


def _bytes(value: float) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f} GB"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} MB"
    return f"{value / 1_000:.1f} KB"


def _noun(value: float, word: str) -> str:
    return word if int(round(value)) == 1 else f"{word}s"


def _page(path: str) -> str:
    return unquote(path)


def _country(code: str) -> str:
    names = {
        "AT": "Austria",
        "AU": "Australia",
        "BE": "Belgium",
        "BR": "Brazil",
        "CA": "Canada",
        "CH": "Switzerland",
        "CN": "China",
        "DE": "Germany",
        "DK": "Denmark",
        "ES": "Spain",
        "FI": "Finland",
        "FR": "France",
        "GB": "United Kingdom",
        "HK": "Hong Kong",
        "IE": "Ireland",
        "IL": "Israel",
        "IN": "India",
        "IT": "Italy",
        "JP": "Japan",
        "KR": "South Korea",
        "MX": "Mexico",
        "NL": "Netherlands",
        "NO": "Norway",
        "NZ": "New Zealand",
        "PL": "Poland",
        "PT": "Portugal",
        "SE": "Sweden",
        "SG": "Singapore",
        "US": "United States",
        "ZA": "South Africa",
    }
    return names.get(code, code)


def _join(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"
