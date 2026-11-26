# APS monthly update

Two steps, run at different times:

1. **Collect** saves a snapshot of the website and social numbers. Do this at least once a month, including months with no meeting.
2. **Report** writes the meeting update from every snapshot saved since the last update you marked as delivered. Do this when a meeting needs the update.

Collecting does not change what the next report is compared with. Only marking a report as delivered does that.

## Setup

Copy `.env.example` to `.env` and fill in the website repo, a Cloudflare token with Zone Analytics Read, the zone id, and a Buffer personal API key.

Dates use America/Edmonton unless `REPORT_TIMEZONE` is set. Run the commands from this directory.

## 1. Collect

Buffer insights and Cloudflare's top pages only cover about 31 days. A snapshot keeps that stretch so a later meeting can still include it. Cloudflare's daily totals for this zone cover about a year, and the changelog is kept permanently. If a month is already outside Buffer's history, the snapshot still saves the changelog, traffic totals, and site counts, and marks the social numbers unavailable.

```bash
python -m aps_update status
python -m aps_update collect
python -m aps_update collect --from 2026-05-01 --through 2026-05-31
```

`status` shows the snapshots already saved and whether a report has been marked as delivered.

`collect` with no dates saves through yesterday, starting where the last snapshot ended. The first run saves the last 30 days. `--from` is inclusive and `--through` is inclusive. A range longer than 31 days is stored as one snapshot per calendar month.

If May and June have no meeting, still collect those months. The July report then includes May, June, and July.

Snapshots are stored in `data/collections/`. They contain site traffic and the text of public social posts, and no API keys. `data/` and `reports/` stay on this machine and are listed in `.gitignore`.

## 2. Report

```bash
python -m aps_update report
python -m aps_update report --finalize
```

`report` writes `reports/<start>_<end>.md`. It includes every snapshot after the last delivered report. It does not move the comparison date, so you can read the draft and run it again.

The file has four sections: Website, Socials, and an empty Field Trips section for you to fill in. Website includes the changelog, the number of events and pages, and traffic.

`--finalize` records that this file is the update that was delivered at the meeting. The next report starts the day after this one ends, and is compared with it. Finalize only after the update has been delivered. A draft does not count.

## How a multi-month report combines snapshots

Requests, page views, data transfer, posts, reactions, comments, impressions, shares, and clicks are added across the snapshots in the report.

Requests for the Hope Johnson book, Now There Was a Lady!, are listed for every collection. They are added when every collection has that count.

These are not added:

- **Events and pages** are the calendar and the site at the end of the latest snapshot.
- **Unique visitors** are distinct client addresses inside one snapshot. The same person can appear in more than one.
- **Reach** works the same way.

## What each source can answer

- Website changes come from `CHANGELOG.md` in the public site repo.
- Events are calendar entries. Pages are the site's own pages, including each Fossil Friday, and do not count those calendar entries again.
- Traffic comes from Cloudflare: requests, page views, data transfer, unique client addresses, countries, top pages, and requests for the Hope Johnson book.
- Social numbers come from Buffer, per channel: posts, reactions, comments, and whichever of impressions, reach, shares, clicks, and engagement rate that channel provides. Follower totals are not available. Figures can lag the networks by about a day.
