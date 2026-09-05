"""Database Configuration service.

A Database Configuration is the ONLY persisted object needed to connect to
a database. There is no separate Connection entity. Secret fields
(password/pat) are encrypted before being written to app.db and are
decrypted only transiently, in-memory, right before a runtime connector is
created - they are never returned by normal GET operations.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import ConnectionTestResult
from app.connectors.factory import create_connector, supported_database_types
from app.models import DatabaseConfiguration
from app.security.secret_service import get_secret_service

SECRET_FIELDS_BY_TYPE: dict[str, list[str]] = {
    "snowflake": ["pat"],
    "postgresql": ["password"],
    "oracle": ["password"],
    "sqlite": [],
}

REQUIRED_FIELDS_BY_TYPE: dict[str, list[str]] = {
    "snowflake": ["account", "username", "pat", "warehouse", "database", "schema"],
    "postgresql": ["host", "port", "database", "username"],
    "oracle": ["host", "port", "service_name", "username"],
    "sqlite": ["database_file"],
}


class ConfigValidationError(ValueError):
    pass


def _secret_fields(database_type: str) -> list[str]:
    return SECRET_FIELDS_BY_TYPE.get(database_type, [])


def mask_configuration(database_type: str, configuration: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the configuration with secret fields masked for display."""
    masked = dict(configuration)
    for field in _secret_fields(database_type):
        if masked.get(field):
            masked[field] = "********"
    return masked


def validate_configuration(database_type: str, configuration: dict[str, Any]) -> None:
    if database_type not in supported_database_types():
        raise ConfigValidationError(f"Unsupported database_type: {database_type}")
    required = REQUIRED_FIELDS_BY_TYPE.get(database_type, [])
    missing = [f for f in required if not configuration.get(f)]
    if missing:
        raise ConfigValidationError(f"Missing required fields for {database_type}: {', '.join(missing)}")


def _encrypt_secrets(database_type: str, configuration: dict[str, Any]) -> dict[str, Any]:
    secret_service = get_secret_service()
    result = dict(configuration)
    for field in _secret_fields(database_type):
        if result.get(field) and not secret_service.is_encrypted(result[field]):
            result[field] = secret_service.encrypt(result[field])
    return result


def decrypt_configuration(database_type: str, configuration: dict[str, Any]) -> dict[str, Any]:
    """Decrypts secret fields for transient runtime use only. Never persist
    or return the result of this function through an API response."""
    secret_service = get_secret_service()
    result = dict(configuration)
    for field in _secret_fields(database_type):
        if result.get(field):
            result[field] = secret_service.decrypt(result[field])
    return result


def create_configuration(
    db: Session,
    name: str,
    database_type: str,
    configuration: dict[str, Any],
    enabled: bool = True,
    is_default: bool = False,
) -> DatabaseConfiguration:
    validate_configuration(database_type, configuration)
    encrypted_config = _encrypt_secrets(database_type, configuration)

    if is_default:
        _clear_defaults(db)

    obj = DatabaseConfiguration(
        name=name, database_type=database_type, configuration=encrypted_config,
        enabled=enabled, is_default=is_default,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_configuration(
    db: Session,
    config_id: str,
    name: str | None = None,
    configuration: dict[str, Any] | None = None,
    enabled: bool | None = None,
    is_default: bool | None = None,
) -> DatabaseConfiguration:
    obj = get_configuration_or_404(db, config_id)
    if name is not None:
        obj.name = name
    if configuration is not None:
        # Merge with existing so unchanged secret fields (still masked with
        # ******** from a GET response) are preserved rather than overwritten.
        merged = dict(obj.configuration)
        secret_service = get_secret_service()
        for k, v in configuration.items():
            if k in _secret_fields(obj.database_type) and v == "********":
                continue  # unchanged secret placeholder - keep existing encrypted value
            merged[k] = v
        validate_configuration(obj.database_type, merged)
        obj.configuration = _encrypt_secrets(obj.database_type, merged)
    if enabled is not None:
        obj.enabled = enabled
    if is_default is not None and is_default:
        _clear_defaults(db)
        obj.is_default = True
    elif is_default is not None:
        obj.is_default = False
    obj.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return obj


def _clear_defaults(db: Session) -> None:
    db.query(DatabaseConfiguration).filter(DatabaseConfiguration.is_default.is_(True)).update({"is_default": False})


def clone_configuration(db: Session, config_id: str, new_name: str) -> DatabaseConfiguration:
    src = get_configuration_or_404(db, config_id)
    obj = DatabaseConfiguration(
        name=new_name, database_type=src.database_type,
        configuration=dict(src.configuration), enabled=src.enabled, is_default=False,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def delete_configuration(db: Session, config_id: str) -> None:
    obj = get_configuration_or_404(db, config_id)
    db.delete(obj)
    db.commit()


def get_configuration_or_404(db: Session, config_id: str) -> DatabaseConfiguration:
    obj = db.get(DatabaseConfiguration, config_id)
    if obj is None:
        raise LookupError(f"Database configuration not found: {config_id}")
    return obj


def list_configurations(db: Session) -> list[DatabaseConfiguration]:
    return list(db.scalars(select(DatabaseConfiguration).order_by(DatabaseConfiguration.name)))


def test_configuration(db: Session, config_id: str) -> ConnectionTestResult:
    obj = get_configuration_or_404(db, config_id)
    runtime_config = decrypt_configuration(obj.database_type, obj.configuration)
    connector = create_connector(obj.database_type, runtime_config)
    result = connector.test_connection()
    obj.last_tested_at = datetime.now(timezone.utc)
    obj.last_test_status = "SUCCESS" if result.success else "FAILURE"
    obj.last_test_message = result.message
    db.commit()
    return result


def test_adhoc_configuration(
    db: Session,
    database_type: str,
    configuration: dict[str, Any],
    existing_config_id: str | None = None,
) -> ConnectionTestResult:
    """Tests connectivity using whatever is currently in the form, without
    requiring the configuration to be saved first. This is what the UI's
    'Test Configuration' button calls - it always reflects the latest,
    possibly-unsaved field values, so editing the database file / host /
    port and testing again never uses stale data.

    If `existing_config_id` is given and the payload still contains the
    masked secret placeholder ("********") for a field, the real decrypted
    secret from the existing saved configuration is substituted in so
    editing non-secret fields doesn't require re-entering the password/PAT.
    """
    validate_configuration(database_type, configuration)
    runtime_config = dict(configuration)

    if existing_config_id:
        existing = get_configuration_or_404(db, existing_config_id)
        if existing.database_type == database_type:
            decrypted_existing = decrypt_configuration(existing.database_type, existing.configuration)
            for field in _secret_fields(database_type):
                if runtime_config.get(field) == "********":
                    runtime_config[field] = decrypted_existing.get(field)

    connector = create_connector(database_type, runtime_config)
    return connector.test_connection()


def build_runtime_connector(db: Session, config_id: str):
    """Build a runtime connector for a configuration. Caller is responsible
    for connect()/close() (a context manager is recommended)."""
    obj = get_configuration_or_404(db, config_id)
    runtime_config = decrypt_configuration(obj.database_type, obj.configuration)
    return create_connector(obj.database_type, runtime_config), obj
