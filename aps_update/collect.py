from __future__ import annotations

from datetime import datetime

from aps_update.buffer import fetch_socials
from aps_update.changelog import fetch_changelog
from aps_update.cloudflare import fetch_traffic
from aps_update.config import Config
from aps_update.ranges import Window, format_window, split_for_storage, today_in
from aps_update.site_inventory import fetch_inventory
from aps_update.store import find_overlap, load_collections, save_collection


def collect_windows(config: Config, windows: list[Window], *, force: bool = False) -> list[dict]:
    today = today_in(config.timezone)
    existing = [] if force else load_collections()
    saved = []
    for window in windows:
        for chunk in split_for_storage(window):
            overlap = None if force else find_overlap(chunk, existing)
            if overlap and overlap["id"] == chunk.id:
                print(f"skip {chunk.id} (already collected)")
                continue
            if overlap:
                raise SystemExit(
                    f"{format_window(chunk)} overlaps collection {overlap['id']}. "
                    "Choose a range that starts where that collection ends."
                )
            print(f"collect {format_window(chunk)}")
            payload = {
                "id": chunk.id,
                "start": chunk.start.isoformat(),
                "end": chunk.end.isoformat(),
                "timezone": str(config.timezone),
                "collected_at": datetime.now(config.timezone).isoformat(timespec="seconds"),
                "changelog": fetch_changelog(config.website_repo, chunk),
                "inventory": fetch_inventory(config.website_repo, chunk, config.timezone),
                "traffic": fetch_traffic(config, chunk, today),
                "socials": fetch_socials(config, chunk, today),
            }
            path = save_collection(payload)
            existing.append(payload)
            saved.append(payload)
            socials = "saved" if payload["socials"]["available"] else "unavailable"
            inventory = payload["inventory"]
            print(
                f"  wrote {path.relative_to(config.root)} "
                f"({inventory['events']} events, {inventory['pages']} pages, Buffer insights {socials})"
            )
    return saved
