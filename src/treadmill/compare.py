"""Comparison, explanation and coverage (spec §4, §5, §6)."""

from collections import defaultdict
from datetime import date, datetime, time, timedelta, tzinfo

from .classify import SITTING, WALKING, Interval, Segment, clip, label
from .effort import UNRATED, Rules
from .walks import Walk

CATEGORY_ORDER = ("high", "medium", "low", "none", UNRATED)
GAP_MIN_SECONDS = 600  # D26
EQUAL_BELOW = 0.005  # D23: "equal" when the difference rounds to 0.00


def period_bounds(start: date, end: date, tz: tzinfo) -> tuple[datetime, datetime]:
    """Inclusive local dates → [start of first day, start of the day after the last) (§6, D25)."""
    return (
        datetime.combine(start, time.min, tz),
        datetime.combine(end + timedelta(days=1), time.min, tz),
    )


def _merge(intervals: list[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    for iv in sorted(intervals, key=lambda i: i.start):
        if merged and iv.start <= merged[-1].end:
            merged[-1] = Interval(merged[-1].start, max(merged[-1].end, iv.end))
        else:
            merged.append(iv)
    return merged


def _condition(seconds_by_cat: dict[str, float], weights: dict[str, float], unavailable_if_empty: str | None):
    active = sum(seconds_by_cat.values())
    unrated = seconds_by_cat.get(UNRATED, 0.0)
    rated = active - unrated
    unavailable = unavailable_if_empty
    if unavailable is None:
        if active == 0:
            unavailable = "no_active_time"
        elif rated == 0:
            unavailable = "all_unrated"
    score = None
    if unavailable is None:
        score = sum(weights[c] * s for c, s in seconds_by_cat.items() if c != UNRATED) / rated
    return {"active_s": active, "rated_s": rated, "unrated_s": unrated, "score": score, "unavailable": unavailable}


def _coverage(afk: list[Interval], walks: list[Interval], start: datetime, end: datetime, tz: tzinfo):
    covered = [
        Interval(max(i.start, start), min(i.end, end)) for i in afk if min(i.end, end) > max(i.start, start)
    ]
    covered = _merge(covered)

    dates = set()
    for iv in covered:
        d = iv.start.astimezone(tz).date()
        while datetime.combine(d, time.min, tz) < iv.end:
            dates.add(d)
            d += timedelta(days=1)

    gaps = []
    cursor = start
    for iv in covered + [Interval(end, end)]:
        if (iv.start - cursor).total_seconds() >= GAP_MIN_SECONDS:
            during = any(w.start < iv.start and w.end > cursor for w in walks)
            gaps.append({"start": cursor.isoformat(), "end": iv.start.isoformat(), "during_walk": during})
        cursor = max(cursor, iv.end)

    return {"dates": [d.isoformat() for d in sorted(dates)], "gaps": gaps}


def build_report(
    *,
    segments: list[Segment],
    walks: list[Walk],
    afk: list[Interval],
    rules: Rules,
    start_date: date,
    end_date: date,
    tz: tzinfo,
    now: datetime,
) -> dict:
    ps, pe = period_bounds(start_date, end_date, tz)
    effective_end = max(ps, min(pe, now))  # §4 edge case: count only up to now

    walk_ivs = [Interval(w.started_at, w.end_or(now)) for w in walks]
    pieces = label(clip(segments, ps, effective_end), walk_ivs)

    by_cat = {WALKING: defaultdict(float), SITTING: defaultdict(float)}
    by_app = defaultdict(lambda: {WALKING: 0.0, SITTING: 0.0})
    for seg, cond in pieces:
        cat = rules.categorize(seg.app, seg.title)
        by_cat[cond][cat] += seg.seconds
        by_app[seg.app][cond] += seg.seconds

    has_sessions = any(w.start < effective_end and w.end > ps for w in walk_ivs)
    walking = _condition(by_cat[WALKING], rules.weights, None if has_sessions else "no_sessions")
    sitting = _condition(by_cat[SITTING], rules.weights, None)

    verdict = difference = None
    if walking["score"] is not None and sitting["score"] is not None:
        difference = walking["score"] - sitting["score"]
        if abs(difference) < EQUAL_BELOW:
            verdict = "equal"
        else:
            verdict = "higher" if difference > 0 else "lower"

    apps = sorted(by_app.items(), key=lambda kv: (-(kv[1][WALKING] + kv[1][SITTING]), kv[0]))

    return {
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "timezone": getattr(tz, "key", None) or str(tz),
        },
        "conditions": {WALKING: walking, SITTING: sitting},
        "verdict": verdict,
        "difference": difference,
        "categories": [
            {"category": c, "walking_s": by_cat[WALKING].get(c, 0.0), "sitting_s": by_cat[SITTING].get(c, 0.0)}
            for c in CATEGORY_ORDER
        ],
        "apps": [{"app": a, "walking_s": v[WALKING], "sitting_s": v[SITTING]} for a, v in apps],
        "coverage": _coverage(afk, walk_ivs, ps, effective_end, tz),
    }
