"""SQLAlchemy ORM models for the application metadata store (data/app.db).

Note: there is intentionally NO Connection entity/table. A "Database
Configuration" holds everything needed to connect; runtime connections are
created on demand via the connector factory and never persisted.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DatabaseConfiguration(Base):
    __tablename__ = "database_configurations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    database_type: Mapped[str] = mapped_column(String(32), nullable=False)  # snowflake|oracle|postgresql|sqlite
    # `configuration` holds all connection details as JSON. Secret fields
    # (password/pat) are encrypted at rest via SecretService before storage.
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_status: Mapped[str | None] = mapped_column(String(32), nullable=True)  # SUCCESS|FAILURE
    last_test_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class TableFilter(Base):
    __tablename__ = "table_filters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_mode: Mapped[str] = mapped_column(String(32), nullable=False)  # starts_with|ends_with|contains|exact|wildcard|regex
    include_patterns: Mapped[list] = mapped_column(JSON, default=list)
    exclude_patterns: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class SchemaVersion(Base):
    __tablename__ = "schema_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    database_configuration_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("database_configurations.id"), nullable=True
    )
    database_type: Mapped[str] = mapped_column(String(32), nullable=False)
    database_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    schema_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filter_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("table_filters.id"), nullable=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    table_count: Mapped[int] = mapped_column(Integer, default=0)
    column_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    database_configuration = relationship("DatabaseConfiguration")
    table_filter = relationship("TableFilter")


class Comparison(Base):
    __tablename__ = "comparisons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # live|schema_version|uploaded_json
    source_reference: Mapped[str] = mapped_column(String(1024), nullable=False)
    destination_type: Mapped[str] = mapped_column(String(32), nullable=False)
    destination_reference: Mapped[str] = mapped_column(String(1024), nullable=False)
    # Human-readable labels resolved at comparison time (e.g. a database
    # configuration name or "MyVersion (v3)") so history/reports/dashboard
    # never have to show raw ids or file paths.
    source_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    destination_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_filter_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("table_filters.id"), nullable=True)
    destination_filter_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("table_filters.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")  # PENDING|RUNNING|PASS|FAIL|ERROR
    table_count: Mapped[int] = mapped_column(Integer, default=0)
    column_count: Mapped[int] = mapped_column(Integer, default=0)
    difference_count: Mapped[int] = mapped_column(Integer, default=0)
    critical_count: Mapped[int] = mapped_column(Integer, default=0)
    high_count: Mapped[int] = mapped_column(Integer, default=0)
    medium_count: Mapped[int] = mapped_column(Integer, default=0)
    low_count: Mapped[int] = mapped_column(Integer, default=0)
    info_count: Mapped[int] = mapped_column(Integer, default=0)
    report_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    duration: Mapped[float | None] = mapped_column(nullable=True)  # seconds


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    comparison_id: Mapped[str] = mapped_column(String(36), ForeignKey("comparisons.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    comparison = relationship("Comparison")
