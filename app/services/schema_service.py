from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SchemaVersion
from app.schema.canonical import CanonicalSchema
from app.storage import schema_storage


def save_new_schema_version(
    db: Session,
    name: str,
    schema: CanonicalSchema,
    description: str | None = None,
    database_configuration_id: str | None = None,
    filter_id: str | None = None,
    schema_group_id: str | None = None,
) -> SchemaVersion:
    """Saves a new version. `schema_group_id` groups multiple versions of the
    'same' logical schema together (e.g. re-extractions over time); if not
    given, a fresh id is used (this is the first version of a new group)."""
    import uuid
    group_id = schema_group_id or str(uuid.uuid4())
    version_num = schema_storage.next_version_number(group_id)
    path, checksum = schema_storage.save_schema_version(group_id, version_num, schema)

    obj = SchemaVersion(
        name=name, version=version_num, description=description,
        database_configuration_id=database_configuration_id,
        database_type=schema.metadata.database_type,
        database_name=schema.metadata.database,
        schema_name=schema.metadata.schema_name,
        filter_id=filter_id,
        file_path=str(path),
        checksum=checksum,
        table_count=schema.table_count(),
        column_count=schema.column_count(),
    )
    # Stash the group id on file_path's parent so future versions can be
    # linked; simplest approach: encode group id in the id itself is not
    # possible (id is a distinct uuid), so we rely on directory name.
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_group_id_from_path(file_path: str) -> str:
    from pathlib import Path
    return Path(file_path).parent.name


def list_versions(db: Session) -> list[SchemaVersion]:
    return list(db.scalars(select(SchemaVersion).order_by(SchemaVersion.created_at.desc())))


def get_version_or_404(db: Session, version_id: str) -> SchemaVersion:
    obj = db.get(SchemaVersion, version_id)
    if obj is None:
        raise LookupError(f"Schema version not found: {version_id}")
    return obj


def list_versions_in_group(db: Session, group_id: str) -> list[SchemaVersion]:
    versions = list_versions(db)
    return [v for v in versions if get_group_id_from_path(v.file_path) == group_id]


def rename_version(db: Session, version_id: str, new_name: str) -> SchemaVersion:
    obj = get_version_or_404(db, version_id)
    obj.name = new_name
    db.commit()
    db.refresh(obj)
    return obj


def describe_version(db: Session, version_id: str, description: str) -> SchemaVersion:
    obj = get_version_or_404(db, version_id)
    obj.description = description
    db.commit()
    db.refresh(obj)
    return obj


def delete_version(db: Session, version_id: str) -> None:
    obj = get_version_or_404(db, version_id)
    from pathlib import Path
    try:
        Path(obj.file_path).unlink(missing_ok=True)
    except Exception:
        pass
    db.delete(obj)
    db.commit()


def load_canonical_schema(version: SchemaVersion) -> CanonicalSchema:
    return schema_storage.load_schema_from_path(version.file_path)


def import_uploaded_schema(db: Session, name: str, canonical: CanonicalSchema, description: str | None = None) -> SchemaVersion:
    return save_new_schema_version(db, name=name, schema=canonical, description=description or "Imported from uploaded JSON")
