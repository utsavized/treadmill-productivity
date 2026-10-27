"""AC7, AC8 and AC4 through the API, with a stub ActivityWatch and test data."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from treadmill.api import create_app
from treadmill.aw import AWError
from treadmill.classify import Interval, Segment
from treadmill.walks import WalkStore

TZ = ZoneInfo("America/Chicago")
NOW = datetime(2026, 10, 20, 12, tzinfo=TZ).astimezone(UTC)


class StubAW:
    def __init__(self, down: str | None = None):
        self.down = down

    def find_buckets(self):
        if self.down:
            raise AWError(self.down, "stub: ActivityWatch is down")
        return "w", "a"

    def active_segments(self, window, afk, start, end):
        return [Segment(NOW - timedelta(hours=2), NOW, "Code", "x")]

    def afk_intervals(self, afk, start, end):
        return [Interval(start, end)]


def make_client(aw=None, rules_path=None):
    kwargs = {"rules_path": rules_path} if rules_path else {}
    clock = {"now": NOW}
    app = create_app(store=WalkStore(":memory:"), aw=aw or StubAW(), tz=TZ, now=lambda: clock["now"], **kwargs)
    return TestClient(app), clock


def test_report_and_walk_lifecycle():
    c, clock = make_client()
    clock["now"] = NOW - timedelta(hours=1)
    assert c.post("/api/walks/start").status_code == 200
    assert c.post("/api/walks/start").status_code == 409
    clock["now"] = NOW - timedelta(minutes=30)
    w = c.post("/api/walks/stop").json()
    assert c.post("/api/walks/stop").status_code == 409
    clock["now"] = NOW

    r = c.get("/api/report", params={"start": "2026-10-20", "end": "2026-10-20"}).json()
    assert r["conditions"]["walking"]["active_s"] == 1800
    assert r["conditions"]["sitting"]["active_s"] == 5400
    assert r["verdict"] == "equal"  # all Code (D19: same category scores the same)
    assert r["open_walk"] is None
    assert r["period"]["timezone"] == "America/Chicago"

    walks = c.get("/api/walks", params={"start": "2026-10-20", "end": "2026-10-20"}).json()
    assert [x["id"] for x in walks] == [w["id"]]


def test_edit_and_delete():
    c, clock = make_client()
    clock["now"] = NOW - timedelta(hours=1)
    w = c.post("/api/walks/start").json()
    clock["now"] = NOW
    c.post("/api/walks/stop")
    ok = c.patch(f"/api/walks/{w['id']}", json={
        "started_at": (NOW - timedelta(minutes=50)).isoformat(),
        "ended_at": (NOW - timedelta(minutes=10)).isoformat(),
    })
    assert ok.status_code == 200
    bad = c.patch(f"/api/walks/{w['id']}", json={
        "started_at": (NOW - timedelta(minutes=10)).isoformat(),
        "ended_at": (NOW - timedelta(minutes=50)).isoformat(),
    })
    assert bad.status_code == 422 and bad.json()["error"] == "invalid"
    assert c.delete(f"/api/walks/{w['id']}").status_code == 200
    assert c.delete(f"/api/walks/{w['id']}").status_code == 404


@pytest.mark.parametrize("code", ["activitywatch_unreachable", "buckets_missing"])
def test_activitywatch_down(code):
    c, clock = make_client(aw=StubAW(down=code))
    r = c.get("/api/report", params={"start": "2026-10-20", "end": "2026-10-20"})
    assert r.status_code == 503
    assert r.json()["error"] == code
    status = c.get("/api/status").json()
    assert status["activitywatch"] == ("unreachable" if code == "activitywatch_unreachable" else code)
    # Start/Stop keep working (D28)
    assert c.post("/api/walks/start").status_code == 200
    assert c.get("/api/status").json()["open_walk"] is not None
    clock["now"] = NOW + timedelta(minutes=5)
    assert c.post("/api/walks/stop").status_code == 200


def test_invalid_rules_file(tmp_path):
    p = tmp_path / "bad.toml"
    p.write_text("[weights]\nnone = 0\n")
    c, _ = make_client(rules_path=p)
    r = c.get("/api/report", params={"start": "2026-10-20", "end": "2026-10-20"})
    assert r.status_code == 422
    assert r.json()["error"] == "invalid_rules"
    assert "[weights]" in r.json()["message"]


def test_bad_dates():
    c, _ = make_client()
    assert c.get("/api/report", params={"start": "2026-10-21", "end": "2026-10-20"}).status_code == 422
    assert c.get("/api/report", params={"start": "nope", "end": "2026-10-20"}).status_code == 422
