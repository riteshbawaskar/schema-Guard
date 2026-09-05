"""File-based storage for HTML comparison reports, organized by YYYY/MM."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings

_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_id(comparison_id: str) -> None:
    if not _SAFE_ID_RE.match(comparison_id):
        raise ValueError(f"Invalid comparison id: {comparison_id!r}")


def report_path_for(comparison_id: str, when: datetime | None = None) -> Path:
    _validate_id(comparison_id)
    when = when or datetime.now(timezone.utc)
    settings = get_settings()
    d = settings.reports_dir / f"{when.year:04d}" / f"{when.month:02d}"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{comparison_id}.html"


def save_report(comparison_id: str, html: str, when: datetime | None = None) -> Path:
    path = report_path_for(comparison_id, when)
    path.write_text(html, encoding="utf-8")
    return path


def load_report(path: str | Path) -> str:
    resolved = Path(path).resolve()
    settings = get_settings()
    root = settings.reports_dir.resolve()
    if not str(resolved).startswith(str(root)):
        raise ValueError("Refusing to read report file outside managed reports directory")
    if not resolved.exists():
        raise FileNotFoundError(f"Report not found: {resolved}")
    return resolved.read_text(encoding="utf-8")
