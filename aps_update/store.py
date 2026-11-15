from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from aps_update.config import COLLECTIONS_DIR, FINALIZED_DIR, STATE_PATH
from aps_update.ranges import Window, overlaps


def collection_path(window: Window) -> Path:
    return COLLECTIONS_DIR / f"{window.id}.json"


def load_collections() -> list[dict]:
    if not COLLECTIONS_DIR.exists():
        return []
    loaded = []
    for path in sorted(COLLECTIONS_DIR.glob("*.json")):
        loaded.append(json.loads(path.read_text()))
    loaded.sort(key=lambda item: (item["start"], item["end"]))
    return loaded


def save_collection(payload: dict) -> Path:
    COLLECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = COLLECTIONS_DIR / f"{payload['id']}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def find_overlap(window: Window, collections: list[dict]) -> dict | None:
    for existing in collections:
        other = Window(date.fromisoformat(existing["start"]), date.fromisoformat(existing["end"]))
        if window.id == other.id or overlaps(window, other):
            return existing
    return None


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text())


def latest_finalized() -> dict | None:
    state = load_state()
    report_id = state.get("finalized_report")
    if not report_id:
        return None
    path = FINALIZED_DIR / f"{report_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def save_finalized(payload: dict) -> None:
    FINALIZED_DIR.mkdir(parents=True, exist_ok=True)
    (FINALIZED_DIR / f"{payload['id']}.json").write_text(json.dumps(payload, indent=2) + "\n")
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"finalized_report": payload["id"]}, indent=2) + "\n")
