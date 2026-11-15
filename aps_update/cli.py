from __future__ import annotations

import argparse
from datetime import datetime, timedelta

from aps_update.aggregate import build_report, comparison_totals, select_collections
from aps_update.collect import collect_windows
from aps_update.config import REPORTS_DIR, load_config
from aps_update.ranges import Window, default_window, format_window, parse_date, today_in
from aps_update.render import render
from aps_update.store import latest_finalized, load_collections, save_finalized


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and report APS meeting updates.")
    commands = parser.add_subparsers(dest="command", required=True)

    collect = commands.add_parser("collect", help="Save changelog, traffic, and social snapshots.")
    collect.add_argument("--from", dest="start", help="Inclusive start date, YYYY-MM-DD.")
    collect.add_argument("--through", dest="through", help="Inclusive end date, YYYY-MM-DD.")
    collect.add_argument("--force", action="store_true", help="Replace an existing collection with the same dates.")

    report = commands.add_parser("report", help="Write the report for every collection since the last delivered one.")
    report.add_argument("--finalize", action="store_true", help="Mark this report as delivered. The next comparison starts after it.")

    commands.add_parser("status", help="Show saved collections and the last delivered report.")
    args = parser.parse_args()
    config = load_config()

    if args.command == "collect":
        _collect(config, args)
    elif args.command == "report":
        _report(config, args.finalize)
    else:
        _status(config)


def _collect(config, args) -> None:
    today = today_in(config.timezone)
    finalized = latest_finalized()
    collections = load_collections()
    last_end = None
    if collections:
        last_end = parse_date(max(item["end"] for item in collections))
    if args.start or args.through:
        start = parse_date(args.start) if args.start else (last_end or today - timedelta(days=30))
        end = parse_date(args.through) + timedelta(days=1) if args.through else today
        try:
            window = Window(start, end)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    else:
        window = default_window(today, last_end)
        if window is None:
            print(f"Nothing to collect. The latest collection already runs through {format_window(Window(last_end - timedelta(days=1), last_end)) if last_end else 'today'}.")
            return
    if finalized and window.start < parse_date(finalized["end"]) and not args.start:
        print(
            f"Note: the last delivered report ends {finalized['end']}. "
            "This collection can still fill a gap before the next report."
        )
    saved = collect_windows(config, [window], force=args.force)
    if not saved:
        print("No new collections.")


def _report(config, finalize: bool) -> None:
    collections = load_collections()
    finalized = latest_finalized()
    selected = select_collections(collections, finalized["end"] if finalized else None)
    if not selected:
        if finalized:
            print(f"No collections since the last delivered report, which ends {finalized['end']}. Run collect first.")
        else:
            print("No collections yet. Run collect first.")
        return
    report = build_report(selected, str(config.timezone), datetime.now(config.timezone))
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{report['id']}.md"
    path.write_text(render(report, finalized))
    print(f"wrote {path.relative_to(config.root)}")
    if finalize:
        payload = comparison_totals(report)
        payload["finalized_at"] = datetime.now(config.timezone).isoformat(timespec="seconds")
        save_finalized(payload)
        print(f"Finalized. The next report will start at {report['end']}.")
    else:
        print("Draft only. Run report --finalize after this is the update delivered at the meeting.")


def _status(config) -> None:
    collections = load_collections()
    finalized = latest_finalized()
    if not collections:
        print("No collections.")
    else:
        print("Collections:")
        for item in collections:
            window = Window(parse_date(item["start"]), parse_date(item["end"]))
            socials = "buffer" if item["socials"]["available"] else "no buffer insights"
            print(f"  {format_window(window)}  {socials}  {item['id']}")
    if finalized:
        window = Window(parse_date(finalized["start"]), parse_date(finalized["end"]))
        print(f"Last delivered report: {format_window(window)}")
    else:
        print("No delivered report yet.")
    pending = select_collections(collections, finalized["end"] if finalized else None)
    if pending and finalized:
        print(f"{len(pending)} collection(s) waiting for the next report.")
