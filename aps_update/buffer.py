from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from aps_update.config import Config
from aps_update.http_json import post_json
from aps_update.ranges import Window, covers_retention, utc_stamp

_ENDPOINT = "https://api.buffer.com"
_COUNT_METRICS = (
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
_SERVICE_ORDER = {"facebook": 0, "instagram": 1, "mastodon": 2}


def fetch_socials(config: Config, window: Window, today: date) -> dict:
    if not covers_retention(window, today, 31):
        return {
            "available": False,
            "reason": (
                "Buffer free-plan insights only cover the last 31 days, "
                "and this window was already outside that history."
            ),
            "channels": [],
        }
    organization_id, channels = _account(config)
    start = utc_stamp(window.start, config.timezone)
    end = utc_stamp(window.last_day, config.timezone, end_of_day=True)
    try:
        collected = [
            _channel(config, organization_id, channel, window, start, end)
            for channel in sorted(channels, key=lambda item: (_SERVICE_ORDER.get(item["service"], 9), item["name"]))
        ]
    except RuntimeError as exc:
        if "31 days" in str(exc).lower():
            return {"available": False, "reason": str(exc), "channels": []}
        raise
    return {"available": True, "reason": None, "channels": collected}


def _graphql(config: Config, query: str, variables: dict | None = None) -> dict:
    payload: dict = {"query": query}
    if variables:
        payload["variables"] = variables
    body = post_json(
        _ENDPOINT,
        payload,
        {
            "Authorization": f"Bearer {config.buffer_api_key}",
            "Content-Type": "application/json",
        },
    )
    if body.get("errors"):
        messages = "; ".join(error.get("message", "unknown error") for error in body["errors"])
        raise RuntimeError(f"Buffer: {messages}")
    return body["data"]


def _account(config: Config) -> tuple[str, list[dict]]:
    data = _graphql(config, "query { account { organizations { id name } } }")
    organizations = data["account"]["organizations"]
    if not organizations:
        raise RuntimeError("Buffer account has no organization.")
    organization = organizations[0]
    data = _graphql(
        config,
        """
        query Channels($id: OrganizationId!) {
          channels(input: { organizationId: $id }) { id name displayName service }
        }
        """,
        {"id": organization["id"]},
    )
    channels = [
        {
            "id": channel["id"],
            "service": channel["service"],
            "name": channel.get("displayName") or channel.get("name") or channel["service"],
        }
        for channel in data["channels"]
    ]
    return organization["id"], channels


def _channel(config: Config, organization_id: str, channel: dict, window: Window, start: str, end: str) -> dict:
    metrics_body = _graphql(
        config,
        """
        query Agg($org: OrganizationId!, $channel: ChannelId!, $start: DateTime!, $end: DateTime!) {
          aggregatedPostMetrics(input: {
            organizationId: $org
            channelIds: [$channel]
            startDateTime: $start
            endDateTime: $end
          }) {
            metrics { type name value unit }
            metricsUpdatedAt
          }
        }
        """,
        {"org": organization_id, "channel": channel["id"], "start": start, "end": end},
    )["aggregatedPostMetrics"]
    metrics = {
        item["type"]: {"name": item["name"], "value": item["value"], "unit": item["unit"]}
        for item in metrics_body["metrics"]
        if item["type"] in _COUNT_METRICS or item["type"] == "engagementRate"
    }
    posts = _posts(config, organization_id, channel["id"], start, end, window, config.timezone)
    posts = _dedupe_posts(posts)
    posts.sort(key=lambda post: post["reactions"], reverse=True)
    return {
        "id": channel["id"],
        "service": channel["service"],
        "name": channel["name"],
        "metrics": metrics,
        "metrics_updated_at": metrics_body.get("metricsUpdatedAt"),
        "posts": posts,
    }


def _posts(
    config: Config,
    organization_id: str,
    channel_id: str,
    start: str,
    end: str,
    window: Window,
    tz: ZoneInfo,
) -> list[dict]:
    posts: list[dict] = []
    cursor = None
    while True:
        variables = {
            "org": organization_id,
            "channel": channel_id,
            "start": start,
            "end": end,
        }
        after = ", $after: String" if cursor else ""
        after_arg = ", after: $after" if cursor else ""
        if cursor:
            variables["after"] = cursor
        data = _graphql(
            config,
            f"""
            query Posts(
              $org: OrganizationId!
              $channel: ChannelId!
              $start: DateTime!
              $end: DateTime!
              {after}
            ) {{
              posts(first: 50{after_arg}, input: {{
                organizationId: $org
                filter: {{
                  status: [sent]
                  channelIds: [$channel]
                  dueAt: {{ start: $start, end: $end }}
                }}
              }}) {{
                edges {{
                  node {{ id text dueAt sentAt externalLink metrics {{ type value }} }}
                }}
                pageInfo {{ hasNextPage endCursor }}
              }}
            }}
            """,
            variables,
        )["posts"]
        for edge in data["edges"]:
            node = edge["node"]
            when = _local_day(node.get("sentAt") or node.get("dueAt"), tz)
            if when is not None and not (window.start <= when < window.end):
                continue
            values = {item["type"]: item["value"] for item in node.get("metrics") or []}
            text = " ".join((node.get("text") or "").split())
            posts.append(
                {
                    "id": node["id"],
                    "text": text,
                    "sent_on": when.isoformat() if when else None,
                    "url": node.get("externalLink"),
                    "reactions": values.get("reactions", 0),
                    "comments": values.get("comments", 0),
                }
            )
        if not data["pageInfo"]["hasNextPage"]:
            return posts
        cursor = data["pageInfo"]["endCursor"]


def _dedupe_posts(posts: list[dict]) -> list[dict]:
    """Instagram can return several copies of one send. Keep the copy with reactions."""
    best: dict[tuple, dict] = {}
    for post in posts:
        key = (post["sent_on"], post["text"])
        current = best.get(key)
        if current is None or post["reactions"] > current["reactions"]:
            best[key] = post
    return list(best.values())


def _local_day(stamp: str | None, tz: ZoneInfo) -> date | None:
    if not stamp:
        return None
    if stamp.endswith("Z"):
        stamp = stamp[:-1] + "+00:00"
    moment = datetime.fromisoformat(stamp)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(tz).date()
