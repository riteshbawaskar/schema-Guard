"""Orchestrates a full comparison: resolve source & destination (each may be
    a live database, a saved schema version, or an uploaded schema file),
apply filters INDEPENDENTLY to each side (filters never hide real
differences - a table only in source will show as REMOVED even if it
doesn't match the destination-side filter evaluation), run the comparison
engine, persist a Comparison row, and render/save the HTML report.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.orm import Session

from app.comparison.engine import compare_schemas
from app.comparison.models import ComparisonResult
from app.database import session_scope
from app.filters.engine import apply_filter
from app.models import Comparison
from app.schema.canonical import CanonicalSchema
from app.services import config_service, extraction_service, filter_service, schema_service
from app.storage import report_storage

SourceType = Literal["live", "schema_version", "uploaded_json"]

_JOB_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="comparison")


def shutdown_comparison_jobs() -> None:
    _JOB_EXECUTOR.shutdown(wait=False, cancel_futures=True)


def _filter_canonical_schema(schema: CanonicalSchema, filter_id: str | None, db: Session) -> tuple[CanonicalSchema, list[str]]:
    if not filter_id:
        return schema, []
    filter_obj = filter_service.get_filter_or_404(db, filter_id)
    filter_def = filter_service.to_filter_definition(filter_obj)
    all_names = [t.name for t in schema.tables]
    matched = set(apply_filter(all_names, filter_def))
    removed = sorted(set(all_names) - matched)
    filtered_schema = schema.model_copy(deep=True)
    filtered_schema.tables = [t for t in schema.tables if t.name in matched]
    filtered_schema.metadata.filter = filter_obj.name
    return filtered_schema, removed


def _live_side_label(raw: CanonicalSchema, database: str | None, schema_name: str | None, fallback: str) -> str:
    selected_database = database or raw.metadata.database
    selected_schema = schema_name or raw.metadata.schema_name
    config_name = raw.metadata.database_configuration or fallback
    if selected_database and selected_schema:
        return f"{config_name} ({selected_database}.{selected_schema})"
    if selected_database:
        return f"{config_name} ({selected_database})"
    if selected_schema:
        return f"{config_name} ({selected_schema})"
    return config_name


def _initial_job_label(
    db: Session,
    source_type: SourceType,
    reference: str,
    database: str | None,
    schema_name: str | None,
) -> str:
    if source_type == "live":
        config = config_service.get_configuration_or_404(db, reference)
        configured_database = database or config.configuration.get("database")
        configured_schema = schema_name or config.configuration.get("schema")
        if configured_database and configured_schema:
            return f"{config.name} ({configured_database}.{configured_schema})"
        if configured_database:
            return f"{config.name} ({configured_database})"
        if configured_schema:
            return f"{config.name} ({configured_schema})"
        return config.name
    if source_type == "schema_version":
        version = schema_service.get_version_or_404(db, reference)
        return version.name
    if source_type == "uploaded_json":
        from app.storage.schema_storage import load_schema_from_path
        raw = load_schema_from_path(reference)
        if raw.metadata.database_type.lower() == "axiom" and raw.metadata.database_configuration:
            return raw.metadata.database_configuration
        return raw.metadata.schema_name or raw.metadata.database or reference
    return reference


def resolve_side(
    db: Session,
    source_type: SourceType,
    reference: str,
    filter_id: str | None,
    database: str | None = None,
    schema_name: str | None = None,
) -> tuple[CanonicalSchema, list[str], str]:
    """Returns (filtered_canonical_schema, removed_by_filter, human_label)."""
    if source_type == "live":
        # reference = database_configuration_id
        raw = extraction_service.extract_schema(
            db, config_id=reference, database=database, schema=schema_name, filter_id=None
        )
        label = _live_side_label(
            raw, database, schema_name, raw.metadata.database_configuration or reference
        )
        filtered, removed = _filter_canonical_schema(raw, filter_id, db)
        return filtered, removed, label
    elif source_type == "schema_version":
        version = schema_service.get_version_or_404(db, reference)
        raw = schema_service.load_canonical_schema(version)
        label = version.name
        filtered, removed = _filter_canonical_schema(raw, filter_id, db)
        return filtered, removed, label
    elif source_type == "uploaded_json":
        # reference = file path under data/uploads
        from app.storage.schema_storage import load_schema_from_path
        raw = load_schema_from_path(reference)
        if raw.metadata.database_type.lower() == "axiom" and raw.metadata.database_configuration:
            label = raw.metadata.database_configuration
        else:
            label = raw.metadata.schema_name or raw.metadata.database or reference
        filtered, removed = _filter_canonical_schema(raw, filter_id, db)
        return filtered, removed, label
    else:
        raise ValueError(f"Unknown source_type: {source_type}")


def run_comparison(
    db: Session,
    source_type: SourceType,
    source_reference: str,
    destination_type: SourceType,
    destination_reference: str,
    source_filter_id: str | None = None,
    destination_filter_id: str | None = None,
    source_database: str | None = None,
    source_schema: str | None = None,
    destination_database: str | None = None,
    destination_schema: str | None = None,
    normalization_mode: str = "compatible",
    fail_on: list[str] | None = None,
) -> tuple[Comparison, ComparisonResult, str]:
    start = time.monotonic()
    comparison_row = Comparison(
        source_type=source_type, source_reference=source_reference,
        destination_type=destination_type, destination_reference=destination_reference,
        source_filter_id=source_filter_id, destination_filter_id=destination_filter_id,
        status="RUNNING",
    )
    db.add(comparison_row)
    db.commit()
    db.refresh(comparison_row)

    try:
        src_schema, src_removed, src_label = resolve_side(
            db, source_type, source_reference, source_filter_id, source_database, source_schema
        )
        dst_schema, dst_removed, dst_label = resolve_side(
            db, destination_type, destination_reference, destination_filter_id, destination_database, destination_schema
        )

        result = compare_schemas(src_schema, dst_schema, fail_on=fail_on)
        result.source_label = src_label
        result.destination_label = dst_label
        result.normalization_mode = normalization_mode
        if source_filter_id:
            result.source_filter = filter_service.get_filter_or_404(db, source_filter_id).name
        if destination_filter_id:
            result.destination_filter = filter_service.get_filter_or_404(db, destination_filter_id).name
        result.removed_by_filter = {"source": src_removed, "destination": dst_removed}

        from app.reports.html_report import render_html_report
        html = render_html_report(result, comparison_row.id)
        report_path = report_storage.save_report(comparison_row.id, html)

        from app.models import Report
        report_row = Report(comparison_id=comparison_row.id, file_path=str(report_path), file_size=len(html.encode()))
        db.add(report_row)

        comparison_row.status = result.status
        comparison_row.source_label = result.source_label
        comparison_row.destination_label = result.destination_label
        comparison_row.table_count = result.summary.tables_compared
        comparison_row.column_count = result.summary.columns_added + result.summary.columns_removed + result.summary.columns_modified
        comparison_row.difference_count = result.summary.difference_count
        comparison_row.critical_count = result.summary.critical_count
        comparison_row.high_count = result.summary.high_count
        comparison_row.medium_count = result.summary.medium_count
        comparison_row.low_count = result.summary.low_count
        comparison_row.info_count = result.summary.info_count
        comparison_row.report_path = str(report_path)
        comparison_row.duration = time.monotonic() - start
        db.commit()
        db.refresh(comparison_row)
        return comparison_row, result, str(report_path)
    except Exception as e:  # noqa: BLE001
        comparison_row.status = "ERROR"
        comparison_row.error_message = str(e)
        comparison_row.duration = time.monotonic() - start
        db.commit()
        raise


def create_comparison_job(
    db: Session,
    source_type: SourceType,
    source_reference: str,
    destination_type: SourceType,
    destination_reference: str,
    source_filter_id: str | None = None,
    destination_filter_id: str | None = None,
    source_database: str | None = None,
    source_schema: str | None = None,
    destination_database: str | None = None,
    destination_schema: str | None = None,
    normalization_mode: str = "compatible",
    fail_on: list[str] | None = None,
) -> Comparison:
    """Create a visible RUNNING job and execute it outside the request."""
    comparison_row = Comparison(
        source_type=source_type,
        source_reference=source_reference,
        destination_type=destination_type,
        destination_reference=destination_reference,
        source_filter_id=source_filter_id,
        destination_filter_id=destination_filter_id,
        status="RUNNING",
        source_label=_initial_job_label(db, source_type, source_reference, source_database, source_schema),
        destination_label=_initial_job_label(
            db, destination_type, destination_reference, destination_database, destination_schema
        ),
    )
    db.add(comparison_row)
    db.commit()
    db.refresh(comparison_row)
    job_args = (
        source_type, source_reference, destination_type, destination_reference,
        source_filter_id, destination_filter_id, source_database, source_schema,
        destination_database, destination_schema, normalization_mode, fail_on,
    )
    _JOB_EXECUTOR.submit(_run_comparison_job, comparison_row.id, job_args)
    return comparison_row


def _run_comparison_job(comparison_id: str, args: tuple) -> None:
    try:
        with session_scope() as db:
            # run_comparison creates its own row for synchronous callers, so
            # run the worker against the already-created job here.
            comparison_row = db.get(Comparison, comparison_id)
            if comparison_row is None:
                return
            start = time.monotonic()
            try:
                src_schema, src_removed, src_label = resolve_side(
                    db, args[0], args[1], args[4], args[6], args[7]
                )
                dst_schema, dst_removed, dst_label = resolve_side(
                    db, args[2], args[3], args[5], args[8], args[9]
                )
                result = compare_schemas(src_schema, dst_schema, fail_on=args[11])
                result.source_label = src_label
                result.destination_label = dst_label
                result.normalization_mode = args[10]
                if args[4]:
                    result.source_filter = filter_service.get_filter_or_404(db, args[4]).name
                if args[5]:
                    result.destination_filter = filter_service.get_filter_or_404(db, args[5]).name
                result.removed_by_filter = {"source": src_removed, "destination": dst_removed}

                from app.reports.html_report import render_html_report
                html = render_html_report(result, comparison_id)
                report_path = report_storage.save_report(comparison_id, html)
                from app.models import Report
                db.add(Report(
                    comparison_id=comparison_id,
                    file_path=str(report_path),
                    file_size=len(html.encode()),
                ))
                comparison_row.status = result.status
                comparison_row.source_label = result.source_label
                comparison_row.destination_label = result.destination_label
                comparison_row.table_count = result.summary.tables_compared
                comparison_row.column_count = (
                    result.summary.columns_added + result.summary.columns_removed
                    + result.summary.columns_modified
                )
                comparison_row.difference_count = result.summary.difference_count
                comparison_row.critical_count = result.summary.critical_count
                comparison_row.high_count = result.summary.high_count
                comparison_row.medium_count = result.summary.medium_count
                comparison_row.low_count = result.summary.low_count
                comparison_row.info_count = result.summary.info_count
                comparison_row.report_path = str(report_path)
                comparison_row.duration = time.monotonic() - start
            except Exception as exc:  # noqa: BLE001
                comparison_row.status = "ERROR"
                comparison_row.error_message = str(exc)
                comparison_row.duration = time.monotonic() - start
            db.commit()
    except Exception:
        # The job has no request context; leave a best-effort error update.
        with session_scope() as db:
            comparison_row = db.get(Comparison, comparison_id)
            if comparison_row is not None:
                comparison_row.status = "ERROR"
                comparison_row.error_message = "Background comparison failed"
                db.commit()
