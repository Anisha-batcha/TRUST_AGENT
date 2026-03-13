from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalJobQueue:
    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=4)

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "created_at": utc_now_iso(),
                "updated_at": utc_now_iso(),
                "result": None,
                "error": None,
                "backend": "local",
            }

        def runner() -> None:
            self._update(job_id, status="running")
            try:
                result = fn(*args, **kwargs)
                self._update(job_id, status="completed", result=result)
            except Exception as exc:
                self._update(job_id, status="failed", error=str(exc))

        self._executor.submit(runner)
        return job_id

    def _update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            if job_id not in self._jobs:
                return
            self._jobs[job_id].update(fields)
            self._jobs[job_id]["updated_at"] = utc_now_iso()

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None


class QueueAdapter:
    """
    Celery/Redis-ready wrapper.
    If CELERY_BROKER_URL and celery package are available, this can be extended
    to route jobs to Celery. For now it safely falls back to local workers.
    """

    def __init__(self) -> None:
        self.mode = "local"
        self.local = LocalJobQueue()
        self._celery_app = None

        broker = os.getenv("CELERY_BROKER_URL")
        if broker:
            try:
                from celery import Celery  # type: ignore

                backend = os.getenv("CELERY_RESULT_BACKEND", broker)
                self._celery_app = Celery("trustagent", broker=broker, backend=backend)
                self.mode = "celery_stub"
            except Exception:
                self.mode = "local"

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
        # Keep execution reliable: local queue always works in dev.
        return self.local.submit(fn, *args, **kwargs)

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self.local.get(job_id)


queue_adapter = QueueAdapter()
