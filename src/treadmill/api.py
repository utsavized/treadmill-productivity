"""FastAPI routes and the dashboard server (spec API, UI / output)."""

import os
from datetime import UTC, date, datetime, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .aw import AWClient, AWError
from .compare import build_report, period_bounds
from .effort import RulesError, load_rules
from .walks import WalkError, WalkStore

ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).parent / "static"
HOST, PORT = "127.0.0.1", 8765


def local_tz() -> tzinfo:
    """The Mac's time zone, as a named zone so DST is handled across a period (D25)."""
    name = os.environ.get("TZ")
    if not name:
        try:
            link = os.readlink("/etc/localtime")
            name = link.split("zoneinfo/", 1)[1] if "zoneinfo/" in link else None
        except OSError:
            name = None
    try:
        return ZoneInfo(name) if name else datetime.now().astimezone().tzinfo
    except Exception:
        return datetime.now().astimezone().tzinfo


class WalkTimes(BaseModel):
    started_at: datetime
    ended_at: datetime | None


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, "message": message})


def create_app(
    store: WalkStore | None = None,
    aw: AWClient | None = None,
    rules_path: Path = ROOT / "config" / "categories.toml",
    tz: tzinfo | None = None,
    now=lambda: datetime.now(UTC),
) -> FastAPI:
    store = store or WalkStore(ROOT / "data" / "treadmill.db")
    aw = aw or AWClient()
    tz = tz or local_tz()
    app = FastAPI(title="Treadmill Productivity")

    @app.exception_handler(WalkError)
    def walk_error(request: Request, e: WalkError):
        code = {409: "conflict", 404: "not_found"}.get(e.status, "invalid")
        return _error(e.status, code, str(e))

    def check_dates(start: date, end: date):
        if start > end:
            return _error(422, "invalid_dates", "start date is after end date")

    @app.get("/api/status")
    def status():
        try:
            aw.find_buckets()
            aw_status = "ok"
        except AWError as e:
            aw_status = "unreachable" if e.code == "activitywatch_unreachable" else e.code
        open_walk = store.open_walk()
        return {"activitywatch": aw_status, "open_walk": open_walk.to_json() if open_walk else None}

    @app.get("/api/walks")
    def list_walks(start: date, end: date):
        if bad := check_dates(start, end):
            return bad
        ps, pe = period_bounds(start, end, tz)
        return [w.to_json() for w in store.overlapping(ps, pe, now=now())]

    @app.post("/api/walks/start")
    def start_walk():
        return store.start(now=now()).to_json()

    @app.post("/api/walks/stop")
    def stop_walk():
        return store.stop(now=now()).to_json()

    @app.patch("/api/walks/{walk_id}")
    def edit_walk(walk_id: int, body: WalkTimes):
        return store.update(walk_id, body.started_at, body.ended_at, now=now()).to_json()

    @app.delete("/api/walks/{walk_id}")
    def delete_walk(walk_id: int):
        store.delete(walk_id)
        return {"deleted": walk_id}

    @app.get("/api/report")
    def report(start: date, end: date):
        if bad := check_dates(start, end):
            return bad
        try:
            rules = load_rules(rules_path)
        except RulesError as e:
            return _error(422, "invalid_rules", str(e))
        t = now()
        ps, pe = period_bounds(start, end, tz)
        query_end = max(ps, min(pe, t))
        try:
            window, afk = aw.find_buckets()
            segments = aw.active_segments(window, afk, ps, query_end) if query_end > ps else []
            afk_ivs = aw.afk_intervals(afk, ps, query_end) if query_end > ps else []
        except AWError as e:
            return _error(503, e.code, e.message)
        result = build_report(
            segments=segments,
            walks=store.overlapping(ps, pe, now=t),
            afk=afk_ivs,
            rules=rules,
            start_date=start,
            end_date=end,
            tz=tz,
            now=t,
        )
        open_walk = store.open_walk()
        result["open_walk"] = open_walk.to_json() if open_walk else None
        return result

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    return app


def main():
    uvicorn.run(create_app(), host=HOST, port=PORT)
