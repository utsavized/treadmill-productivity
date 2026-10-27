"""Walking sessions in SQLite (spec Data model, API, Edge cases)."""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS walks (
  id         INTEGER PRIMARY KEY,
  started_at TEXT NOT NULL,
  ended_at   TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_walk ON walks ((ended_at IS NULL)) WHERE ended_at IS NULL;
"""


class WalkError(Exception):
    status = 400


class Conflict(WalkError):
    status = 409


class Invalid(WalkError):
    status = 422


class NotFound(WalkError):
    status = 404


@dataclass(frozen=True)
class Walk:
    id: int
    started_at: datetime
    ended_at: datetime | None

    def end_or(self, now: datetime) -> datetime:
        return self.ended_at or now

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }


def _to_db(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise Invalid("times must include a UTC offset")
    return dt.astimezone(UTC).isoformat()


def _from_db(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def _now() -> datetime:
    return datetime.now(UTC)


class WalkStore:
    def __init__(self, path: Path | str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)

    def all(self) -> list[Walk]:
        rows = self.db.execute("SELECT id, started_at, ended_at FROM walks").fetchall()
        return [Walk(i, _from_db(s), _from_db(e)) for i, s, e in rows]

    def get(self, walk_id: int) -> Walk:
        for w in self.all():
            if w.id == walk_id:
                return w
        raise NotFound(f"walking session {walk_id} not found")

    def open_walk(self) -> Walk | None:
        return next((w for w in self.all() if w.ended_at is None), None)

    def overlapping(self, start: datetime, end: datetime, now: datetime | None = None) -> list[Walk]:
        """Sessions overlapping [start, end), newest first. An open session runs to now."""
        now = now or _now()
        found = [w for w in self.all() if w.started_at < end and w.end_or(now) > start]
        return sorted(found, key=lambda w: w.started_at, reverse=True)

    def start(self, now: datetime | None = None) -> Walk:
        now = now or _now()
        if self.open_walk():
            raise Conflict("a walking session is already open")
        with self.db:
            cur = self.db.execute("INSERT INTO walks (started_at) VALUES (?)", (_to_db(now),))
        return self.get(cur.lastrowid)

    def stop(self, now: datetime | None = None) -> Walk:
        now = now or _now()
        walk = self.open_walk()
        if not walk:
            raise Conflict("no walking session is open")
        return self.update(walk.id, walk.started_at, now, now=now)

    def update(
        self, walk_id: int, started_at: datetime, ended_at: datetime | None, now: datetime | None = None
    ) -> Walk:
        now = now or _now()
        walk = self.get(walk_id)
        if ended_at is None and walk.ended_at is not None:
            raise Invalid("only the open session can have no end time")
        for dt in (started_at, ended_at):
            if dt is not None and dt.tzinfo is None:
                raise Invalid("times must include a UTC offset")
        end = ended_at or now
        if end <= started_at:
            raise Invalid("a session must end after it starts")
        if end > now:
            raise Invalid("a session can't end in the future")
        for other in self.all():
            if other.id != walk_id and other.started_at < end and other.end_or(now) > started_at:
                raise Invalid(f"overlaps walking session {other.id}")
        with self.db:
            self.db.execute(
                "UPDATE walks SET started_at = ?, ended_at = ? WHERE id = ?",
                (_to_db(started_at), _to_db(ended_at) if ended_at else None, walk_id),
            )
        return self.get(walk_id)

    def delete(self, walk_id: int) -> None:
        self.get(walk_id)
        with self.db:
            self.db.execute("DELETE FROM walks WHERE id = ?", (walk_id,))
