"""Read and validate the editable comparison policy."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

MAPPING_PATH = Path("config/axiom_mapping.yaml")
DEFAULT_MAPPING = {
    "table_matching": {
        "enabled": True,
        "ignore_names": False,
        "mappings": [],
    },
    "attribute_mappings": [],
    "ignored_attributes": [],
    "missing_attribute": {"severity": "WARNING", "fail": False},
    "xml": {
        "enabled": True,
        "object_type": "DataSource",
        "validate_object_types": ["DataSource:field"],
        "validate_scope": "selected_objects",
        "attribute_mappings": [],
        "ignored_attributes": [],
        "missing_attribute": {"severity": "WARNING", "fail": False},
        "ignored_properties": [],
        "datatype_map": {},
    }
}


def load_mapping(path: str | Path | None = None) -> dict[str, Any]:
    mapping_path = Path(path) if path else MAPPING_PATH
    if not mapping_path.exists():
        return _merge_defaults({})
    with mapping_path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    return _merge_defaults(loaded)


def _merge_defaults(value: dict[str, Any]) -> dict[str, Any]:
    table_matching = dict(DEFAULT_MAPPING["table_matching"])
    table_matching.update(value.get("table_matching") or {})
    # Accept the older singular key and normalize empty YAML/UI values.
    if "mapping" in table_matching and "mappings" not in table_matching:
        table_matching["mappings"] = table_matching.pop("mapping")
    if table_matching.get("mappings") is None:
        table_matching["mappings"] = []
    generic = {key: value.get(key, default) for key, default in DEFAULT_MAPPING.items() if key != "xml"}
    xml = dict(DEFAULT_MAPPING["xml"])
    xml.update(value.get("xml", {}))
    xml["missing_attribute"] = {
        **DEFAULT_MAPPING["xml"]["missing_attribute"],
        **(xml.get("missing_attribute") or {}),
    }
    return {**value, **generic, "table_matching": table_matching, "xml": xml}


def validate_mapping(value: dict[str, Any]) -> dict[str, Any]:
    value = _merge_defaults(value)
    if not isinstance(value.get("attribute_mappings"), list):
        raise ValueError("attribute_mappings must be a list")
    if not isinstance(value.get("ignored_attributes"), list):
        raise ValueError("ignored_attributes must be a list")
    table_matching = value.get("table_matching", {})
    if not isinstance(table_matching.get("ignore_names", False), bool):
        raise ValueError("table_matching.ignore_names must be boolean")
    if not isinstance(table_matching.get("mappings", []), list):
        raise ValueError("table_matching.mappings must be a list")
    for item in table_matching.get("mappings", []):
        if not isinstance(item, dict) or not item.get("source") or not item.get("destination"):
            raise ValueError("Each table mapping requires source and destination")
    xml = value["xml"]
    for item in value["attribute_mappings"] + xml.get("attribute_mappings", []):
        if not isinstance(item, dict) or not item.get("source") or not item.get("target"):
            raise ValueError("Each attribute mapping requires source and target")
        if not isinstance(item.get("enabled", True), bool) or not isinstance(item.get("compare", True), bool):
            raise ValueError("Mapping enabled and compare values must be boolean")
    if xml.get("validate_scope") not in {"selected_objects", "all_objects", "complete_xml"}:
        raise ValueError("xml.validate_scope is invalid")
    return value


def save_mapping(value: dict[str, Any], path: str | Path | None = None) -> dict[str, Any]:
    validated = validate_mapping(value)
    mapping_path = Path(path) if path else MAPPING_PATH
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    with mapping_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(validated, handle, sort_keys=False)
    return validated