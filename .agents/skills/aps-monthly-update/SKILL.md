---
name: aps-monthly-update
description: Collects and writes the Alberta Palaeontological Society meeting report from the website changelog, Cloudflare traffic, and Buffer social metrics. Use when the user asks for the APS monthly update, meeting report, website stats, or social stats, or asks to collect data for a later meeting.
---

# APS monthly update

Work from the repository root.

- `python -m aps_update status`
- `python -m aps_update collect`
- `python -m aps_update collect --from YYYY-MM-DD --through YYYY-MM-DD`
- `python -m aps_update report`
- `python -m aps_update report --finalize`

## Collect even when there is no meeting

Buffer insights and Cloudflare top pages only cover about 31 days. Cloudflare daily totals for this zone cover about a year, and the changelog is permanent. `collect` saves a snapshot so a later meeting can still include that stretch.

With no dates, `collect` saves through yesterday, starting where the last snapshot ended. The first run saves the last 30 days. A range longer than 31 days is stored as one snapshot per calendar month. Months outside Buffer's history are still saved, with the missing social numbers marked unavailable.

Collecting does not move the comparison date.

## Report from the last delivered update

`report` includes every snapshot after the last finalized report. If May and June had no meeting, the July report shows May, June, and July, with combined totals where adding is valid.

Show the user the file it writes. Do not change a figure, date, or comparison. `## Field Trips` stays empty.

The Hope Johnson book, Now There Was a Lady!, always has its request count. Each collection is listed, and the total is compared with the previous delivered report when that count exists. The report does not list individual posts.

Run `report --finalize` only after the user says this is the update delivered at the meeting. That is the date the next comparison starts from. A draft does not move it.

## How to read the numbers

- Events are calendar entries, and pages are the site's own pages, including each Fossil Friday. Both are the site at the end of the period. Do not add them across snapshots.
- Unique visitors are Cloudflare client addresses for one snapshot. Do not add them across snapshots.
- Reach works the same way. Do not add it across snapshots.
- Requests, page views, data transfer, posts, reactions, comments, impressions, shares, and clicks are safe to add. The report already does that.
- Buffer does not provide follower totals.
- Metrics can lag the networks by about a day.
- Do not estimate a number the snapshot marks unavailable.
