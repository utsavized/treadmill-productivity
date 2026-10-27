# Treadmill Productivity: functional requirements
Version: v5 · Verification uses test data built inside the tests

## Problem
Utsav wants to understand whether working while walking is associated with higher or lower estimated productivity, with minimal manual tracking. Activity choice may explain differences and is itself useful information.

## The question this product answers
During recorded walking sessions, is estimated productivity higher or lower than during ordinary computer use? What differences in activity mix accompany that result, including within comparable activities?

The MVP makes effort-based comparisons from available data. It does not establish causation or directly measure completed work or its quality.

## Users and context
- Initially one user: Utsav, working on a Mac (primary browser: Microsoft Edge) with a walking treadmill.
- Observe normal work; no prescribed walking/sitting experiment is required.
- The user chooses the observation duration and reporting period: one day, months, or longer.
- Delivery target: implemented and ready to use within a maximum three-hour build budget, using role-based agents rather than Utsav coding manually. Collecting an experiment's data is not part of that budget or a prerequisite for acceptance.
- Feasibility is assessed in `docs/architecture.md`: the MVP fits the budget with the scope below. Utsav makes final calls on changes to scope or direction.

## Functional requirements
**FR1 — Collect activity.** Automatically record app usage, timestamps, and active duration. Distinguish idle time from active use and exclude idle time from effort calculations.

**FR2 — Track walking sessions.** The user starts and stops each walking session manually from the local app. Record session start/end times, align them with computer activity, and let the user see and fix an open or mistimed session. Automatic detection (Apple Health, treadmill Bluetooth) is deferred (D12, D18).

**FR3 — Classify working conditions.** Treat active computer use outside recorded walking sessions as sitting by assumption. Make this assumption visible. Missing walking records can misclassify activity; missing computer activity must not become measured sitting time.

**FR4 — Assign effort.** Apply configurable default categories to app activity. Allow optional corrections without requiring daily review. Defaults are estimates and may not capture the intent of a particular task.

**FR5 — Compare estimated productivity.** For a user-selected period, compare average effort per active minute between walking and assumed-sitting activity. Report whether this indicator is higher, lower, or equal while walking. Define numerical weights, treatment of unrated activity, and rounding before implementation.

**FR6 — Explain results.** Show total active time, time in each effort category, and app activity mix for both conditions alongside the indicator. Support comparisons within the same app or effort category so the user can inspect whether differences reflect task choice.

**FR7 — Show coverage and missing data.** Use whatever data is available; no minimum observation period is required. Show dates covered and active duration in each condition, including when only one day is recorded. If either condition lacks usable data, explain why its comparison cannot be calculated. Do not treat missing data as zero productivity. Expose collection gaps where detectable.

**FR8 — Keep personal data local.** Store personal activity and health data locally. Never commit real activity logs, health exports, or tokens to the repository. Verification uses test data built inside the tests; the repository ships no data files.

**FR9 — Local dashboard.** Present FR5–FR7 results and the walking-session controls in a dashboard that runs locally and is viewed in the browser (D13).

## Definitions
- **No effort:** Default for watching videos and general web browsing.
- **Low effort:** Default for email.
- **Medium effort:** Default for collaboration with Claude or OpenAI tools.
- **High effort:** Default for VS Code and DaVinci Resolve.
- **Estimated productivity:** An indicator based on the assigned effort rating averaged over active time. Higher means greater estimated effort intensity, not necessarily more useful output.
- **Activity mix:** The distribution of active computer time across apps or effort categories.
- **Idle:** The computer is on but the user has given no keyboard or mouse input for 3 minutes. Passive video viewing therefore counts as idle; this is accepted because video carries no effort (D15).
- **Sitting:** Active computer use outside recorded walking sessions; actual posture is not independently verified.
- **Walking session:** A period between the user pressing Start and Stop. A walk without a recorded session counts as sitting.
- **Comparable activity:** For the MVP, activity grouped by the same app or effort category. This does not guarantee equally difficult tasks.

## Out of scope
- A required experiment duration, data volume, or particular experimental outcome.
- Proving that walking causes productivity changes.
- Objective assessment of work quality, completed output, or biological mechanisms.
- A separate focus score for the initial version.
- Multi-user functionality.
- Selecting technology in the FRD (see `docs/architecture.md`).
- Automatic walking detection from Apple Health or the treadmill's Bluetooth, for this round.
- A screen for correcting individual activity; corrections are made by editing category rules.
- Platforms other than macOS.

## Success criteria
- A working MVP is implemented and ready to use within the three-hour build budget.
- A verification session demonstrates activity capture, effort assignment, walking-session alignment, and the default sitting classification.
- Comparisons calculate correctly when both conditions have usable data, including within a single recorded day.
- Results show the underlying activity mix, active duration, coverage, and calculation definition.
- Empty and one-sided datasets produce clear unavailable-comparison states rather than misleading scores.
- Routine collection requires no daily review. Starting and stopping walking sessions is the only recurring user action.
- Verification does not require waiting for a month of real observations.

## Open questions
None at the requirements level. The architect's research answered the v3 questions in `docs/architecture.md`: ActivityWatch for activity and idle (D11), manual walking sessions (D12), macOS with Edge (D16), and a feasibility estimate of about three hours. Numerical weights, unrated handling and rounding are proposed there and pinned down in `docs/spec.md`.

## Decisions

| # | Decision | Rejected alternatives | Why | Raised by |
|---|---|---|---|---|
| D1 | Observe normal work patterns | Prescribed comparable sessions | Natural activity choices are themselves useful findings | Utsav |
| D2 | Include activity-mix comparisons | Rely only on one aggregate score | Different tasks could explain apparent differences | Utsav |
| D3 | Cap the initial build at three hours using agents | Larger initial build | Keep this a small, exploratory project | Utsav |
| D4 | Support any observation duration | Month-level reporting as an acceptance requirement | Reverses the v1 draft success criterion; experiment duration belongs to the user | Utsav |
| D5 | Use four configurable effort categories | Required daily manual scoring | Provide useful defaults with minimal burden | Utsav |
| D6 | Assume sitting outside recorded walking sessions | Require explicit sitting-session tracking | Reduce manual tracking | Utsav |
| D7 | Prefer automatic walking records, with manual controls as fallback | Require Apple Health integration regardless of complexity | Protect the three-hour delivery budget | Utsav |
| D8 | Compare average effort per active minute alongside duration and category breakdowns | Use total accumulated effort as the main comparison | Avoid automatically favoring longer sessions; numerical details require research | Product manager; accepted by Utsav |
| D9 | Hand implementation feasibility questions to the architect and iterate on scope afterward | Require Utsav to settle collection and scoring details during the FRD phase | Establish the MVP target now and resolve technical feasibility through research | Utsav |
| D10 | Omit a separate focus score from the initial version | Infer focus directly from app switching | Switching can represent useful work or distraction | Product manager; accepted by Utsav |

