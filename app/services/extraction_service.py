from __future__ import annotations

from sqlalchemy.orm import Session

from app.filters.engine import apply_filter
from app.schema.canonical import CanonicalSchema
from app.services import config_service, filter_service


def list_databases(db: Session, config_id: str) -> list[str]:
    connector, _ = config_service.build_runtime_connector(db, config_id)
    with connector:
        return connector.get_databases()


def list_schemas(db: Session, config_id: str, database: str | None = None) -> list[str]:
    connector, _ = config_service.build_runtime_connector(db, config_id)
    with connector:
        return connector.get_schemas(database)


def list_tables(db: Session, config_id: str, database: str | None, schema: str | None) -> list[str]:
    connector, _ = config_service.build_runtime_connector(db, config_id)
    with connector:
        return connector.get_tables(database, schema)


def preview_tables(
    db: Session, config_id: str, database: str | None, schema: str | None, filter_id: str | None
) -> dict:
    all_tables = list_tables(db, config_id, database, schema)
    if filter_id:
        filtered = filter_service.preview_filter(db, filter_id, all_tables)
    else:
        filtered = list(all_tables)
    return {
        "total_tables": len(all_tables),
        "matched_tables": filtered,
        "matched_count": len(filtered),
        "excluded_tables": sorted(set(all_tables) - set(filtered)),
    }


def extract_schema(
    db: Session,
    config_id: str,
    database: str | None,
    schema: str | None,
    filter_id: str | None = None,
    filter_name: str | None = None,
) -> CanonicalSchema:
    connector, config_obj = config_service.build_runtime_connector(db, config_id)
    with connector:
        all_tables = connector.get_tables(database, schema)
        table_names = all_tables
        if filter_id:
            table_names = filter_service.preview_filter(db, filter_id, all_tables)
        canonical = connector.extract_schema(database, schema, table_names)

    canonical.metadata.database_configuration = config_obj.name
    canonical.metadata.filter = filter_name
    return canonical
