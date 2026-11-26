from __future__ import annotations

from collections import defaultdict
from urllib.parse import quote, unquote
from datetime import date

from aps_update.config import Config
from aps_update.http_json import post_json
from aps_update.ranges import Window, covers_retention, slice_days, utc_stamp

_ENDPOINT = "https://api.cloudflare.com/client/v4/graphql"
BOOK_ROUTE = "/openSourcePublications/Now There Was a Lady.pdf"
_STATIC_SUFFIXES = (
    ".css",
    ".js",
    ".mjs",
    ".map",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".xml",
    ".txt",
    ".json",
)


def _graphql(config: Config, query: str, variables: dict) -> dict:
    body = post_json(
        _ENDPOINT,
        {"query": query, "variables": variables},
        {
            "Authorization": f"Bearer {config.cloudflare_token}",
            "Content-Type": "application/json",
        },
    )
    if body.get("errors"):
        messages = "; ".join(error.get("message", "unknown error") for error in body["errors"])
        raise RuntimeError(f"Cloudflare analytics: {messages}")
    zones = ((body.get("data") or {}).get("viewer") or {}).get("zones") or []
    if not zones:
        raise RuntimeError("Cloudflare analytics returned no zone. Check CLOUDFLARE_ZONE_ID.")
    return zones[0]


def fetch_traffic(config: Config, window: Window, today: date) -> dict:
    zone_id = config.cloudflare_zone_id
    period = _graphql(
        config,
        """
        query Period($zoneTag: String!, $since: Date!, $until: Date!) {
          viewer {
            zones(filter: { zoneTag: $zoneTag }) {
              httpRequests1dGroups(limit: 1, filter: { date_geq: $since, date_lt: $until }) {
                sum {
                  requests
                  bytes
                  pageViews
                  cachedRequests
                  threats
                  countryMap { clientCountryName requests }
                }
                uniq { uniques }
              }
            }
          }
        }
        """,
        {"zoneTag": zone_id, "since": window.start.isoformat(), "until": window.end.isoformat()},
    )["httpRequests1dGroups"]
    if not period:
        raise RuntimeError(f"Cloudflare returned no daily analytics for {window.id}")
    totals = period[0]
    countries = [
        {"name": row["clientCountryName"], "requests": row["requests"]}
        for row in totals["sum"].get("countryMap") or []
        if row.get("clientCountryName")
    ]
    countries.sort(key=lambda row: row["requests"], reverse=True)

    daily_groups = _graphql(
        config,
        """
        query Daily($zoneTag: String!, $since: Date!, $until: Date!) {
          viewer {
            zones(filter: { zoneTag: $zoneTag }) {
              httpRequests1dGroups(
                limit: 400
                orderBy: [date_ASC]
                filter: { date_geq: $since, date_lt: $until }
              ) {
                dimensions { date }
                sum { requests pageViews bytes }
                uniq { uniques }
              }
            }
          }
        }
        """,
        {"zoneTag": zone_id, "since": window.start.isoformat(), "until": window.end.isoformat()},
    )["httpRequests1dGroups"]
    daily = [
        {
            "date": row["dimensions"]["date"],
            "requests": row["sum"]["requests"],
            "page_views": row["sum"]["pageViews"],
            "bytes": row["sum"]["bytes"],
            "uniques": row["uniq"]["uniques"],
        }
        for row in daily_groups
    ]

    try:
        top_pages, top_pages_note = _top_pages(config, window, today)
    except RuntimeError as exc:
        top_pages, top_pages_note = [], str(exc)
    try:
        book_requests, book_note = _book_requests(config, window, today)
    except RuntimeError as exc:
        book_requests, book_note = None, str(exc)
    return {
        "requests": totals["sum"]["requests"],
        "page_views": totals["sum"]["pageViews"],
        "bytes": totals["sum"]["bytes"],
        "cached_requests": totals["sum"]["cachedRequests"],
        "threats": totals["sum"]["threats"],
        "uniques": totals["uniq"]["uniques"],
        "daily": daily,
        "countries": countries,
        "top_pages": top_pages,
        "top_pages_note": top_pages_note,
        "routes": [{"path": BOOK_ROUTE, "requests": book_requests, "note": book_note}],
    }


def _top_pages(config: Config, window: Window, today: date) -> tuple[list[dict], str | None]:
    counts: dict[str, int] = defaultdict(int)
    covered = 0
    skipped = 0
    for chunk in slice_days(window, 30):
        if not covers_retention(chunk, today, 31):
            skipped += chunk.days
            continue
        covered += chunk.days
        groups = _graphql(
            config,
            """
            query Paths($zoneTag: String!, $start: Time!, $end: Time!) {
              viewer {
                zones(filter: { zoneTag: $zoneTag }) {
                  httpRequestsAdaptiveGroups(
                    limit: 250
                    orderBy: [count_DESC]
                    filter: {
                      datetime_geq: $start
                      datetime_lt: $end
                      requestSource: "eyeball"
                    }
                  ) {
                    count
                    dimensions { clientRequestPath }
                  }
                }
              }
            }
            """,
            {
                "zoneTag": config.cloudflare_zone_id,
                "start": utc_stamp(chunk.start, config.timezone),
                "end": utc_stamp(chunk.end, config.timezone),
            },
        )["httpRequestsAdaptiveGroups"]
        for row in groups:
            path = _canonical(row["dimensions"]["clientRequestPath"] or "/")
            if _keep_path(path):
                counts[path] += row["count"]
    pages = [
        {"path": path, "requests": count}
        for path, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:15]
    ]
    if covered == 0:
        return [], "Top pages were no longer in Cloudflare's 31-day path history when this was collected."
    if skipped:
        return pages, "Top pages cover only the part of this window still in Cloudflare's 31-day path history."
    return pages, None


def _book_requests(config: Config, window: Window, today: date) -> tuple[int | None, str | None]:
    """Count the Hope Johnson book even when it is outside the top paths."""
    total = 0
    covered = 0
    skipped = 0
    encoded = quote(BOOK_ROUTE, safe="/")
    for chunk in slice_days(window, 30):
        if not covers_retention(chunk, today, 31):
            skipped += chunk.days
            continue
        covered += chunk.days
        groups = _graphql(
            config,
            """
            query Book($zoneTag: String!, $start: Time!, $end: Time!, $path: String!) {
              viewer {
                zones(filter: { zoneTag: $zoneTag }) {
                  httpRequestsAdaptiveGroups(
                    limit: 5
                    orderBy: [count_DESC]
                    filter: {
                      datetime_geq: $start
                      datetime_lt: $end
                      requestSource: "eyeball"
                      clientRequestPath: $path
                    }
                  ) {
                    count
                  }
                }
              }
            }
            """,
            {
                "zoneTag": config.cloudflare_zone_id,
                "start": utc_stamp(chunk.start, config.timezone),
                "end": utc_stamp(chunk.end, config.timezone),
                "path": encoded,
            },
        )["httpRequestsAdaptiveGroups"]
        total += sum(row["count"] for row in groups)
    if covered == 0:
        return None, (
            "Requests for this route were no longer in Cloudflare's 31-day path history when this was collected."
        )
    if skipped:
        return total, (
            "Requests for this route cover only the part of this window still in Cloudflare's 31-day path history."
        )
    return total, None


def is_book_route(path: str) -> bool:
    return _canonical(path) == BOOK_ROUTE


_PROBE_ROOTS = (
    "/wp",
    "/wordpress",
    "/cms",
    "/xmlrpc",
    "/cgi-bin",
    "/phpmyadmin",
    "/blog",
    "/press",
    "/news",
    "/site",
    "/backup",
    "/old",
    "/admin",
    "/wp-admin",
    "/wp-login",
    "/wp-content",
    "/wp-includes",
    "/wp-json",
    "/login",
    "/register",
    "/signin",
    "/signup",
    "/api",
)


def _canonical(path: str) -> str:
    path = unquote(path or "/")
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return path or "/"


def _keep_path(path: str) -> bool:
    lowered = unquote(path).lower()
    if lowered.startswith("/cdn-cgi/") or lowered.startswith("/_astro/") or lowered.startswith("/assets/"):
        return False
    if lowered.startswith("/.") or ".env" in lowered or "/.git" in lowered:
        return False
    trimmed = lowered.rstrip("/") or "/"
    if any(
        trimmed == root or trimmed.startswith(root + "/") or trimmed.startswith(root + "-")
        for root in _PROBE_ROOTS
    ):
        return False
    return not lowered.endswith(_STATIC_SUFFIXES)
