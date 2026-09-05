"""Abstract connector interface. All database-specific connectors implement
this so that services/UI/CLI never depend on driver-specific details.

A connector is always constructed from a runtime configuration dict (never
from a persisted "Connection" object) and is short-lived: created, used,
closed.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.schema.canonical import CanonicalSchema


@dataclass
class ConnectionTestResult:
    success: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


class DatabaseConnector(ABC):
    """Abstract connector. Implementations must never log or persist secrets."""

    database_type: str = "unknown"

    def __init__(self, configuration: dict[str, Any]):
        self.configuration = configuration
        self._conn: Any = None

    # -- lifecycle -----------------------------------------------------
    @abstractmethod
    def connect(self) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    def __enter__(self) -> "DatabaseConnector":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @abstractmethod
    def test_connection(self) -> ConnectionTestResult:
        ...

    # -- discovery -------------------------------------------------------
    @abstractmethod
    def get_databases(self) -> list[str]:
        ...

    @abstractmethod
    def get_schemas(self, database: str | None = None) -> list[str]:
        ...

    @abstractmethod
    def get_tables(self, database: str | None, schema: str | None) -> list[str]:
        ...

    # -- extraction --------------------------------------------------------
    @abstractmethod
    def extract_schema(
        self,
        database: str | None,
        schema: str | None,
        table_names: list[str] | None = None,
    ) -> CanonicalSchema:
        """Extract full metadata for the given (optionally filtered) tables
        and return it as a CanonicalSchema. `table_names`, when provided,
        restricts extraction to exactly those tables (already filtered)."""
        ...
