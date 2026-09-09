from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class FieldDiff(BaseModel):
    """A single field-level difference within a modified object."""
    category: str  # datatype|length|precision|scale|nullable|default|identity|position|comment
    field: str
    source_value: Any = None
    destination_value: Any = None
    severity: str


class ObjectDiff(BaseModel):
    """A difference for a single named object (column, index, key, etc.)."""
    object_type: str  # column|primary_key|foreign_key|unique_constraint|check_constraint|index
    name: str
    diff_type: str  # ADDED|REMOVED|MODIFIED|UNCHANGED
    severity: str
    field_diffs: list[FieldDiff] = Field(default_factory=list)
    source_value: Optional[dict] = None
    destination_value: Optional[dict] = None


class TableDiff(BaseModel):
    table_name: str
    diff_type: str  # ADDED|REMOVED|MODIFIED|UNCHANGED
    severity: str
    column_diffs: list[ObjectDiff] = Field(default_factory=list)
    primary_key_diff: Optional[ObjectDiff] = None
    foreign_key_diffs: list[ObjectDiff] = Field(default_factory=list)
    unique_constraint_diffs: list[ObjectDiff] = Field(default_factory=list)
    check_constraint_diffs: list[ObjectDiff] = Field(default_factory=list)
    index_diffs: list[ObjectDiff] = Field(default_factory=list)

    def has_differences(self) -> bool:
        if self.diff_type != "UNCHANGED":
            return True
        collections = [
            self.column_diffs, self.foreign_key_diffs, self.unique_constraint_diffs,
            self.check_constraint_diffs, self.index_diffs,
        ]
        if self.primary_key_diff and self.primary_key_diff.diff_type != "UNCHANGED":
            return True
        return any(d.diff_type != "UNCHANGED" for coll in collections for d in coll)


class ComparisonSummary(BaseModel):
    tables_compared: int = 0
    tables_added: int = 0
    tables_removed: int = 0
    tables_modified: int = 0
    tables_unchanged: int = 0
    columns_added: int = 0
    columns_removed: int = 0
    columns_modified: int = 0
    difference_count: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    info_count: int = 0
    warning_count: int = 0


class ComparisonResult(BaseModel):
    source_label: str
    destination_label: str
    source_format: str = "database"  # xml|database
    destination_format: str = "database"  # xml|database
    source_filter: Optional[str] = None
    destination_filter: Optional[str] = None
    normalization_mode: str = "compatible"
    status: str = "PASS"  # PASS|FAIL
    summary: ComparisonSummary = Field(default_factory=ComparisonSummary)
    table_diffs: list[TableDiff] = Field(default_factory=list)
    removed_by_filter: dict[str, list[str]] = Field(default_factory=dict)
