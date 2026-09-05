"""File-based storage for schema JSON artifacts.

Large JSON snapshots live under data/schemas/<schema-id>/v<N>.json; SQLite
only stores the metadata row (see SchemaVersion model).
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from app.config import get_settings
from app.schema.canonical import CanonicalSchema

_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_id(schema_id: str) -> None:
    """Guards against path traversal via a crafted schema id."""
    if not _SAFE_ID_RE.match(schema_id):
        raise ValueError(f"Invalid schema id: {schema_id!r}")


def schema_dir(schema_id: str) -> Path:
    _validate_id(schema_id)
    settings = get_settings()
    d = settings.schemas_dir / schema_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def version_file_path(schema_id: str, version: int) -> Path:
    return schema_dir(schema_id) / f"v{version}.json"


def compute_checksum(canonical_json: str) -> str:
    return hashlib.sha256(canonical_json.encode()).hexdigest()


def save_schema_version(schema_id: str, version: int, schema: CanonicalSchema) -> tuple[Path, str]:
    canonical_json = schema.to_canonical_json()
    path = version_file_path(schema_id, version)
    path.write_text(canonical_json, encoding="utf-8")
    checksum = compute_checksum(canonical_json)
    return path, checksum


def load_schema_from_path(path: str | Path) -> CanonicalSchema:
    resolved = Path(path).resolve()
    settings = get_settings()
    allowed_roots = [settings.schemas_dir.resolve(), settings.uploads_dir.resolve()]
    if not any(str(resolved).startswith(str(root)) for root in allowed_roots):
        raise ValueError("Refusing to read schema file outside managed storage directories")
    if not resolved.exists():
        raise FileNotFoundError(f"Schema file not found: {resolved}")
    return CanonicalSchema.model_validate_json(resolved.read_text(encoding="utf-8"))


def next_version_number(schema_id: str) -> int:
    d = schema_dir(schema_id)
    existing = [int(p.stem[1:]) for p in d.glob("v*.json") if p.stem[1:].isdigit()]
    return (max(existing) + 1) if existing else 1
