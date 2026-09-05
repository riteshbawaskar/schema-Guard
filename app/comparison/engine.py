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


def _index_by_name(items: list, key: str = "name") -> dict:
    return {getattr(i, key): i for i in items}


def _compare_columns(src_cols: list[ColumnModel], dst_cols: list[ColumnModel], rules: dict) -> list[ObjectDiff]:
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
                source_value=s.model_dump(),
            ))
            continue
        if s is None and d is not None:
            diffs.append(ObjectDiff(
                object_type="column", name=name, diff_type="ADDED",
                severity=get_severity(rules, "column", "ADDED"),
                destination_value=d.model_dump(),
            ))
            continue

        field_diffs: list[FieldDiff] = []
        checks = [
            ("datatype", s.normalized_datatype, d.normalized_datatype),
            ("length", s.length, d.length),
            ("precision", s.precision, d.precision),
            ("scale", s.scale, d.scale),
            ("nullable", s.nullable, d.nullable),
            ("default", s.default, d.default),
            ("identity", s.is_identity, d.is_identity),
            ("position", s.ordinal_position, d.ordinal_position),
        ]
        for category, sv, dv in checks:
            if sv != dv:
                field_diffs.append(FieldDiff(
                    category=category, field=category, source_value=sv, destination_value=dv,
                    severity=get_severity(rules, category, "MODIFIED"),
                ))

        diff_type = "MODIFIED" if field_diffs else "UNCHANGED"
        severity = max((fd.severity for fd in field_diffs), key=_severity_rank, default="INFO") if field_diffs else "INFO"
        diffs.append(ObjectDiff(
            object_type="column", name=name, diff_type=diff_type, severity=severity,
            field_diffs=field_diffs,
            source_value=s.model_dump(), destination_value=d.model_dump(),
        ))
    return diffs


_SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}


def _severity_rank(sev: str) -> int:
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
    if s.columns != d.columns:
        return ObjectDiff(object_type="primary_key", name=d.name or s.name or "PK", diff_type="MODIFIED",
                           severity=get_severity(rules, "primary_key", "MODIFIED"),
                           source_value=s.model_dump(), destination_value=d.model_dump())
    return ObjectDiff(object_type="primary_key", name=d.name or s.name or "PK", diff_type="UNCHANGED",
                       severity="INFO", source_value=s.model_dump(), destination_value=d.model_dump())


def _compare_table(src_table: TableModel | None, dst_table: TableModel | None, rules: dict) -> TableDiff:
    if src_table is not None and dst_table is None:
        return TableDiff(table_name=src_table.name, diff_type="REMOVED",
                          severity=get_severity(rules, "table", "REMOVED"))
    if src_table is None and dst_table is not None:
        return TableDiff(table_name=dst_table.name, diff_type="ADDED",
                          severity=get_severity(rules, "table", "ADDED"))

    assert src_table is not None and dst_table is not None
    column_diffs = _compare_columns(src_table.columns, dst_table.columns, rules)
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
        table_name=dst_table.name, diff_type=table_diff_type, severity=table_severity,
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
    rules = load_severity_rules(severity_config_path)
    fail_on = fail_on if fail_on is not None else load_fail_on(severity_config_path)

    src_sorted = source.sorted()
    dst_sorted = destination.sorted()

    src_map = {t.name: t for t in src_sorted.tables}
    dst_map = {t.name: t for t in dst_sorted.tables}

    table_diffs: list[TableDiff] = []
    for name in sorted(set(src_map) | set(dst_map)):
        table_diffs.append(_compare_table(src_map.get(name), dst_map.get(name), rules))

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
            else:
                summary.info_count += 1

    status = "FAIL" if any(getattr(summary, f"{s.lower()}_count") > 0 for s in fail_on) else "PASS"

    return ComparisonResult(
        source_label=source.metadata.database_configuration or source.metadata.database or "source",
        destination_label=destination.metadata.database_configuration or destination.metadata.database or "destination",
        status=status,
        summary=summary,
        table_diffs=table_diffs,
    )


def _collect_severities(td: TableDiff) -> list[str]:
    sevs = []
    if td.diff_type != "UNCHANGED":
        sevs.append(td.severity)
    for coll in (td.column_diffs, td.foreign_key_diffs, td.unique_constraint_diffs, td.check_constraint_diffs, td.index_diffs):
        for d in coll:
            if d.diff_type != "UNCHANGED":
                sevs.append(d.severity)
    if td.primary_key_diff and td.primary_key_diff.diff_type != "UNCHANGED":
        sevs.append(td.primary_key_diff.severity)
    return sevs
