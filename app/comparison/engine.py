"""Core comparison engine. Pure function of two CanonicalSchema objects plus
configuration - no I/O, no DB access, fully unit-testable. Used identically
by the API, UI and CLI so comparison logic is never duplicated.
"""
from __future__ import annotations

from app.comparison.models import (
    ComparisonResult,
    ComparisonSummary,
    FieldDiff,
    ObjectDiff,
    TableDiff,
)
from app.comparison.severity import get_severity, load_fail_on, load_severity_rules
from app.schema.canonical import CanonicalSchema, ColumnModel, TableModel
from app.services.xml_mapping_service import load_mapping
from app.services.xml_mapping_service import map_value


def _index_by_name(items: list, key: str = "name") -> dict:
    """Index model collections by their configured comparison key."""
    return {getattr(i, key): i for i in items}


def _column_snapshot(column: ColumnModel) -> dict:
    """Serialize only attributes explicitly supplied by a column source."""
    values = column.model_dump()
    available = set(column.model_fields_set) | {"name", "native_datatype", "normalized_datatype"}
    return {key: value for key, value in values.items() if key in available}


def _compare_columns(src_cols: list[ColumnModel], dst_cols: list[ColumnModel], rules: dict, xml_policy: dict) -> list[ObjectDiff]:
    """Compare columns dynamically using supplied attributes and policy mappings."""
    src_map = _index_by_name(src_cols)
    dst_map = _index_by_name(dst_cols)
    diffs: list[ObjectDiff] = []

    for name in sorted(set(src_map) | set(dst_map)):
        s = src_map.get(name)
        d = dst_map.get(name)
        if s is not None and d is None:
            diffs.append(ObjectDiff(
                object_type="column", name=name, diff_type="REMOVED",
                severity=get_severity(rules, "column", "REMOVED"),
                source_value=_column_snapshot(s),
            ))
            continue
        if s is None and d is not None:
            diffs.append(ObjectDiff(
                object_type="column", name=name, diff_type="ADDED",
                severity=get_severity(rules, "column", "ADDED"),
                destination_value=_column_snapshot(d),
            ))
            continue

        assert s is not None and d is not None

        field_diffs: list[FieldDiff] = []
        xml_config = xml_policy.get("xml", {})
        configured_attributes = xml_policy.get("attribute_mappings") or xml_config.get("attribute_mappings", [])
        attribute_mappings = [item for item in configured_attributes if item.get("enabled", True)]
        target_mapping = {item["target"]: item for item in attribute_mappings}
        ignored_attributes = set(xml_policy.get("ignored_attributes", []))
        ignored_attributes.update(item["target"] for item in attribute_mappings if item.get("compare") is False)
        mapped_xml_targets = {
            item["target"] for item in attribute_mappings
            if item["source"] in s.source_properties or item["source"] in d.source_properties
        }
        source_values = _column_snapshot(s)
        destination_values = _column_snapshot(d)
        comparable_keys = (set(source_values) | set(destination_values)) - {"name", "source_properties"}
        for category in sorted(comparable_keys):
            severity_category = {
                "normalized_datatype": "datatype",
                "ordinal_position": "position",
                "is_identity": "identity",
            }.get(category) or category
            source_has = category in source_values
            destination_has = category in destination_values
            if category in ignored_attributes:
                continue
            if category in mapped_xml_targets:
                continue
            sv = map_value(xml_policy, category, source_values.get(category))
            dv = map_value(xml_policy, category, destination_values.get(category))
            if sv != dv or source_has != destination_has:
                field_diffs.append(FieldDiff(
                    category=severity_category, field=category, source_value=sv, destination_value=dv,
                    severity=get_severity(rules, severity_category, "MODIFIED"),
                ))

        # Axiom exports carry additional field metadata that is not part of
        # the database-neutral column contract. Compare it when both sides
        # provide XML properties, while leaving database comparisons unchanged.
        if s.source_properties and d.source_properties:
            missing_policy = xml_policy.get("missing_attribute") or xml_config.get("missing_attribute") or {}
            missing_severity = missing_policy.get("severity", "WARNING")
            comparable_properties = {
                item["source"]: item for item in attribute_mappings
                if item.get("compare", True)
            }
            for property_name, attribute_mapping in sorted(comparable_properties.items()):
                target = attribute_mapping["target"]
                source_has = property_name in s.source_properties
                destination_has = property_name in d.source_properties
                sv = map_value(xml_policy, target, s.source_properties.get(property_name))
                dv = map_value(xml_policy, target, d.source_properties.get(property_name))
                if sv != dv or source_has != destination_has:
                    severity_category = "datatype" if target == "datatype" else "comment"
                    severity = missing_severity if not source_has or not destination_has else get_severity(rules, severity_category, "MODIFIED")
                    field_diffs.append(FieldDiff(
                        category=f"xml:{property_name}", field=property_name,
                        source_value=sv, destination_value=dv,
                        severity=severity,
                    ))

        diff_type = "MODIFIED" if field_diffs else "UNCHANGED"
        severity = max((fd.severity for fd in field_diffs), key=_severity_rank, default="INFO") if field_diffs else "INFO"
        diffs.append(ObjectDiff(
            object_type="column", name=name, diff_type=diff_type, severity=severity,
            field_diffs=field_diffs,
            source_value=_column_snapshot(s), destination_value=_column_snapshot(d),
        ))
    return diffs


_SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "WARNING": 0.5, "INFO": 0}


def _severity_rank(sev: str) -> int:
    """Return the configured ordering used to summarize object severity."""
    return _SEVERITY_ORDER.get(sev, 0)


def _compare_named_collection(object_type: str, src_items: list, dst_items: list, rules: dict) -> list[ObjectDiff]:
    """Generic comparer for FK/unique/check/index collections, keyed by name."""
    src_map = _index_by_name(src_items)
    dst_map = _index_by_name(dst_items)
    diffs: list[ObjectDiff] = []
    for name in sorted(set(src_map) | set(dst_map)):
        s = src_map.get(name)
        d = dst_map.get(name)
        if s is not None and d is None:
            diffs.append(ObjectDiff(
                object_type=object_type, name=name, diff_type="REMOVED",
                severity=get_severity(rules, object_type, "REMOVED"),
                source_value=s.model_dump(),
            ))
        elif s is None and d is not None:
            diffs.append(ObjectDiff(
                object_type=object_type, name=name, diff_type="ADDED",
                severity=get_severity(rules, object_type, "ADDED"),
                destination_value=d.model_dump(),
            ))
        else:
            assert s is not None and d is not None
            if s.model_dump() != d.model_dump():
                diffs.append(ObjectDiff(
                    object_type=object_type, name=name, diff_type="MODIFIED",
                    severity=get_severity(rules, object_type, "MODIFIED"),
                    source_value=s.model_dump(), destination_value=d.model_dump(),
                ))
            else:
                diffs.append(ObjectDiff(
                    object_type=object_type, name=name, diff_type="UNCHANGED",
                    severity="INFO",
                    source_value=s.model_dump(), destination_value=d.model_dump(),
                ))
    return diffs


def _compare_primary_key(src_table: TableModel, dst_table: TableModel, rules: dict) -> ObjectDiff | None:
    s, d = src_table.primary_key, dst_table.primary_key
    if s is None and d is None:
        return None
    if s is not None and d is None:
        return ObjectDiff(object_type="primary_key", name=s.name or "PK", diff_type="REMOVED",
                           severity=get_severity(rules, "primary_key", "REMOVED"), source_value=s.model_dump())
    if s is None and d is not None:
        return ObjectDiff(object_type="primary_key", name=d.name or "PK", diff_type="ADDED",
                           severity=get_severity(rules, "primary_key", "ADDED"), destination_value=d.model_dump())
    assert s is not None and d is not None
    if s.columns != d.columns:
        return ObjectDiff(object_type="primary_key", name=d.name or s.name or "PK", diff_type="MODIFIED",
                           severity=get_severity(rules, "primary_key", "MODIFIED"),
                           source_value=s.model_dump(), destination_value=d.model_dump())
    return ObjectDiff(object_type="primary_key", name=d.name or s.name or "PK", diff_type="UNCHANGED",
                       severity="INFO", source_value=s.model_dump(), destination_value=d.model_dump())


def _compare_table(src_table: TableModel | None, dst_table: TableModel | None, rules: dict, xml_policy: dict, logical_name: str | None = None) -> TableDiff:
    if src_table is not None and dst_table is None:
        return TableDiff(table_name=logical_name or src_table.name, diff_type="REMOVED",
                          severity=get_severity(rules, "table", "REMOVED"))
    if src_table is None and dst_table is not None:
        return TableDiff(table_name=logical_name or dst_table.name, diff_type="ADDED",
                          severity=get_severity(rules, "table", "ADDED"))

    assert src_table is not None and dst_table is not None
    column_diffs = _compare_columns(src_table.columns, dst_table.columns, rules, xml_policy)
    pk_diff = _compare_primary_key(src_table, dst_table, rules)
    fk_diffs = _compare_named_collection("foreign_key", src_table.foreign_keys, dst_table.foreign_keys, rules)
    uq_diffs = _compare_named_collection("unique_constraint", src_table.unique_constraints, dst_table.unique_constraints, rules)
    chk_diffs = _compare_named_collection("check_constraint", src_table.check_constraints, dst_table.check_constraints, rules)
    idx_diffs = _compare_named_collection("index", src_table.indexes, dst_table.indexes, rules)

    all_diff_types = (
        [c.diff_type for c in column_diffs]
        + [fk.diff_type for fk in fk_diffs]
        + [u.diff_type for u in uq_diffs]
        + [c.diff_type for c in chk_diffs]
        + [i.diff_type for i in idx_diffs]
        + ([pk_diff.diff_type] if pk_diff else [])
    )
    has_changes = any(dt != "UNCHANGED" for dt in all_diff_types)
    table_diff_type = "MODIFIED" if has_changes else "UNCHANGED"

    severities = [c.severity for c in column_diffs if c.diff_type != "UNCHANGED"]
    severities += [fk.severity for fk in fk_diffs if fk.diff_type != "UNCHANGED"]
    severities += [u.severity for u in uq_diffs if u.diff_type != "UNCHANGED"]
    severities += [c.severity for c in chk_diffs if c.diff_type != "UNCHANGED"]
    severities += [i.severity for i in idx_diffs if i.diff_type != "UNCHANGED"]
    if pk_diff and pk_diff.diff_type != "UNCHANGED":
        severities.append(pk_diff.severity)
    table_severity = max(severities, key=_severity_rank) if severities else "INFO"

    return TableDiff(
        table_name=logical_name or dst_table.name, diff_type=table_diff_type, severity=table_severity,
        column_diffs=column_diffs, primary_key_diff=pk_diff,
        foreign_key_diffs=fk_diffs, unique_constraint_diffs=uq_diffs,
        check_constraint_diffs=chk_diffs, index_diffs=idx_diffs,
    )


def compare_schemas(
    source: CanonicalSchema,
    destination: CanonicalSchema,
    severity_config_path: str | None = None,
    fail_on: list[str] | None = None,
) -> ComparisonResult:
    """Compare two canonical schemas using the current table and attribute policy."""
    rules = load_severity_rules(severity_config_path)
    xml_policy = load_mapping()
    fail_on = fail_on if fail_on is not None else load_fail_on(severity_config_path)

    src_sorted = source.sorted()
    dst_sorted = destination.sorted()

    src_map = {t.name: t for t in src_sorted.tables}
    dst_map = {t.name: t for t in dst_sorted.tables}

    table_diffs: list[TableDiff] = []
    legacy_table_policy = xml_policy.get("table_matching") or {}
    use_matching = legacy_table_policy.get("enabled", True)
    table_mappings = xml_policy.get("table_mappings")
    if table_mappings is None:
        table_mappings = legacy_table_policy.get("mappings") or legacy_table_policy.get("mapping") or []
    ignore_names = xml_policy.get("ignore_table_names", legacy_table_policy.get("ignore_names", False))
    pairs: list[tuple[str, TableModel | None, TableModel | None]] = []
    used_source: set[str] = set()
    used_destination: set[str] = set()

    if use_matching:
        for item in table_mappings:
            if item.get("enabled", True) is False:
                continue
            source_name = item.get("source")
            destination_name = item.get("destination")
            source_table = src_map.get(source_name)
            destination_table = dst_map.get(destination_name)
            if source_table is not None and destination_table is not None:
                pairs.append((source_name, source_table, destination_table))
                used_source.add(source_name)
                used_destination.add(destination_name)

    for name in sorted(set(src_map) & set(dst_map)):
        if name not in used_source and name not in used_destination:
            pairs.append((name, src_map[name], dst_map[name]))
            used_source.add(name)
            used_destination.add(name)

    unmatched_source = [src_map[name] for name in sorted(set(src_map) - used_source)]
    unmatched_destination = [dst_map[name] for name in sorted(set(dst_map) - used_destination)]
    if ignore_names:
        paired_count = min(len(unmatched_source), len(unmatched_destination))
        for source_table, destination_table in zip(unmatched_source, unmatched_destination):
            pairs.append((source_table.name, source_table, destination_table))
        unmatched_source = unmatched_source[paired_count:]
        unmatched_destination = unmatched_destination[paired_count:]

    pairs.extend((table.name, table, None) for table in unmatched_source)
    pairs.extend((table.name, None, table) for table in unmatched_destination)
    for logical_name, source_table, destination_table in pairs:
        table_diffs.append(_compare_table(source_table, destination_table, rules, xml_policy, logical_name))

    summary = ComparisonSummary(tables_compared=len(table_diffs))
    for td in table_diffs:
        if td.diff_type == "ADDED":
            summary.tables_added += 1
        elif td.diff_type == "REMOVED":
            summary.tables_removed += 1
        elif td.diff_type == "MODIFIED":
            summary.tables_modified += 1
        else:
            summary.tables_unchanged += 1

        for cd in td.column_diffs:
            if cd.diff_type == "ADDED":
                summary.columns_added += 1
            elif cd.diff_type == "REMOVED":
                summary.columns_removed += 1
            elif cd.diff_type == "MODIFIED":
                summary.columns_modified += 1

        for sev in _collect_severities(td):
            summary.difference_count += 1
            if sev == "CRITICAL":
                summary.critical_count += 1
            elif sev == "HIGH":
                summary.high_count += 1
            elif sev == "MEDIUM":
                summary.medium_count += 1
            elif sev == "LOW":
                summary.low_count += 1
            elif sev == "WARNING":
                summary.warning_count += 1
            else:
                summary.info_count += 1

    status = "FAIL" if any(getattr(summary, f"{s.lower()}_count") > 0 for s in fail_on) else "PASS"

    return ComparisonResult(
        source_label=source.metadata.database_configuration or source.metadata.database or "source",
        destination_label=destination.metadata.database_configuration or destination.metadata.database or "destination",
        source_format="xml" if source.metadata.database_type.lower() == "axiom" else "database",
        destination_format="xml" if destination.metadata.database_type.lower() == "axiom" else "database",
        status=status,
        summary=summary,
        table_diffs=table_diffs,
    )


def _collect_severities(td: TableDiff) -> list[str]:
    sevs = []
    if td.diff_type != "UNCHANGED" and td.severity != "WARNING":
        sevs.append(td.severity)
    for coll in (td.column_diffs, td.foreign_key_diffs, td.unique_constraint_diffs, td.check_constraint_diffs, td.index_diffs):
        for d in coll:
            if d.diff_type != "UNCHANGED":
                sevs.append(d.severity)
    if td.primary_key_diff and td.primary_key_diff.diff_type != "UNCHANGED":
        sevs.append(td.primary_key_diff.severity)
    return sevs
