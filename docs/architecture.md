# Treadmill Productivity: building blocks
Version: v4 · Test data lives inside the tests (D31)

Platform: macOS, Microsoft Edge as main browser (D16).

## Overview

```
ActivityWatch (background, on the Mac)
  ├─ aw-watcher-window  → front app + window title
  └─ aw-watcher-afk     → active vs idle (3 min without input)
          │  REST API, localhost:5600
          ▼
treadmill app (Python, FastAPI, localhost only)
  ├─ walk sessions: Start / Stop buttons → SQLite in data/   → FR2
  ├─ pull window events, keep only not-AFK time               → FR1
  ├─ label each active minute walking / assumed sitting       → FR3
  ├─ map app/title → effort category via rules file           → FR4
  └─ compare, explain, coverage                               → FR5–FR7
          │
          ▼
Dashboard in the browser at http://localhost:8765            → FR5–FR7
```

Nothing leaves the machine. No accounts, no cloud (FR8).

## Data sources

### Computer activity: ActivityWatch (D11)
- **Provides.** `currentwindow` events with `app` and `title`; `afkstatus` events with `status` = `afk` / `not-afk`. Every event is `{timestamp, duration (s), data}`.
- **How we get it.** REST API at `http://localhost:5600/api/0/`, no auth by default. `GET /buckets/` for bucket ids, then `POST /query/`; its `filter_period_intersect` keeps only window time overlapping not-AFK time.
- **Idle rule.** Built in: 3 minutes without mouse/keyboard input = AFK. Passive video becomes idle, which Utsav accepted since video scores 0 anyway (D15).
- **Edge.** The docs only promise URL capture from the window watcher for Chrome-family browsers and Safari; Edge isn't named, so we don't rely on it. Default rules match on **window title**, which Edge always exposes (e.g. "… - YouTube", "Claude", "ChatGPT"). The official aw-watcher-web browser extension can add exact URLs later if titles prove too coarse; not in the MVP (C5).
- **Limitations.** Timestamps are UTC with the offset discarded, so we display in local time ourselves. Gaps in the AFK bucket mean ActivityWatch wasn't running or the Mac was asleep, which gives FR7 its collection-gap signal.
- **Sources.** [Data model](https://docs.activitywatch.net/en/latest/buckets-and-events.html) · [REST API](https://docs.activitywatch.net/en/latest/api/rest.html) · [Watchers, 3-min AFK default](https://docs.activitywatch.net/en/latest/watchers.html) · [Query functions](https://docs.activitywatch.net/en/latest/examples/working-with-data.html)

### Walking sessions: manual Start / Stop (D12)
- **Provides.** One row per session: `id, started_at, ended_at` (aware UTC), stored in `data/treadmill.db`.
- **How we get it.** Start and Stop buttons on the dashboard, plus `POST /api/walks/start` and `/stop` so a shortcut or keyboard macro can hit them later.
- **Limitation.** A forgotten Stop inflates walking time; a forgotten Start counts a walk as sitting. The dashboard shows an open session prominently and lets Utsav edit a session's times. The spec decides whether a long AFK stretch auto-closes an open session.
- **Why not Apple Health.** HealthKit can't be read on macOS (`isHealthDataAvailable()` returns `false`, [Apple DTS](https://developer.apple.com/forums/thread/798780)). Exporting a zip from the iPhone each time is as much effort as pressing Start/Stop, and an iOS app is outside the budget.

### Evaluated and deferred: KingSmith WalkingPad Z1 over Bluetooth
Goal: detect belt start/stop automatically from the Mac.

- **It's possible in principle.** An open-source project controls and reads a Z1 from a Mac over Bluetooth LE. The pad speaks the standard Fitness Machine Service (FTMS `0x1826`, treadmill data `0x2ACD`, machine status `0x2ADA`), giving live speed, distance, time and steps. It has a Python/bleak CLI and a Swift menu-bar app. [slandau3/z1-walkingpad-mcp](https://github.com/slandau3/z1-walkingpad-mcp) (MIT)
- **But it isn't a passive listener.** The pad sends no telemetry until a connected client completes a reverse-engineered unlock handshake. And it **accepts only one Bluetooth connection at a time**, so the Mac would replace the KingSmith phone app while you walk, not listen alongside it. The older [ph4-walkingpad](https://github.com/ph4r05/ph4-walkingpad) library documents the same one-connection limit on other models.
- **Other risks.** Tested on one Z1 variant (KS-HD-Z1D, firmware V0.0.6); a firmware update could break the unlock. It needs a background process holding the connection, reconnect handling, and macOS Bluetooth permission.
- **Verdict.** Doesn't fit the three-hour MVP; deferred (D18). Good next-round candidate: because sessions are just rows in `walks`, a Bluetooth watcher would only write the same rows. Suggested first step after the MVP: a 30-minute spike in `spikes/` running that project's CLI against your pad, to see whether telemetry arrives on your firmware and whether you can live without the phone app while walking.

## Stack (D17)

| Block | Choice | Why |
|---|---|---|
| Language | Python 3.12 | One language for data logic, tests, and a later Bluetooth watcher (the Z1 work above is Python/bleak) |
| Web server | FastAPI + uvicorn, bound to `127.0.0.1` | Small, typed JSON API; serves the static dashboard too |
| Dashboard | One static page: HTML + vanilla JS + Chart.js (vendored file, no CDN) | A few tables, bars and two buttons don't need React or a Node build step |
| Storage | SQLite via stdlib `sqlite3`, `data/treadmill.db` | Walk sessions only; activity is read live from ActivityWatch |
| Effort rules | `config/categories.toml`, read with `tomllib` | Editable defaults and overrides without a UI (C1) |
| ActivityWatch client | `httpx` against the REST API | One local endpoint |
| Tests | `pytest`, ActivityWatch events built as test data inside the tests | Verification without waiting for real data |
| Packaging | `uv` (or plain `venv` + `pip`), `pyproject.toml` | One command to install and run |

**Why not Node + React?** It works fine, and the ActivityWatch side is just HTTP either way. But it adds a second language and a build toolchain for a dashboard of a few tables and charts. And if the Bluetooth watcher happens later, Mac BLE is better supported in Python (bleak) than Node.

Suggested layout:

```
treadmill-productivity/
  pyproject.toml
  config/categories.toml
  src/treadmill/
    aw.py          ActivityWatch client + not-AFK intersection
    walks.py       session storage and start/stop
    classify.py    walking vs assumed sitting
    effort.py      rule matching and weights
    compare.py     FR5–FR7 calculations
    api.py         FastAPI routes
    static/        index.html, app.js, chart.min.js
  tests/
  data/            git-ignored: treadmill.db
```

## Proposed calculation inputs (for the spec to pin down)
- **Weights:** none = 0, low = 1, medium = 2, high = 3. Estimated productivity = Σ(weight × active minutes) ÷ rated active minutes, per condition.
- **Unrated activity:** excluded from the average, shown as its own row in minutes and %.
- **Rounding:** compute at full precision, display to 2 decimals; "equal" means the difference rounds to 0.00.
- **Rule matching:** first match wins, title then app; unmatched is unrated.

## Local setup (what Utsav does)
1. Install ActivityWatch, launch it, grant Accessibility and Screen Recording when macOS asks. Check `http://localhost:5600` shows activity, including Edge window titles.
2. Install the app (`uv sync`), run it (`uv run treadmill`), open `http://localhost:8765`.
3. Press Start when you step on the treadmill and Stop when you step off.

## Feasibility against the 3-hour budget

| Piece | Est. |
|---|---|
| ActivityWatch client + not-AFK intersection | 25 min |
| Walk sessions: SQLite, start/stop/edit API | 20 min |
| Condition labelling (walking / assumed sitting) | 15 min |
| Category rules + defaults | 20 min |
| Comparison, breakdowns, within-app/category, coverage and unavailable states | 45 min |
| Dashboard (tables, bars, start/stop) | 40 min |
| Test data + tests + verification session | 25 min |
| **Total** | **~3 h 10 min** |

Verdict: **feasible, at the edge of the budget.** Keeping the dashboard (D13) uses the time freed by dropping Apple Health. If the build runs long, the order to protect is: correct numbers and unavailable states first, tables second, charts last.

### Cuts
- **C1. No correction UI.** Overrides are rules in `categories.toml`. Accepted (D14).
- **C2. No Apple Health.** Superseded by D12.
- **C3. Static report instead of dashboard.** Rejected; dashboard kept (D13).
- **C4. Manual start/stop dropped.** Reversed; manual is now the only walk source (D12).
- **C5. No browser extension.** Accepted; title rules for Edge (D14).
- **C6. No Bluetooth treadmill integration.** Deferred to a future round (D18).

## Risks
- **R1. Forgotten Start/Stop.** Directly skews the comparison. Mitigation: open session shown prominently, sessions editable, optional auto-close rule in the spec.
- **R2. Video under-counted.** Accepted (D15). The dashboard states it next to the indicator.
- **R3. Title rules too coarse for Edge.** Some tabs may land in unrated. Unrated is shown, not hidden; aw-watcher-web can add URLs later.
- **R4. Time zones.** ActivityWatch is UTC; walk sessions stored as aware UTC; display in local time.
- **R5. Budget overrun.** Hold the cuts; charts are the first thing to trim.

## Open questions
None. Building blocks are settled; next step is `docs/spec.md` with the `principal-engineer`.

## Decisions

| # | Decision | Rejected alternatives | Why | Raised by |
|---|---|---|---|---|
| D11 | Use ActivityWatch for app and idle tracking | Writing our own collector | Already covers FR1 locally; it's the tool Utsav had in mind | Solutions architect; accepted by Utsav |
| D12 | Record walking sessions with manual Start/Stop in the local web app | Apple Health export import; iPhone app with HealthKit | HealthKit isn't readable on macOS; exporting a zip is as much effort as Start/Stop; an iOS app doesn't fit the budget | Utsav |
| D13 | Keep a local web dashboard in the MVP | Static generated HTML report (C3) | It's a thin layer once the data exists, and much more usable | Utsav |
| D14 | Accept cuts C1 (no correction UI) and C5 (no browser extension) | Correction screen; aw-watcher-web from day one | Protect the three-hour budget | Solutions architect; accepted by Utsav |
| D15 | Treat passive video as idle | Raising the AFK threshold; audible-tab detection | Video scores 0 anyway; keeps idle detection stock | Utsav |
| D16 | Target macOS with Edge as the main browser | Cross-platform support | That's Utsav's setup | Utsav |
| D17 | Python 3.12 + FastAPI, a vanilla JS + Chart.js dashboard, SQLite for walk sessions | Node + React | One language for logic, tests and a future Bluetooth watcher; no build step for a small dashboard | Solutions architect; accepted by Utsav |
| D18 | Defer KingSmith Z1 Bluetooth integration to a future round | Build it into the MVP | Needs an active connection with a reverse-engineered unlock, displaces the phone app, firmware-specific | Solutions architect; accepted by Utsav |
