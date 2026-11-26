from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from aps_update.cloudflare import BOOK_ROUTE, is_book_route
from aps_update.ranges import Window, format_window

_COUNT_METRICS = (
    "postCount",
    "reactions",
    "comments",
    "impressions",
    "shares",
    "reposts",
    "clicks",
    "saves",
    "views",
    "follows",
)
def build_report(collections: list[dict], timezone_name: str, generated_at: datetime) -> dict:
    if not collections:
        raise ValueError("no collections")
    start = min(item["start"] for item in collections)
    end = max(item["end"] for item in collections)
    window = Window(date.fromisoformat(start), date.fromisoformat(end))
    gaps = _gaps(collections)
    traffic = _traffic(collections)
    traffic["book"] = book_summary(collections)
    socials = _socials(collections)
    inventory = _inventory(collections)
    releases: list[dict] = []
    seen: set[str] = set()
    for collection in collections:
        for release in collection["changelog"]["releases"]:
            if release["version"] in seen:
                continue
            seen.add(release["version"])
            releases.append(release)
    releases.sort(key=lambda release: release["date"])
    return {
        "id": window.id,
        "start": window.start.isoformat(),
        "end": window.end.isoformat(),
        "timezone": timezone_name,
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "collections": [item["id"] for item in collections],
        "collection_labels": [
            {"id": item["id"], "label": format_window(_window(item))} for item in collections
        ],
        "gaps": gaps,
        "changelog": releases,
        "inventory": inventory,
        "traffic": traffic,
        "socials": socials,
    }


def select_collections(collections: list[dict], after: str | None) -> list[dict]:
    if after is None:
        return list(collections)
    return [item for item in collections if item["start"] >= after]


def _window(collection: dict) -> Window:
    return Window(date.fromisoformat(collection["start"]), date.fromisoformat(collection["end"]))


def _gaps(collections: list[dict]) -> list[dict]:
    gaps = []
    ordered = sorted(collections, key=lambda item: item["start"])
    for previous, current in zip(ordered, ordered[1:]):
        if previous["end"] < current["start"]:
            gaps.append({"start": previous["end"], "end": current["start"]})
    return gaps


def _inventory(collections: list[dict]) -> dict | None:
    """Site size at the end of the period. These totals are not added across months."""
    latest = None
    for collection in collections:
        inventory = collection.get("inventory")
        if not inventory or inventory.get("events") is None or inventory.get("pages") is None:
            continue
        if latest is None or collection["end"] > latest["end"]:
            latest = collection
    if latest is None:
        return None
    inventory = latest["inventory"]
    return {
        "events": inventory["events"],
        "pages": inventory["pages"],
        "committed_at": inventory.get("committed_at"),
    }


def _traffic(collections: list[dict]) -> dict:
    requests = page_views = transferred = 0
    countries: dict[str, int] = defaultdict(int)
    pages: dict[str, int] = defaultdict(int)
    page_notes = []
    uniques = []
    for collection in collections:
        traffic = collection["traffic"]
        requests += traffic["requests"]
        page_views += traffic["page_views"]
        transferred += traffic["bytes"]
        uniques.append(
            {
                "id": collection["id"],
                "label": format_window(_window(collection)),
                "uniques": traffic["uniques"],
            }
        )
        for country in traffic["countries"]:
            countries[country["name"]] += country["requests"]
        for page in traffic["top_pages"]:
            pages[page["path"]] += page["requests"]
        if traffic.get("top_pages_note"):
            page_notes.append(f"{format_window(_window(collection))}: {traffic['top_pages_note']}")
    return {
        "requests": requests,
        "page_views": page_views,
        "bytes": transferred,
        "uniques": uniques[0]["uniques"] if len(uniques) == 1 else None,
        "uniques_by_collection": uniques,
        "countries": [
            {"name": name, "requests": count}
            for name, count in sorted(countries.items(), key=lambda item: item[1], reverse=True)[:8]
        ],
        "top_pages": [
            {"path": path, "requests": count}
            for path, count in sorted(pages.items(), key=lambda item: item[1], reverse=True)[:10]
        ],
        "top_pages_notes": page_notes,
    }


def book_summary(collections: list[dict]) -> dict:
    periods = []
    for collection in collections:
        requests, note = _book_count(collection)
        periods.append(
            {
                "id": collection["id"],
                "label": format_window(_window(collection)),
                "requests": requests,
                "note": note,
            }
        )
    known = [period["requests"] for period in periods]
    total = sum(known) if known and all(value is not None for value in known) else None
    return {
        "path": BOOK_ROUTE,
        "label": "Now There Was a Lady!",
        "requests": total,
        "periods": periods,
    }


def previous_with_book(previous: dict | None, collections: list[dict]) -> dict | None:
    """Fill the Hope Johnson comparison from saved collections when an older report lacks it."""
    if not previous:
        return None
    traffic = dict(previous.get("traffic") or {})
    if traffic.get("book"):
        return previous
    by_id = {item["id"]: item for item in collections}
    prior = [by_id[item_id] for item_id in previous.get("collections") or [] if item_id in by_id]
    if not prior:
        return previous
    traffic["book"] = book_summary(prior)
    return {**previous, "traffic": traffic}


def _book_count(collection: dict) -> tuple[int | None, str | None]:
    traffic = collection.get("traffic") or {}
    for route in traffic.get("routes") or []:
        if is_book_route(route.get("path") or ""):
            return route.get("requests"), route.get("note")
    for page in traffic.get("top_pages") or []:
        if is_book_route(page.get("path") or ""):
            return page.get("requests"), traffic.get("top_pages_note")
    if "top_pages" in traffic:
        return None, "This route was outside the saved top pages for this collection."
    return None, "This route was not collected."


def _socials(collections: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    unavailable: list[dict] = []
    for collection in collections:
        label = format_window(_window(collection))
        socials = collection["socials"]
        if not socials["available"]:
            unavailable.append({"label": label, "reason": socials["reason"]})
            continue
        for channel in socials["channels"]:
            current = grouped.setdefault(
                channel["service"],
                {
                    "service": channel["service"],
                    "name": channel["name"],
                    "metrics": {},
                    "reach_by_collection": [],
                    "rate_parts": [],
                    "missing": [],
                },
            )
            current["name"] = channel["name"]
            for key, metric in channel["metrics"].items():
                if key == "engagementRate":
                    impressions = (channel["metrics"].get("impressions") or {}).get("value")
                    current["rate_parts"].append((metric["value"], impressions))
                    continue
                if key == "reach":
                    current["reach_by_collection"].append({"label": label, "value": metric["value"]})
                    continue
                if key not in _COUNT_METRICS:
                    continue
                bucket = current["metrics"].setdefault(
                    key, {"name": metric["name"], "unit": metric["unit"], "value": 0}
                )
                bucket["value"] += metric["value"]
    if not grouped:
        return [
            {
                "service": None,
                "name": None,
                "metrics": {},
                "reach_by_collection": [],
                "engagement_rate": None,
                "missing": unavailable,
            }
        ]
    channels = []
    for channel in grouped.values():
        channel["missing"] = list(unavailable)
        parts = channel.pop("rate_parts")
        channel["engagement_rate"] = _combine_rate(parts, len(collections))
        if len(collections) == 1 and len(channel["reach_by_collection"]) == 1:
            channel["metrics"]["reach"] = {
                "name": "Reach",
                "unit": "count",
                "value": channel["reach_by_collection"][0]["value"],
            }
        channels.append(channel)
    channels.sort(key=lambda channel: channel["service"] or "")
    return channels


def _combine_rate(parts: list[tuple], collection_count: int) -> float | None:
    if not parts or len(parts) != collection_count:
        return None
    if collection_count == 1:
        return parts[0][0]
    if any(impressions is None for _, impressions in parts):
        return None
    total = sum(impressions for _, impressions in parts)
    if not total:
        return None
    return sum(rate * impressions for rate, impressions in parts) / total


def comparison_totals(report: dict) -> dict:
    socials = {}
    for channel in report["socials"]:
        if not channel.get("service"):
            continue
        metrics = {key: metric["value"] for key, metric in channel["metrics"].items()}
        metrics["engagementRate"] = channel.get("engagement_rate")
        socials[channel["service"]] = {"name": channel["name"], "metrics": metrics}
    return {
        "id": report["id"],
        "start": report["start"],
        "end": report["end"],
        "timezone": report["timezone"],
        "generated_at": report["generated_at"],
        "collections": report["collections"],
        "inventory": report.get("inventory"),
        "traffic": {
            "requests": report["traffic"]["requests"],
            "page_views": report["traffic"]["page_views"],
            "bytes": report["traffic"]["bytes"],
            "uniques": report["traffic"]["uniques"],
            "book": report["traffic"].get("book"),
        },
        "socials": socials,
    }
