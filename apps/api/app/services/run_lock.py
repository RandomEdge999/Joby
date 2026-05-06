"""Process-wide pipeline lock.

Prevents ``POST /api/runs/trigger`` and a scheduled watch from running the
pipeline concurrently, which would race on the SQLite writes and on the
``Screening`` / ``JobRanking`` unique constraints.

The lock is a plain ``threading.Lock`` because the FastAPI app is single-process
(uvicorn with workers=1 is the default for local deployments). If you run
multiple worker processes, swap this for a file lock under ``data/``.
"""
from __future__ import annotations

import threading

_PIPELINE_LOCK = threading.Lock()


def try_acquire(timeout: float = 0.0) -> bool:
    """Non-blocking acquire by default. Returns True when the lock was obtained."""
    return _PIPELINE_LOCK.acquire(blocking=timeout > 0, timeout=timeout or -1)


def release() -> None:
    try:
        _PIPELINE_LOCK.release()
    except RuntimeError:
        pass


def is_busy() -> bool:
    acquired = _PIPELINE_LOCK.acquire(blocking=False)
    if acquired:
        _PIPELINE_LOCK.release()
        return False
    return True
