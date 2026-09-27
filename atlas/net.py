"""Shared request pacing for all Atlas HTTP traffic."""

from __future__ import annotations

import threading
import time

_last_request_finished = 0.0
_lock = threading.Lock()


def before_request(min_interval: float = 1.0) -> None:
    """Wait until the configured quiet period after the prior HTTP call."""
    global _last_request_finished
    with _lock:
        delay = max(1.0, min_interval) - (time.monotonic() - _last_request_finished)
        if delay > 0:
            time.sleep(delay)


def after_request() -> None:
    global _last_request_finished
    with _lock:
        _last_request_finished = time.monotonic()
