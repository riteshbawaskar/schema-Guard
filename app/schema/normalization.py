"""Database-independent datatype normalization.

Two modes:
  - strict: native type name (uppercased) is the normalized type. Different
    native names are never considered equal, even if semantically similar.
  - compatible: native types are mapped into a smaller set of canonical
    buckets (NUMERIC, TEXT, DATE, TIMESTAMP, BOOLEAN, BINARY, ...) via a
    configurable mapping table, so e.g. Snowflake NUMBER, Oracle NUMBER and
    Postgres NUMERIC are all treated as NUMERIC.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml

NormalizationMode = Literal["strict", "compatible"]

# Default compatible-mode mapping: (database_type, native_type_prefix) -> canonical bucket.
# native_type_prefix is matched case-insensitively against the start of the
# native type name (already stripped of length/precision).
_DEFAULT_COMPATIBLE_MAP: dict[str, list[tuple[str, str]]] = {
    "NUMERIC": [
        ("snowflake", "NUMBER"),
        ("snowflake", "DECIMAL"),
        ("snowflake", "NUMERIC"),
        ("snowflake", "INT"),
        ("snowflake", "BIGINT"),
        ("snowflake", "SMALLINT"),
        ("snowflake", "FLOAT"),
        ("snowflake", "DOUBLE"),
        ("oracle", "NUMBER"),
        ("oracle", "FLOAT"),
        ("oracle", "BINARY_FLOAT"),
        ("oracle", "BINARY_DOUBLE"),
        ("postgresql", "NUMERIC"),
        ("postgresql", "DECIMAL"),
        ("postgresql", "INTEGER"),
        ("postgresql", "BIGINT"),
        ("postgresql", "SMALLINT"),
        ("postgresql", "REAL"),
        ("postgresql", "DOUBLE"),
        ("sqlite", "INTEGER"),
        ("sqlite", "REAL"),
        ("sqlite", "NUMERIC"),
        ("sqlite", "DECIMAL"),
    ],
    "TEXT": [
        ("snowflake", "VARCHAR"),
        ("snowflake", "CHAR"),
        ("snowflake", "STRING"),
        ("snowflake", "TEXT"),
        ("oracle", "VARCHAR2"),
        ("oracle", "NVARCHAR2"),
        ("oracle", "CHAR"),
        ("oracle", "CLOB"),
        ("postgresql", "VARCHAR"),
        ("postgresql", "CHARACTER VARYING"),
        ("postgresql", "CHAR"),
        ("postgresql", "TEXT"),
        ("sqlite", "TEXT"),
        ("sqlite", "VARCHAR"),
        ("sqlite", "CHAR"),
    ],
    "BOOLEAN": [
        ("snowflake", "BOOLEAN"),
        ("postgresql", "BOOLEAN"),
        ("postgresql", "BOOL"),
        ("oracle", "BOOLEAN"),
        ("sqlite", "BOOLEAN"),
    ],
    "DATE": [
        ("snowflake", "DATE"),
        ("oracle", "DATE"),
        ("postgresql", "DATE"),
        ("sqlite", "DATE"),
    ],
    "TIMESTAMP": [
        ("snowflake", "TIMESTAMP"),
        ("snowflake", "TIMESTAMP_NTZ"),
        ("snowflake", "TIMESTAMP_LTZ"),
        ("snowflake", "TIMESTAMP_TZ"),
        ("snowflake", "DATETIME"),
        ("oracle", "TIMESTAMP"),
        ("postgresql", "TIMESTAMP"),
        ("postgresql", "TIMESTAMPTZ"),
        ("sqlite", "TIMESTAMP"),
        ("sqlite", "DATETIME"),
    ],
    "BINARY": [
        ("snowflake", "BINARY"),
        ("snowflake", "VARBINARY"),
        ("oracle", "BLOB"),
        ("oracle", "RAW"),
        ("postgresql", "BYTEA"),
        ("sqlite", "BLOB"),
    ],
}


def load_compatible_map(config_path: str | Path | None = None) -> dict[str, list[tuple[str, str]]]:
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}
        mapping = cfg.get("datatype_normalization", {}).get("compatible_map")
        if mapping:
            result: dict[str, list[tuple[str, str]]] = {}
            for bucket, entries in mapping.items():
                result[bucket] = [(e["database_type"], e["native_prefix"]) for e in entries]
            return result
    return _DEFAULT_COMPATIBLE_MAP


def _strip_size(native_type: str) -> str:
    """Strip trailing (n), (n,m) etc from a native type string."""
    idx = native_type.find("(")
    return native_type[:idx].strip() if idx != -1 else native_type.strip()


def normalize_datatype(
    database_type: str,
    native_type: str,
    mode: NormalizationMode = "compatible",
    compatible_map: dict[str, list[tuple[str, str]]] | None = None,
) -> str:
    """Return the normalized datatype for a native type.

    strict mode: returns the bare native type name, uppercased, size stripped.
    compatible mode: maps into a canonical bucket; falls back to the bare
    native type name (uppercased) if no mapping is configured, so unmapped
    types are never silently treated as equal to unrelated types.
    """
    base = _strip_size(native_type).upper()
    if mode == "strict":
        return base

    mapping = compatible_map if compatible_map is not None else _DEFAULT_COMPATIBLE_MAP
    db_type = database_type.lower()
    for bucket, entries in mapping.items():
        for entry_db, prefix in entries:
            if entry_db == db_type and base.startswith(prefix.upper()):
                return bucket
    return base
