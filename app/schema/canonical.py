"""Canonical, deterministic, versioned JSON schema representation.

Every supported database is extracted into this single format so that
comparison logic never needs to know about source-specific quirks.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

SCHEMA_FORMAT_VERSION = "1.0"


class ColumnModel(BaseModel):
    name: str
    ordinal_position: int
    native_datatype: str
    normalized_datatype: str
    length: Optional[int] = None
    precision: Optional[int] = None
    scale: Optional[int] = None
    nullable: bool = True
    default: Optional[str] = None
    is_identity: bool = False
    comment: Optional[str] = None
    source_properties: dict[str, str | None] = Field(default_factory=dict)


class PrimaryKeyModel(BaseModel):
    name: Optional[str] = None
    columns: list[str] = Field(default_factory=list)


class ForeignKeyModel(BaseModel):
    name: Optional[str] = None
    columns: list[str] = Field(default_factory=list)
    referenced_table: str
    referenced_columns: list[str] = Field(default_factory=list)


class UniqueConstraintModel(BaseModel):
    name: Optional[str] = None
    columns: list[str] = Field(default_factory=list)


class CheckConstraintModel(BaseModel):
    name: Optional[str] = None
    expression: Optional[str] = None


class IndexModel(BaseModel):
    name: str
    columns: list[str] = Field(default_factory=list)
    unique: bool = False
    index_type: Optional[str] = None


class TableModel(BaseModel):
    name: str
    type: str = "TABLE"
    comment: Optional[str] = None
    columns: list[ColumnModel] = Field(default_factory=list)
    primary_key: Optional[PrimaryKeyModel] = None
    foreign_keys: list[ForeignKeyModel] = Field(default_factory=list)
    unique_constraints: list[UniqueConstraintModel] = Field(default_factory=list)
    indexes: list[IndexModel] = Field(default_factory=list)
    check_constraints: list[CheckConstraintModel] = Field(default_factory=list)


class SchemaMetadata(BaseModel):
    database_type: str
    database_configuration: Optional[str] = None
    database: Optional[str] = None
    schema_name: Optional[str] = Field(default=None, alias="schema")
    filter: Optional[str] = None
    extracted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    model_config = {"populate_by_name": True}


class CanonicalSchema(BaseModel):
    schema_format_version: str = SCHEMA_FORMAT_VERSION
    metadata: SchemaMetadata
    tables: list[TableModel] = Field(default_factory=list)

    def sorted(self) -> "CanonicalSchema":
        """Return a deterministically sorted copy (tables/columns/etc)."""
        tables = []
        for t in sorted(self.tables, key=lambda x: x.name):
            t2 = t.model_copy(deep=True)
            t2.columns = sorted(t2.columns, key=lambda c: c.name)
            t2.foreign_keys = sorted(t2.foreign_keys, key=lambda f: (f.name or "", tuple(f.columns)))
            t2.unique_constraints = sorted(t2.unique_constraints, key=lambda u: (u.name or "", tuple(u.columns)))
            t2.check_constraints = sorted(t2.check_constraints, key=lambda c: (c.name or ""))
            t2.indexes = sorted(t2.indexes, key=lambda i: i.name)
            tables.append(t2)
        return CanonicalSchema(
            schema_format_version=self.schema_format_version,
            metadata=self.metadata,
            tables=tables,
        )

    def table_count(self) -> int:
        """Return the number of tables represented in this schema."""
        return len(self.tables)

    def column_count(self) -> int:
        """Return the total number of columns across all represented tables."""
        return sum(len(t.columns) for t in self.tables)

    def to_canonical_json(self) -> str:
        """Deterministic JSON string (sorted keys, sorted collections)."""
        import json
        data = self.sorted().model_dump(mode="json", by_alias=True, exclude_unset=True)
        return json.dumps(data, sort_keys=True, indent=2)
