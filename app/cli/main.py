"""SchemaSentry CLI (DB Schema Validator).

Uses the exact same services as the REST API and UI - no duplicated logic.

Examples:
    python -m dbvalidator extract --database-config "QA Snowflake" --schema CUSTOMER --filter "AX Tables"
    python -m dbvalidator compare --source-config "QA Snowflake" --destination-config "PROD Snowflake" --filter "AX Tables"
    python -m dbvalidator compare --source schema_v1.json --destination schema_v2.json --report report.html

Exit codes:
    0 = PASS
    1 = Schema differences found (FAIL)
    2 = Configuration/execution error
"""
from __future__ import annotations

import sys
from typing import Optional

import typer

from app.database import init_db, session_scope
from app.schema.canonical import CanonicalSchema
from app.services import comparison_service, config_service, extraction_service, filter_service, schema_service

app = typer.Typer(add_completion=False, help="SchemaSentry CLI - DB Schema Validator")


def _resolve_config_id(db, name_or_id: str) -> str:
    configs = config_service.list_configurations(db)
    for c in configs:
        if c.id == name_or_id or c.name == name_or_id:
            return c.id
    typer.secho(f"Database configuration not found: {name_or_id}", fg="red")
    raise typer.Exit(code=2)


def _resolve_filter_id(db, name_or_id: Optional[str]) -> Optional[str]:
    if not name_or_id:
        return None
    filters = filter_service.list_filters(db)
    for f in filters:
        if f.id == name_or_id or f.name == name_or_id:
            return f.id
    typer.secho(f"Filter not found: {name_or_id}", fg="red")
    raise typer.Exit(code=2)


@app.command()
def extract(
    database_config: str = typer.Option(..., "--database-config", help="Database configuration name or id"),
    database: Optional[str] = typer.Option(None, "--database"),
    schema: Optional[str] = typer.Option(None, "--schema"),
    filter: Optional[str] = typer.Option(None, "--filter", help="Table filter name or id"),
    output: Optional[str] = typer.Option(None, "--output", help="Write canonical JSON to this file"),
    save_version: Optional[str] = typer.Option(None, "--save-version", help="Save as a named schema version"),
):
    """Extract a schema from a live database configuration."""
    init_db()
    with session_scope() as db:
        config_id = _resolve_config_id(db, database_config)
        filter_id = _resolve_filter_id(db, filter)
        filter_name = None
        if filter_id:
            filter_name = filter_service.get_filter_or_404(db, filter_id).name
        try:
            canonical: CanonicalSchema = extraction_service.extract_schema(
                db, config_id, database, schema, filter_id, filter_name
            )
        except Exception as e:  # noqa: BLE001
            typer.secho(f"Extraction failed: {e}", fg="red")
            raise typer.Exit(code=2)

        typer.echo(f"Extracted {canonical.table_count()} tables / {canonical.column_count()} columns")

        if output:
            with open(output, "w") as f:
                f.write(canonical.to_canonical_json())
            typer.echo(f"Wrote {output}")

        if save_version:
            version = schema_service.save_new_schema_version(
                db, save_version, canonical, database_configuration_id=config_id, filter_id=filter_id
            )
            typer.echo(f"Saved schema version '{version.name}' v{version.version} (id={version.id})")


def _stage_json_file(path: str) -> str:
    """Copies an arbitrary CLI-provided JSON file into the managed uploads
    directory (schema JSON may only be read from managed storage - see
    storage/schema_storage.py path-traversal guard) and returns the staged
    path to use as an 'uploaded_json' comparison reference."""
    import shutil
    import uuid

    from app.config import get_settings

    settings = get_settings()
    dest = settings.uploads_dir / f"{uuid.uuid4()}.json"
    shutil.copyfile(path, dest)
    return str(dest)


@app.command()
def compare(
    source: Optional[str] = typer.Option(None, "--source", help="Path to a schema JSON file"),
    destination: Optional[str] = typer.Option(None, "--destination", help="Path to a schema JSON file"),
    source_config: Optional[str] = typer.Option(None, "--source-config", help="Source database configuration name/id"),
    destination_config: Optional[str] = typer.Option(None, "--destination-config", help="Destination database configuration name/id"),
    filter: Optional[str] = typer.Option(None, "--filter", help="Filter applied to both sides"),
    source_filter: Optional[str] = typer.Option(None, "--source-filter"),
    destination_filter: Optional[str] = typer.Option(None, "--destination-filter"),
    schema: Optional[str] = typer.Option(None, "--schema", help="Schema name for live extractions"),
    report: Optional[str] = typer.Option(None, "--report", help="Write the HTML report to this path"),
    fail_on: Optional[str] = typer.Option(None, "--fail-on", help="Comma-separated severities that cause a non-zero exit, e.g. CRITICAL,HIGH"),
):
    """Compare two schemas: live database configurations and/or JSON files."""
    init_db()
    with session_scope() as db:
        if source_config and destination_config:
            src_type, src_ref = "live", _resolve_config_id(db, source_config)
            dst_type, dst_ref = "live", _resolve_config_id(db, destination_config)
        elif source and destination:
            src_type, src_ref = "uploaded_json", _stage_json_file(source)
            dst_type, dst_ref = "uploaded_json", _stage_json_file(destination)
        else:
            typer.secho("Provide either --source/--destination JSON files or --source-config/--destination-config", fg="red")
            raise typer.Exit(code=2)

        src_filter_id = _resolve_filter_id(db, source_filter or filter)
        dst_filter_id = _resolve_filter_id(db, destination_filter or filter)
        fail_on_list = [s.strip().upper() for s in fail_on.split(",")] if fail_on else None

        try:
            comparison_row, result, report_path = comparison_service.run_comparison(
                db, src_type, src_ref, dst_type, dst_ref,
                src_filter_id, dst_filter_id,
                None, schema, None, schema,
                fail_on=fail_on_list,
            )
        except Exception as e:  # noqa: BLE001
            typer.secho(f"Comparison failed: {e}", fg="red")
            raise typer.Exit(code=2)

        typer.echo(f"Status: {result.status}")
        typer.echo(
            f"Tables: {result.summary.tables_compared} compared, {result.summary.tables_added} added, "
            f"{result.summary.tables_removed} removed, {result.summary.tables_modified} modified"
        )
        typer.echo(
            f"Differences: {result.summary.difference_count} total "
            f"(CRITICAL={result.summary.critical_count}, HIGH={result.summary.high_count}, "
            f"MEDIUM={result.summary.medium_count}, LOW={result.summary.low_count})"
        )
        typer.echo(f"Report saved: {report_path}")

        if report:
            import shutil
            shutil.copyfile(report_path, report)
            typer.echo(f"Report copied to: {report}")

        raise typer.Exit(code=0 if result.status == "PASS" else 1)


if __name__ == "__main__":
    app()
