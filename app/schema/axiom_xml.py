"""Convert Axiom DataSource XML exports into the canonical schema model."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from app.schema.canonical import CanonicalSchema, ColumnModel, SchemaMetadata, TableModel
from app.schema.normalization import normalize_datatype
from app.services.xml_mapping_service import load_mapping, map_value

def load_axiom_mapping(path: str | Path | None = None) -> dict:
    return load_mapping(path).get("xml", {})


def _properties(element: ET.Element) -> dict[str, str | None]:
    # valueType-only entries describe empty Axiom containers, not field values.
    # Keep properties with value="" because an explicit empty value is still
    # part of the exported schema and should compare as such.
    return {
        child.get("name", ""): child.get("value")
        for child in element.findall("property")
        if child.get("value") is not None
    }


def _safe_xml_root(content: bytes) -> ET.Element:
    # ElementTree does not resolve external entities, and rejecting declarations
    # keeps uploaded documents from carrying entity-expansion payloads.
    if re.search(rb"<!DOCTYPE|<!ENTITY", content, flags=re.IGNORECASE):
        raise ValueError("XML declarations are not allowed")
    try:
        return ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML: {exc}") from exc


def _mapped_value(props: dict[str, str | None], source: str | None, default=None):
    return props.get(source, default) if source else default


def _as_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Mapped numeric XML value is invalid: {value!r}") from exc


def _as_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"true", "1", "yes"}


def parse_axiom_xml(content: bytes, mapping_path: str | Path | None = None) -> CanonicalSchema:
    full_mapping = load_mapping(mapping_path)
    mapping = full_mapping.get("xml", {})
    if not mapping.get("enabled", True):
        raise ValueError("XML schema validation is disabled in the XML mapping configuration")
    root = _safe_xml_root(content)
    root_props = _properties(root)
    if root.get("type") != mapping.get("object_type", "DataSource"):
        raise ValueError(f"Axiom XML root object must have type {mapping.get('object_type', 'DataSource')}")

    datasource_name = root_props.get("name") or "Axiom DataSource"
    layout = next((child for child in root.findall("property") if child.get("name") == "layout"), None)
    if layout is None:
        raise ValueError("Axiom DataSource is missing its layout")

    object_types = mapping.get("validate_object_types") or [mapping.get("field_object_type", "DataSource:field")]
    if mapping.get("field_object_type") and object_types == ["DataSource:field"]:
        object_types = [mapping["field_object_type"]]
    layout_objects = layout.findall("object")
    if mapping.get("validate_scope") in {"all_objects", "complete_xml"}:
        fields = layout_objects
    else:
        fields = [obj for obj in layout_objects if obj.get("type") in object_types]
    if not fields:
        raise ValueError("Axiom DataSource contains no DataSource:field objects")

    columns: list[ColumnModel] = []
    configured = mapping.get("attribute_mappings", [])
    if not configured and mapping.get("field_properties"):
        configured = [{"source": source, "target": target, "enabled": True, "compare": True}
                      for target, source in mapping["field_properties"].items()]
    generic = full_mapping.get("attribute_mappings", [])
    mappings = [item for item in generic + configured if item.get("enabled", True)]
    target_to_source = {item["target"]: item["source"] for item in mappings}
    comparable_sources = {item["source"] for item in mappings if item.get("compare", True)}
    name_property = target_to_source.get("name", "name")
    datatype_property = target_to_source.get("datatype", "type")
    nullable_property = target_to_source.get("nullable", "allowNulls")
    comment_property = target_to_source.get("comment", "description")
    default_property = target_to_source.get("default", "default")
    datatype_map = {str(k).upper(): str(v) for k, v in mapping.get("datatype_map", {}).items()}
    ignored_properties = set(mapping.get("ignored_properties", []))
    for ordinal, field in enumerate(fields, start=1):
        props = _properties(field)
        props = {
            key: value for key, value in props.items()
            if key not in ignored_properties and key in comparable_sources
        }
        name = props.get(name_property) or field.get("type")
        axiom_type = (props.get(datatype_property) or field.get("type") or "").upper()
        if not name or not axiom_type:
            raise ValueError("Every DataSource:field must contain name and type properties")
        native_type = datatype_map.get(axiom_type, axiom_type)
        native_type = map_value(full_mapping, "datatype", native_type)
        length = _as_int(_mapped_value(props, target_to_source.get("length")))
        precision = _as_int(_mapped_value(props, target_to_source.get("precision")))
        scale = _as_int(_mapped_value(props, target_to_source.get("scale")))
        columns.append(ColumnModel(
            name=name,
            ordinal_position=ordinal,
            native_datatype=native_type,
            normalized_datatype=normalize_datatype("axiom", native_type),
            length=length,
            precision=precision,
            scale=scale,
            nullable=_as_bool(props.get(nullable_property), True),
            default=props.get(default_property),
            is_identity=_as_bool(_mapped_value(props, target_to_source.get("identity")), False),
            comment=props.get(comment_property) or None,
            source_properties=props,
        ))

    return CanonicalSchema(
        metadata=SchemaMetadata(database_type="axiom", database=datasource_name, schema_name="layout"),
        tables=[TableModel(name=datasource_name, columns=columns)],
    ).sorted()


def parse_axiom_xml_file(path: str | Path, mapping_path: str | Path | None = None) -> CanonicalSchema:
    return parse_axiom_xml(Path(path).read_bytes(), mapping_path=mapping_path)