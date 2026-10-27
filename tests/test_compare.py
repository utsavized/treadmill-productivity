"""AC1–AC3, AC5, AC6, AC9: comparison, splitting, unavailable states, coverage, midnight."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from treadmill.classify import Interval, Segment
from treadmill.compare import build_report
from treadmill.effort import load_rules
from treadmill.walks import Walk

ROOT = Path(__file__).parents[1]
RULES = load_rules(ROOT / "config" / "categories.toml")
TZ = ZoneInfo("America/Chicago")
DAY = date(2026, 10, 20)
LATER = datetime(2026, 11, 1, tzinfo=UTC)


def local(h: int, m: int = 0, day: date = DAY) -> datetime:
    return datetime(day.year, day.month, day.day, h, m, tzinfo=TZ)


def seg(a: datetime, b: datetime, app: str, title: str = "") -> Segment:
    return Segment(a, b, app, title)


def walk(i: int, a: datetime, b: datetime | None) -> Walk:
    return Walk(i, a, b)


def report(segments=(), walks=(), afk=(), start=DAY, end=DAY, now=LATER):
    return build_report(
        segments=list(segments), walks=list(walks), afk=list(afk), rules=RULES,
        start_date=start, end_date=end, tz=TZ, now=now,
    )


def worked_example():
    """The worked example in docs/spec.md §4. Segments are already not-AFK, as ActivityWatch returns them,
    so the AFK stretch 11:45–12:15 has no segment."""
    segments = [
        seg(local(9), local(10, 30), "Code", "compare.py - treadmill-productivity"),
        seg(local(10, 30), local(11), "Microsoft Edge", "A talk - YouTube"),
        seg(local(11), local(11, 30), "Superhuman", "Inbox"),
        seg(local(11, 30), local(11, 45), "Notion", "Notes"),
    ]
    walks = [walk(1, local(10), local(11))]
    afk = [Interval(local(9), local(12, 15))]
    return segments, walks, afk


def by_cat(r):
    return {c["category"]: (c["walking_s"], c["sitting_s"]) for c in r["categories"]}


# AC1, AC2
def test_worked_example():
    r = report(*worked_example())
    w, s = r["conditions"]["walking"], r["conditions"]["sitting"]
    assert round(w["score"], 2) == 1.50
    assert round(s["score"], 2) == 2.33
    assert s["unrated_s"] == 15 * 60
    assert w["unrated_s"] == 0
    assert r["verdict"] == "lower"
    assert round(r["difference"], 2) == -0.83
    # The Code event 09:00–10:30 is split at Start: 60 min sitting, 30 min walking
    assert by_cat(r)["high"] == (30 * 60, 60 * 60)
    assert by_cat(r)["none"] == (30 * 60, 0)
    assert by_cat(r)["low"] == (0, 30 * 60)
    assert w["active_s"] == 60 * 60 and s["active_s"] == 105 * 60
    assert r["apps"][0] == {"app": "Code", "walking_s": 1800, "sitting_s": 3600}
    assert r["coverage"]["dates"] == ["2026-10-20"]


def test_split_to_the_second():
    start = local(10, 0) + timedelta(seconds=17)
    r = report([seg(local(9), local(11), "Code")], [walk(1, start, local(12))])
    assert by_cat(r)["high"] == (3600 - 17, 3600 + 17)


# AC3
def test_no_sessions():
    r = report([seg(local(9), local(10), "Code")])
    assert r["conditions"]["walking"]["unavailable"] == "no_sessions"
    assert r["conditions"]["walking"]["score"] is None
    assert r["conditions"]["sitting"]["score"] == 3
    assert r["verdict"] is None and r["difference"] is None


def test_empty_period():
    r = report()
    assert r["conditions"]["walking"]["unavailable"] == "no_sessions"
    assert r["conditions"]["sitting"]["unavailable"] == "no_active_time"
    assert r["verdict"] is None


def test_session_without_active_time():
    r = report([seg(local(9), local(10), "Code")], [walk(1, local(11), local(12))])
    assert r["conditions"]["walking"]["unavailable"] == "no_active_time"


def test_walking_all_unrated():
    r = report(
        [seg(local(9), local(10), "Code"), seg(local(10), local(11), "Notion")],
        [walk(1, local(10), local(11))],
    )
    assert r["conditions"]["walking"]["unavailable"] == "all_unrated"
    assert r["conditions"]["walking"]["unrated_s"] == 3600
    assert r["verdict"] is None


def test_open_session_counts_to_now():
    now = local(10, 30).astimezone(UTC)
    r = report([seg(local(9), local(11), "Code")], [walk(1, local(10), None)], now=now)
    assert by_cat(r)["high"] == (1800, 3600)  # nothing after now


# AC5
@pytest.mark.parametrize(
    "walk_minutes, expected",
    [
        # sitting: 1000 min high (3.0). walking: high + 1 min low → 3 - 2/n
        (401, "equal"),   # 3 - 2/401 = 2.99501 → diff -0.00499
        (399, "lower"),   # 3 - 2/399 = 2.99499 → diff -0.00501
    ],
)
def test_equal_threshold(walk_minutes, expected):
    w0 = local(0, 0)
    w_end = w0 + timedelta(minutes=walk_minutes)
    segs = [
        seg(w0, w_end - timedelta(minutes=1), "Code"),
        seg(w_end - timedelta(minutes=1), w_end, "Superhuman"),
        seg(w_end, w_end + timedelta(minutes=1000), "Code"),
    ]
    r = report(segs, [walk(1, w0, w_end)])
    assert r["verdict"] == expected


# AC6
def test_gaps():
    afk = [
        Interval(local(0), local(9)),
        # 9:00–9:10 missing: 10 min → reported, overlaps the walk
        Interval(local(9, 10), local(12)),
        # 12:00–12:09 missing: 9 min → not reported
        Interval(local(12, 9), local(0, day=DAY + timedelta(days=1))),
    ]
    r = report(afk=afk, walks=[walk(1, local(8, 30), local(9, 5))])
    gaps = r["coverage"]["gaps"]
    assert len(gaps) == 1
    assert datetime.fromisoformat(gaps[0]["start"]) == local(9)
    assert datetime.fromisoformat(gaps[0]["end"]) == local(9, 10)
    assert gaps[0]["during_walk"] is True


def test_gap_outside_walk_and_up_to_now():
    now = local(15).astimezone(UTC)
    r = report(afk=[Interval(local(0), local(14))], now=now)
    gaps = r["coverage"]["gaps"]
    assert len(gaps) == 1
    assert datetime.fromisoformat(gaps[0]["end"]) == local(15)  # stops at now, not midnight
    assert gaps[0]["during_walk"] is False


# AC9
def test_session_across_midnight():
    next_day = DAY + timedelta(days=1)
    segs = [seg(local(23), local(1, day=next_day), "Code")]
    walks = [walk(1, local(23, 30), local(0, 30, day=next_day))]
    day1 = report(segs, walks, start=DAY, end=DAY)
    day2 = report(segs, walks, start=next_day, end=next_day)
    both = report(segs, walks, start=DAY, end=next_day)
    assert by_cat(day1)["high"] == (1800, 1800)
    assert by_cat(day2)["high"] == (1800, 1800)
    assert by_cat(both)["high"] == (3600, 3600)


def test_period_uses_local_days():
    # 23:30 local on Oct 20 is 04:30 UTC on Oct 21; it belongs to Oct 20 locally
    r = report([seg(local(23, 30), local(23, 45), "Code")])
    assert r["conditions"]["sitting"]["active_s"] == 900
