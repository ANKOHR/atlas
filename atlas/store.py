"""JSON persistence for every run's evidence and analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def save_store(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_store(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
