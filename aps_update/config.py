from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from aps_update.ranges import zone

ROOT = Path(__file__).resolve().parents[1]
COLLECTIONS_DIR = ROOT / "data" / "collections"
REPORTS_DIR = ROOT / "reports"
STATE_PATH = ROOT / "data" / "state.json"
FINALIZED_DIR = ROOT / "data" / "reports"

REQUIRED = (
    "WEBSITE_GIT_REPO",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_ZONE_ID",
    "BUFFER_API_KEY",
)


@dataclass(frozen=True)
class Config:
    website_repo: str
    cloudflare_token: str
    cloudflare_zone_id: str
    buffer_api_key: str
    timezone: ZoneInfo
    root: Path = ROOT


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config() -> Config:
    load_dotenv(ROOT / ".env")
    missing = [key for key in REQUIRED if not os.environ.get(key)]
    if missing:
        raise SystemExit(f"Missing environment variables: {', '.join(missing)}")
    return Config(
        website_repo=os.environ["WEBSITE_GIT_REPO"],
        cloudflare_token=os.environ["CLOUDFLARE_API_TOKEN"],
        cloudflare_zone_id=os.environ["CLOUDFLARE_ZONE_ID"],
        buffer_api_key=os.environ["BUFFER_API_KEY"],
        timezone=zone(os.environ.get("REPORT_TIMEZONE", "America/Edmonton")),
    )
