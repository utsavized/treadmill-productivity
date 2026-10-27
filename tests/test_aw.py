"""AC8 (client side) and ActivityWatch parsing, with a mocked transport and test data."""

import json
from datetime import UTC, datetime

import httpx
import pytest

from treadmill.aw import AWClient, AWError

START = datetime(2026, 10, 20, 5, tzinfo=UTC)
END = datetime(2026, 10, 21, 5, tzinfo=UTC)

BUCKETS = {
    "aw-watcher-window_old": {"id": "aw-watcher-window_old", "type": "currentwindow", "hostname": "old", "last_updated": "2025-01-01T00:00:00+00:00"},
    "aw-watcher-window_new": {"id": "aw-watcher-window_new", "type": "currentwindow", "hostname": "new", "last_updated": "2026-10-20T00:00:00+00:00"},
    "aw-watcher-afk_new": {"id": "aw-watcher-afk_new", "type": "afkstatus", "hostname": "new", "last_updated": "2026-10-20T00:00:00+00:00"},
}


def client(handler) -> AWClient:
    return AWClient(base_url="http://aw.test/api/0", transport=httpx.MockTransport(handler))


def test_unreachable():
    def down(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(AWError) as e:
        client(down).find_buckets()
    assert e.value.code == "activitywatch_unreachable"


def test_buckets_missing():
    only_window = {k: v for k, v in BUCKETS.items() if v["type"] == "currentwindow"}
    with pytest.raises(AWError) as e:
        client(lambda r: httpx.Response(200, json=only_window)).find_buckets()
    assert e.value.code == "buckets_missing"


def test_picks_latest_bucket_when_host_differs():
    assert client(lambda r: httpx.Response(200, json=BUCKETS)).find_buckets() == (
        "aw-watcher-window_new",
        "aw-watcher-afk_new",
    )


def test_active_segments_sends_not_afk_intersection():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json=[[{"timestamp": "2026-10-20T14:00:00.000000", "duration": 90.5, "data": {"app": "Code", "title": "x"}}]],
        )

    segs = client(handler).active_segments("w", "a", START, END)
    query = "\n".join(seen["body"]["query"])
    assert 'filter_keyvals(afk, "status", ["not-afk"])' in query
    assert "filter_period_intersect(window, not_afk)" in query
    assert seen["body"]["timeperiods"] == ["2026-10-20T05:00:00+00:00/2026-10-21T05:00:00+00:00"]
    assert segs[0].start == datetime(2026, 10, 20, 14, tzinfo=UTC)  # no offset → UTC
    assert segs[0].seconds == 90.5
    assert (segs[0].app, segs[0].title) == ("Code", "x")


def test_afk_intervals():
    def handler(request):
        assert request.url.path == "/api/0/buckets/a/events"
        assert request.url.params["limit"] == "-1"
        return httpx.Response(200, json=[{"timestamp": "2026-10-20T14:00:00+00:00", "duration": 60, "data": {"status": "afk"}}])

    (iv,) = client(handler).afk_intervals("a", START, END)
    assert (iv.end - iv.start).total_seconds() == 60
