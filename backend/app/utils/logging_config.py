"""Logging helpers: a root logger + a per-job in-memory handler."""
from __future__ import annotations

import logging
import sys
from collections import deque
from typing import Deque


class _DropJobPolling(logging.Filter):
    """Silence the flood of access-log lines from the UI polling /api/jobs.

    The frontend polls job status ~once a second; without this filter every
    poll prints a `GET /api/jobs/... 200 OK` line and drowns the real logs.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        msg = record.getMessage()
        return "/api/jobs/" not in msg


def configure_root() -> None:
    # Quiet the per-poll access spam regardless of init state.
    logging.getLogger("uvicorn.access").addFilter(_DropJobPolling())
    if logging.getLogger().handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    )
    logging.basicConfig(level=logging.INFO, handlers=[handler])


class JobLogHandler(logging.Handler):
    """Captures log records into a bounded deque so the API can stream them."""

    def __init__(self, maxlen: int = 1000) -> None:
        super().__init__(level=logging.INFO)
        self.records: Deque[str] = deque(maxlen=maxlen)
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s",
                                             datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            self.records.append(self.format(record))
        except Exception:  # pragma: no cover - logging must never raise
            pass

    def lines(self) -> list[str]:
        return list(self.records)
