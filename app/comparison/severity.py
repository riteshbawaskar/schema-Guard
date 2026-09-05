"""Configurable severity classification for schema differences."""
from __future__ import annotations

from enum import Enum
from pathlib import Path

import yaml


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class DiffType(str, Enum):
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    MODIFIED = "MODIFIED"
    UNCHANGED = "UNCHANGED"


# Default severity for each (category, diff_type) pair. category is one of:
# table, column, primary_key, foreign_key, unique_constraint, check_constraint,
# index, datatype, length, precision, scale, nullable, default, identity, position
DEFAULT_SEVERITY_RULES: dict[str, dict[str, str]] = {
    "table": {"ADDED": "MEDIUM", "REMOVED": "CRITICAL", "MODIFIED": "INFO"},
    "column": {"ADDED": "MEDIUM", "REMOVED": "CRITICAL", "MODIFIED": "INFO"},
    "datatype": {"MODIFIED": "CRITICAL"},
    "length": {"MODIFIED": "HIGH"},
    "precision": {"MODIFIED": "HIGH"},
    "scale": {"MODIFIED": "HIGH"},
    "nullable": {"MODIFIED": "HIGH"},
    "default": {"MODIFIED": "MEDIUM"},
    "identity": {"MODIFIED": "MEDIUM"},
    "position": {"MODIFIED": "LOW"},
    "primary_key": {"ADDED": "HIGH", "REMOVED": "CRITICAL", "MODIFIED": "CRITICAL"},
    "foreign_key": {"ADDED": "MEDIUM", "REMOVED": "HIGH", "MODIFIED": "HIGH"},
    "unique_constraint": {"ADDED": "MEDIUM", "REMOVED": "HIGH", "MODIFIED": "HIGH"},
    "check_constraint": {"ADDED": "LOW", "REMOVED": "MEDIUM", "MODIFIED": "MEDIUM"},
    "index": {"ADDED": "LOW", "REMOVED": "MEDIUM", "MODIFIED": "MEDIUM"},
    "comment": {"MODIFIED": "INFO"},
}


def load_severity_rules(config_path: str | Path | None = None) -> dict[str, dict[str, str]]:
    rules = {k: dict(v) for k, v in DEFAULT_SEVERITY_RULES.items()}
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}
        overrides = cfg.get("severity_rules", {})
        for category, diff_map in overrides.items():
            rules.setdefault(category, {}).update(diff_map)
    return rules


def get_severity(rules: dict[str, dict[str, str]], category: str, diff_type: str) -> str:
    return rules.get(category, {}).get(diff_type, Severity.INFO.value)


def load_fail_on(config_path: str | Path | None = None) -> list[str]:
    default = ["CRITICAL", "HIGH"]
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}
        fail_on = cfg.get("comparison", {}).get("fail_on")
        if fail_on:
            return fail_on
    return default
