"""AC7: walking sessions start, stop, edit, delete, and reject conflicts."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from treadmill.walks import Conflict, Invalid, NotFound, WalkStore

T0 = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


@pytest.fixture
def store():
    return WalkStore(":memory:")


def test_start_and_stop(store):
    w = store.start(now=at(0))
    assert w.ended_at is None
    assert store.open_walk() == w
    w = store.stop(now=at(30))
    assert (w.started_at, w.ended_at) == (at(0), at(30))
    assert store.open_walk() is None


def test_start_while_open_conflicts(store):
    store.start(now=at(0))
    with pytest.raises(Conflict):
        store.start(now=at(1))


def test_stop_without_open_conflicts(store):
    with pytest.raises(Conflict):
        store.stop(now=at(0))


def test_database_allows_one_open_session(store):
    store.start(now=at(0))
    with pytest.raises(Exception):
        with store.db:
            store.db.execute("INSERT INTO walks (started_at) VALUES ('2026-10-20T16:00:00+00:00')")


def test_edit_times(store):
    w = store.start(now=at(0))
    store.stop(now=at(30))
    w = store.update(w.id, at(5), at(25), now=at(60))
    assert (w.started_at, w.ended_at) == (at(5), at(25))


def test_stored_as_utc(store):
    local = at(0).astimezone(timezone(timedelta(hours=-5)))
    w = store.start(now=local)
    assert w.started_at == at(0)
    raw = store.db.execute("SELECT started_at FROM walks WHERE id = ?", (w.id,)).fetchone()[0]
    assert raw.endswith("+00:00")


@pytest.mark.parametrize(
    "start, end, reason",
    [
        (at(20), at(10), "end after it starts"),
        (at(10), at(10), "end after it starts"),
        (at(10), at(120), "future"),
        (at(40), at(70), "overlaps"),  # overlaps the second session
    ],
)
def test_invalid_edits(store, start, end, reason):
    first = store.start(now=at(0))
    store.stop(now=at(30))
    store.start(now=at(60))
    store.stop(now=at(90))
    with pytest.raises(Invalid, match=reason):
        store.update(first.id, start, end, now=at(100))


def test_edit_cannot_reopen_closed_session(store):
    w = store.start(now=at(0))
    store.stop(now=at(30))
    with pytest.raises(Invalid):
        store.update(w.id, at(0), None, now=at(40))


def test_open_session_overlap_runs_to_now(store):
    closed = store.start(now=at(0))
    store.stop(now=at(10))
    store.start(now=at(20))  # open, runs to now
    with pytest.raises(Invalid, match="overlaps"):
        store.update(closed.id, at(0), at(25), now=at(40))


def test_naive_times_rejected(store):
    w = store.start(now=at(0))
    store.stop(now=at(10))
    with pytest.raises(Invalid, match="offset"):
        store.update(w.id, datetime(2026, 10, 20, 15, 0), at(10), now=at(20))


def test_delete(store):
    w = store.start(now=at(0))
    store.delete(w.id)
    assert store.all() == []
    with pytest.raises(NotFound):
        store.delete(w.id)


def test_overlapping_newest_first(store):
    a = store.start(now=at(0))
    store.stop(now=at(10))
    b = store.start(now=at(20))
    store.stop(now=at(30))
    store.start(now=at(200))
    store.stop(now=at(210))
    assert [w.id for w in store.overlapping(at(5), at(25), now=at(300))] == [b.id, a.id]
