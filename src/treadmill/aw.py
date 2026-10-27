"""ActivityWatch REST client (spec Ingestion)."""

import socket
from datetime import UTC, datetime, timedelta

import httpx

from .classify import Interval, Segment

BASE_URL = "http://localhost:5600/api/0"


class AWError(Exception):
    """ActivityWatch can't be used; `code` is the API error (D28)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _parse_time(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _span(event: dict) -> tuple[datetime, datetime]:
    start = _parse_time(event["timestamp"])
    return start, start + timedelta(seconds=event["duration"])


def _period(start: datetime, end: datetime) -> str:
    return f"{start.astimezone(UTC).isoformat()}/{end.astimezone(UTC).isoformat()}"


class AWClient:
    def __init__(self, base_url: str = BASE_URL, transport: httpx.BaseTransport | None = None):
        self.http = httpx.Client(base_url=base_url, transport=transport, timeout=30)

    def _request(self, method: str, path: str, **kwargs):
        try:
            r = self.http.request(method, path, **kwargs)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise AWError(
                "activitywatch_unreachable",
                f"ActivityWatch isn't running or didn't respond at {self.http.base_url} ({e})",
            )

    def find_buckets(self) -> tuple[str, str]:
        """Return (window bucket id, afk bucket id)."""
        buckets = self._request("GET", "/buckets/").values()
        host = socket.gethostname()

        def pick(kind: str) -> str:
            found = [b for b in buckets if b.get("type") == kind]
            if not found:
                raise AWError("buckets_missing", f"ActivityWatch has no '{kind}' bucket; is its watcher running?")
            same_host = [b for b in found if b.get("hostname") in (host, host.split(".")[0] + ".local")]
            pool = same_host or found
            return max(pool, key=lambda b: b.get("last_updated") or "")["id"]

        return pick("currentwindow"), pick("afkstatus")

    def active_segments(self, window: str, afk: str, start: datetime, end: datetime) -> list[Segment]:
        """Window time intersected with not-AFK time (FR1)."""
        query = [
            f'window = flood(query_bucket("{window}"));',
            f'afk = flood(query_bucket("{afk}"));',
            'not_afk = filter_keyvals(afk, "status", ["not-afk"]);',
            "RETURN = filter_period_intersect(window, not_afk);",
        ]
        result = self._request("POST", "/query/", json={"timeperiods": [_period(start, end)], "query": query})
        events = result[0] if result else []
        return [
            Segment(*_span(e), e["data"].get("app", ""), e["data"].get("title", ""))
            for e in events
        ]

    def afk_intervals(self, afk: str, start: datetime, end: datetime) -> list[Interval]:
        """All AFK events, either status: when ActivityWatch was recording (FR7)."""
        events = self._request(
            "GET",
            f"/buckets/{afk}/events",
            params={"start": start.astimezone(UTC).isoformat(), "end": end.astimezone(UTC).isoformat(), "limit": -1},
        )
        return [Interval(*_span(e)) for e in events]
