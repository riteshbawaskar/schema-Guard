"""Read and validate the editable comparison policy."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

MAPPING_PATH = Path("config/axiom_mapping.yaml")
DEFAULT_MAPPING = {
    "ignore_table_names": False,
    "table_mappings": [],
    "attribute_mappings": [],
    "value_mappings": [],
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
    legacy_tables = value.get("table_matching") or {}
    table_mappings = value.get("table_mappings")
    if table_mappings is None:
        table_mappings = legacy_tables.get("mappings", legacy_tables.get("mapping", []))
    if table_mappings is None:
        table_mappings = []
    ignore_table_names = value.get("ignore_table_names")
    if ignore_table_names is None:
        ignore_table_names = legacy_tables.get("ignore_names", False)
    generic = {
        "ignore_table_names": bool(ignore_table_names),
        "table_mappings": table_mappings or [],
        "attribute_mappings": value.get("attribute_mappings") or [],
        "value_mappings": value.get("value_mappings") or [],
        "ignored_attributes": value.get("ignored_attributes") or [],
        "missing_attribute": value.get("missing_attribute", DEFAULT_MAPPING["missing_attribute"]),
    }
    xml = dict(DEFAULT_MAPPING["xml"])
    xml.update(value.get("xml", {}))
    xml["missing_attribute"] = {
        **DEFAULT_MAPPING["xml"]["missing_attribute"],
        **(xml.get("missing_attribute") or {}),
    }
    result = {**value, **generic, "xml": xml}
    if "table_matching" in value:
        result["table_matching"] = {
            "enabled": legacy_tables.get("enabled", True),
            "ignore_names": bool(ignore_table_names),
            "mappings": table_mappings,
        }
    return result


def validate_mapping(value: dict[str, Any]) -> dict[str, Any]:
    value = _merge_defaults(value)
    if not isinstance(value.get("attribute_mappings"), list):
        raise ValueError("attribute_mappings must be a list")
    if not isinstance(value.get("ignored_attributes"), list):
        raise ValueError("ignored_attributes must be a list")
    if not isinstance(value.get("ignore_table_names"), bool):
        raise ValueError("ignore_table_names must be boolean")
    if not isinstance(value.get("table_mappings"), list):
        raise ValueError("table_mappings must be a list")
    for item in value.get("table_mappings", []):
        if not isinstance(item, dict) or not item.get("source") or not item.get("destination"):
            raise ValueError("Each table mapping requires source and destination")
    if not isinstance(value.get("value_mappings"), list):
        raise ValueError("value_mappings must be a list")
    for item in value.get("value_mappings", []):
        if not isinstance(item, dict) or not item.get("attribute") or "source" not in item or "target" not in item:
            raise ValueError("Each value mapping requires attribute, source, and target")
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


def map_value(policy: dict[str, Any], attribute: str, value: Any) -> Any:
    """Return the configured canonical value for a comparison attribute."""
    for item in policy.get("value_mappings", []):
        if item.get("enabled", True) and item.get("attribute") == attribute and value == item.get("source"):
            return item.get("target")
    return value