"""Operational entry point for the durable recording-analysis worker."""
from __future__ import annotations

import argparse
import json
import signal
from threading import Event
from uuid import uuid4

from sqlalchemy import text

from app.analysis_worker import build_worker
from app.core import settings
from app.db import SessionLocal
from app.main import get_object_storage


def healthcheck() -> dict[str, object]:
    """Check local dependencies only; never calls paid providers."""
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok", "component": "analysis-worker"}


def run(*, once: bool, worker_id: str | None = None, stop: Event | None = None) -> int:
    """Poll durable jobs until asked to stop, finishing at most one active job."""
    stop = stop or Event()
    identity = worker_id or f"analysis-{uuid4()}"
    with SessionLocal() as db:
        worker = build_worker(db, get_object_storage(), settings)
        while not stop.is_set():
            processed = worker.run_once(identity)
            if once:
                return 0
            if not processed:
                stop.wait(settings.analysis_worker_poll_seconds)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Oratry durable analysis jobs")
    parser.add_argument("--once", action="store_true", help="claim and process at most one job, then exit")
    parser.add_argument("--health", action="store_true", help="check database reachability without provider calls")
    parser.add_argument("--worker-id", help="stable process label; each claim is fenced by its unique lease")
    args = parser.parse_args()
    if args.health:
        print(json.dumps(healthcheck(), separators=(",", ":")))
        return 0
    stop = Event()

    def request_stop(*_: object) -> None:
        # The current provider call is allowed to complete; no new job begins.
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)
    return run(once=args.once, worker_id=args.worker_id, stop=stop)


if __name__ == "__main__":  # pragma: no cover - exercised by process supervisor
    raise SystemExit(main())
