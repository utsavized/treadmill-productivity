# Treadmill Productivity: implementation spec
Version: v4 · Test data lives inside the tests; no data files in the repository

## Summary
A local Python app (D17) reads active computer time from ActivityWatch (D11). It labels each active second as walking or assumed sitting, using Start/Stop sessions recorded in the app (D12). It gives each second an effort category from a rules file and compares average effort per active minute between the two conditions. Results appear on a local dashboard (D13).

**What the indicator measures.** Effort comes from fixed category weights, so a VS Code minute always scores 3. Any difference between walking and sitting therefore reflects *which* activities were done, not *how intensely* (D19). The dashboard says so next to the indicator.

## Requirements map

| FR | Spec section |
|---|---|
| FR1 Collect activity | Ingestion; Core logic §1 |
| FR2 Walking sessions | Data model; API; Edge cases |
| FR3 Classify conditions | Core logic §2 |
| FR4 Assign effort | Data model (rules file); Core logic §3 |
| FR5 Compare | Core logic §4 |
| FR6 Explain | Core logic §5 |
| FR7 Coverage | Core logic §6; Ingestion (ActivityWatch down) |
| FR8 Local data | Data model |
| FR9 Dashboard | API; UI / output |

## Data model

Three stores. Only walking sessions are owned by the app. Activity is read live from ActivityWatch and never copied (D29).

| Store | Contents | Written by | In git |
|---|---|---|---|
| ActivityWatch, `localhost:5600` | Window and AFK events | ActivityWatch watchers | No |
| `data/treadmill.db` (SQLite) | Walking sessions | The app | No, `data/` is ignored |
| `config/categories.toml` | Weights and ordered rules | Utsav, by hand | Yes |

**`walks` table**

```sql
CREATE TABLE walks (
  id         INTEGER PRIMARY KEY,
  started_at TEXT NOT NULL,   -- UTC, ISO-8601 with +00:00
  ended_at   TEXT             -- UTC; NULL while the session is open
);
CREATE UNIQUE INDEX one_open_walk ON walks ((ended_at IS NULL)) WHERE ended_at IS NULL;
```

The database is created on first run.

**`config/categories.toml`**

```toml
[weights]
none = 0
low = 1
medium = 2
high = 3

[[rules]]                       # checked top to bottom, first match wins
app = "Microsoft Edge"
title_contains = ["YouTube", "Netflix"]
category = "none"

[[rules]]
app = ["Claude", "ChatGPT"]     # app is a string or a list
category = "medium"
```

- `app` is an exact match on the app name. `title_contains` is an optional case-insensitive substring match, and any item in the list matches.
- Valid categories are `none`, `low`, `medium` and `high`. An app with no matching rule is unrated.
- The file is read on every report, so an edit applies immediately, to past periods too (D29).
- An invalid file (bad TOML or an unknown category) makes the report fail with an error that names the problem.

## Ingestion

**Finding buckets.** Call `GET /api/0/buckets/` and take the bucket whose `type` is `currentwindow` and the one whose `type` is `afkstatus`. If there's more than one of a type, prefer the bucket whose `hostname` equals the Mac's hostname, otherwise the one with the latest `last_updated`.

**Active segments (FR1).** One call to `POST /api/0/query/` with `timeperiods: ["<start>/<end>"]` in UTC:

```
window = flood(query_bucket("<window bucket>"));
afk = flood(query_bucket("<afk bucket>"));
not_afk = filter_keyvals(afk, "status", ["not-afk"]);
RETURN = filter_period_intersect(window, not_afk);
```

Each returned event becomes a segment `{start, end, app, title}`, where `end = start + duration`. Segments are clipped to `[period start, min(period end, now)]` and zero-length segments are dropped.

**AFK events (FR7).** Call `GET /api/0/buckets/<afk bucket>/events?start=…&end=…&limit=-1`. Both statuses are used, because what matters for coverage is whether ActivityWatch was recording at all.

**Timestamps.** ActivityWatch timestamps are treated as UTC. A timestamp with no offset is read as UTC.

**ActivityWatch down (D28).** If ActivityWatch can't be reached, or a required bucket is missing, the report fails with an explicit error. It never returns empty results. Walking-session endpoints keep working, since they only use SQLite.

## API

FastAPI, bound to `127.0.0.1:8765`, started with `uv run treadmill`. Times in requests and responses are ISO-8601 with an offset. Dates are local `YYYY-MM-DD`.

| Method and path | Does | Errors |
|---|---|---|
| `GET /api/status` | `{activitywatch: "ok" \| "unreachable" \| "buckets_missing", open_walk: {id, started_at} \| null}` | — |
| `GET /api/walks?start=&end=` | Sessions overlapping the period, newest first | — |
| `POST /api/walks/start` | Opens a session at now | 409 if a session is already open |
| `POST /api/walks/stop` | Closes the open session at now | 409 if no session is open |
| `PATCH /api/walks/{id}` | Body `{started_at, ended_at}`; `ended_at` may be null only for the open session | 422 if end ≤ start, end is in the future, or it overlaps another session; 404 |
| `DELETE /api/walks/{id}` | Deletes a session (D27) | 404 |
| `GET /api/report?start=&end=` | The report below | 503 `{error: "activitywatch_unreachable" \| "buckets_missing", message}`; 422 for a bad rules file or bad dates |

**Report shape**

```json
{
  "period": {"start": "2026-10-27", "end": "2026-10-27", "timezone": "America/Chicago"},
  "conditions": {
    "walking": {"active_s": 3600, "rated_s": 3600, "unrated_s": 0, "score": 1.5, "unavailable": null},
    "sitting": {"active_s": 6300, "rated_s": 5400, "unrated_s": 900, "score": 2.3333, "unavailable": null}
  },
  "verdict": "lower",
  "difference": -0.8333,
  "categories": [{"category": "high", "walking_s": 1800, "sitting_s": 3600}],
  "apps": [{"app": "Code", "walking_s": 1800, "sitting_s": 3600}],
  "coverage": {
    "dates": ["2026-10-27"],
    "gaps": [{"start": "…", "end": "…", "during_walk": false}]
  },
  "open_walk": null
}
```

- `score` and `difference` are sent at full precision, and the dashboard rounds them.
- `unavailable` is `null` or one of `no_sessions`, `no_active_time`, `all_unrated`.
- `verdict` and `difference` are `null` when either condition is unavailable.
- `categories` always lists all five (`none`, `low`, `medium`, `high`, `unrated`). `apps` is sorted by total time, largest first.

## Core logic

### §1 Time precision
All durations are computed in seconds at full precision. Minutes are for display only.

### §2 Conditions
An active second is **walking** if it falls within a walking session (`started_at` ≤ t < `ended_at`) and **assumed sitting** otherwise. An activity event that crosses a session boundary is split at the boundary. An open session counts up to "now".

### §3 Effort categories
Weights: none = 0, low = 1, medium = 2, high = 3 (D23). Rules are checked in order and the first match wins. A rule matches an app name, optionally narrowed by a window-title substring. Edge windows that match no title rule count as **none** ("general web browsing"). Any other app with no rule is **unrated** (D20).

Default rules (D22). App names must be confirmed against ActivityWatch on Utsav's Mac during setup.

| App | Title contains | Category |
|---|---|---|
| Microsoft Edge | YouTube, Netflix | none |
| Microsoft Edge | Claude, ChatGPT | medium |
| Microsoft Edge | Superhuman, Outlook | low |
| Microsoft Edge | (anything else) | none |
| Claude, ChatGPT | | medium |
| Superhuman, Mail, Microsoft Outlook, Slack, Messages | | low |
| Code (VS Code), DaVinci Resolve, Terminal, iTerm2 | | high |
| Finder, System Settings, QuickTime Player | | none |
| Anything else (e.g. Notion, Wispr Flow) | | unrated |

### §4 Estimated productivity
For each condition: Σ(weight × rated active seconds) ÷ rated active seconds. Unrated time is left out of the average and shown as its own row. Results are shown to 2 decimals. The verdict is **higher**, **lower** or **equal** while walking, where "equal" means the difference rounds to 0.00 (D23).

A condition with 0 rated active seconds is **unavailable**, and the dashboard says why (D24):
- `no_sessions`: walking only, when no session overlaps the period.
- `no_active_time`: no active time in the condition.
- `all_unrated`: there is active time, but none of it is rated.

There is no minimum beyond that.

**Worked example** (also the test data in `tests/test_compare.py`; all times local):

| Time | App, title | Condition | Category | Minutes |
|---|---|---|---|---|
| 09:00–10:00 | Code | sitting | high | 60 |
| 10:00–10:30 | Code (same event, split at Start) | walking | high | 30 |
| 10:30–11:00 | Microsoft Edge, "… - YouTube" | walking | none | 30 |
| 11:00–11:30 | Superhuman | sitting | low | 30 |
| 11:30–11:45 | Notion | sitting | unrated | 15 |
| 11:45–12:15 | Code, but AFK the whole time | — | excluded | 0 |

The walking session runs 10:00–11:00.
- Walking: (30×3 + 30×0) ÷ 60 = **1.50**
- Sitting: (60×3 + 30×1) ÷ 90 = **2.33**, plus 15 minutes unrated
- Verdict: **lower** while walking, difference −0.83

### §5 Explanation
For each condition, show total active time, time in each category, and time in each app (minutes and % of the condition's active time). Within-category and within-app views compare the **time split** between conditions. They don't compare scores, because a single category's score is identical in both conditions by construction (D19).

### §6 Period and coverage
Periods are local calendar days in the Mac's time zone, with both dates inclusive. Presets: Today (the default), Last 7 days, and a custom range (D25). `coverage.dates` lists the local dates that have any AFK data. The dashboard also shows active time per condition.

A **collection gap** is a stretch of 10 minutes or more between the period start and min(period end, now) that no AFK event covers. A gap is flagged `during_walk` if it overlaps a walking session (D26).

## Edge cases
- **Forgotten Stop.** Not handled automatically. Utsav is responsible for pressing Stop. The dashboard shows an open session prominently, and sessions can be edited (D21).
- **Start while a session is open.** Rejected with 409.
- **Session edit that overlaps another session, ends before it starts, or ends in the future.** Rejected with 422.
- **Accidental session.** Deleted with `DELETE` (D27).
- **Period in the future, or partly in the future.** Counted only up to now.
- **Start date after end date.** Rejected with 422.

## UI / output

One static page at `http://localhost:8765` (`index.html`, `app.js`, vendored `chart.umd.min.js`). It loads `/api/status` and `/api/report` when it opens and whenever the period changes, plus `/api/status` every 30 seconds. Times are shown in local time and durations as `1h 05m`. Top to bottom:

1. **Status bar.** A Start or Stop button. While a session is open, a prominent banner shows "Walking since 10:02 (1h 12m)". If ActivityWatch is down, a red banner says "ActivityWatch isn't running, so results can't be calculated", and the sections below are hidden.
2. **Period picker.** Today / Last 7 days / Custom (two date inputs).
3. **Headline.** The walking and sitting scores (2 decimals) and the verdict ("Lower while walking by 0.83"). An unavailable condition shows its reason in place of a score:
   - `no_sessions`: "No walking sessions in this period"
   - `no_active_time`: "No active computer time"
   - `all_unrated`: "All active time is in apps without a category"

   Under the headline, three fixed notes: how the score is calculated; that it reflects what you worked on, not how intensely (D19); and that passive video counts as idle (D15).
4. **Categories.** A table with one row per category including unrated. Columns: walking minutes and %, sitting minutes and %. A grouped bar chart of the same data sits beside it.
5. **Apps.** The same columns, one row per app. The ten largest are shown, with a "show all" toggle.
6. **Coverage.** Dates covered, active time per condition, and a gap list. Gaps during a walk are highlighted.
7. **Sessions.** Sessions in the period. Each has Edit (two `datetime-local` inputs) and Delete (with a confirm step). API errors are shown inline.

Build priority if time runs short (D30): correct numbers and unavailable states, then tables and session controls, then charts.

## Acceptance criteria

Automated (pytest, test data built in the tests, no ActivityWatch needed):

- **AC1.** The worked example produces walking 1.50, sitting 2.33, 15 minutes sitting unrated, and verdict `lower`.
- **AC2.** An event crossing a session boundary is split to the second, and AFK time is excluded (worked example).
- **AC3.** A period with no sessions shows walking `no_sessions` and a sitting score, with verdict `null`. An empty period shows both conditions unavailable. A walking session with only unrated apps shows `all_unrated`.
- **AC4.** Rules: Edge with no title match is none, an unknown app is unrated, the first match wins, title matching ignores case, and an invalid rules file gives a 422 that names the problem.
- **AC5.** A score difference of less than 0.005 gives `equal`.
- **AC6.** A 10-minute stretch with no AFK data is reported as a gap, and one inside a session has `during_walk: true`. A 9-minute stretch isn't reported.
- **AC7.** Sessions: start, stop, edit and delete work. Start while open → 409. An overlapping or inverted edit → 422.
- **AC8.** ActivityWatch unreachable → the report returns 503, and start/stop still work.
- **AC9.** Local periods: a session that crosses midnight is split correctly across a one-day period.

Manual (Utsav's Mac, real ActivityWatch):

- **AC10.** The verification session: about 20 minutes of normal work with one short walking session. The dashboard shows the session, real app names, categories, both scores, and coverage for that day. Edge titles are categorized as expected.
- **AC11.** The server listens only on `127.0.0.1`. `git status` shows no files from `data/`, and the repository contains no data files; test data is built inside the tests (D31).

## Implementation plan

Each task is one or more commits that reference their section.

1. **Scaffold.** `pyproject.toml` (Python 3.12; fastapi, uvicorn, httpx; pytest), a `treadmill` entry point, and Python entries in `.gitignore`.
2. **Rules** (Data model, §3). `config/categories.toml` with the defaults, and `effort.py` loading and matching. Tests for AC4.
3. **Sessions** (Data model, API). `walks.py` with SQLite and validation. Tests for AC7.
4. **Core logic** (§1, §2, §4–§6). `classify.py` and `compare.py` as pure functions over segment, walk and AFK lists, with the worked example as test data. Tests for AC1–AC3, AC5, AC6 and AC9.
5. **ActivityWatch client** (Ingestion). `aw.py` for bucket lookup, the query, AFK events and the down errors. Test for AC8 using a mocked transport.
6. **API** (API). `api.py` routes wiring 2–5 together.
7. **Dashboard** (UI / output). Status bar, period picker, headline and tables first; charts last.
8. **Verification** (AC10, AC11). Run on the Mac, confirm the app names in §3 (a rules fix gets its own spec change), and report each AC with evidence.

## Future improvements (not in the MVP)
- **Within-activity effort signal (D19).** Options to evaluate: input intensity (keystroke and click rates), and sampling the screen or context about once a minute and having an AI model (Claude or similar) rate the effort level. This matters because a lot of high-effort work is dictated to AI, so typing volume undercounts thinking. Sampling keeps cost and data volume bounded, but sending screen content off the machine conflicts with FR8 and would need its own decision.
- **Automatic walk detection.** Bluetooth (D18) or Apple Health (D12).

## Open questions
None. The spec is ready for Utsav's approval.

## Decisions

| # | Decision | Rejected alternatives | Why | Raised by |
|---|---|---|---|---|
| D19 | Accept that the indicator reflects activity mix only. State this on the dashboard, and compare time splits within categories and apps. A within-activity signal (input intensity, sampled AI rating of the work) is a future improvement | Adding input-intensity or AI sampling to the MVP | Fixed weights can't see effort within an app; a real signal is beyond the 3-hour budget | Principal engineer; accepted by Utsav |
| D20 | Edge windows that match no title rule count as none; other unmatched apps are unrated | All unmatched as unrated (architecture proposal) | The FRD defines general web browsing as no effort | Principal engineer; accepted by Utsav |
| D21 | No automatic closing of a forgotten session; Utsav remembers to press Stop | Auto-close after 30 minutes idle | Keep the MVP simple; open sessions are visible and editable | Utsav |
| D22 | Default rules as in §3, including Superhuman as low effort | Only the FRD's examples | Cover Utsav's actual daily apps | Principal engineer; Superhuman added by Utsav |
| D23 | Second-level precision; weights 0/1/2/3; show 2 decimals; "equal" when the difference rounds to 0.00 | Minute buckets | Exact splits at session boundaries; weights and rounding from the architecture's proposal | Principal engineer; accepted by Utsav |
| D24 | A condition is unavailable only when it has 0 rated active seconds, and the reason is shown | A minimum observation time | FR7: no minimum period, never treat missing data as zero | Principal engineer; accepted by Utsav |
| D25 | Periods are inclusive local calendar days; presets Today (default), Last 7 days, custom | UTC days | Matches how Utsav thinks about a day | Principal engineer; accepted by Utsav |
| D26 | Collection gap = 10 minutes or more with no AFK data, listed per day, gaps during walks highlighted | Listing every gap of any length | Gaps during walks are the ones that skew results | Principal engineer; accepted by Utsav |
| D27 | Sessions can be deleted, with a confirm step on the dashboard | Edit-only sessions | An accidental Start can't be undone by editing times | Principal engineer; accepted by Utsav |
| D28 | When ActivityWatch is unreachable or a bucket is missing, the report fails with an explicit error; Start/Stop keep working | Returning empty results | FR7: missing data must never look like zero activity | Principal engineer; accepted by Utsav |
| D29 | Read activity live from ActivityWatch on every report and apply the rules at read time, so a rules edit also changes past results | Copying events into SQLite; freezing categories when first seen | One source of truth, nothing to sync; rule edits are how corrections are made (D14) | Principal engineer; accepted by Utsav |
| D30 | A single-page dashboard laid out as in UI / output, built in the order numbers, tables, charts | Multi-page dashboard; charts first | Fits the budget; protects correctness if time runs short (architecture R5) | Principal engineer |
| D31 | Test data is built inside the test files; the repository ships no data files | Separate fixture files | A public clone should contain only what runs against the user's own ActivityWatch; tests carry their own inputs | Utsav |
