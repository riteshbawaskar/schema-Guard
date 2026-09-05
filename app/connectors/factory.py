"""Connector factory: DatabaseConfiguration -> runtime DatabaseConnector.

This is the ONLY place that turns a persisted configuration into a live
connector instance. Runtime connectors and connections are never persisted.
"""
from __future__ import annotations

from typing import Any

from app.connectors.base import DatabaseConnector
from app.connectors.oracle_connector import OracleConnector
from app.connectors.postgres_connector import PostgreSQLConnector
from app.connectors.snowflake_connector import SnowflakeConnector
from app.connectors.sqlite_connector import SQLiteConnector

_REGISTRY: dict[str, type[DatabaseConnector]] = {
    "snowflake": SnowflakeConnector,
    "oracle": OracleConnector,
    "postgresql": PostgreSQLConnector,
    "sqlite": SQLiteConnector,
}


def register_connector(database_type: str, connector_cls: type[DatabaseConnector]) -> None:
    """Allows extending with new database types (SQL Server, MySQL, DB2,
    Redshift, Databricks, BigQuery, ...) without modifying this module."""
    _REGISTRY[database_type] = connector_cls


def supported_database_types() -> list[str]:
    return sorted(_REGISTRY.keys())


def create_connector(database_type: str, configuration: dict[str, Any]) -> DatabaseConnector:
    if database_type not in _REGISTRY:
        raise ValueError(
            f"Unsupported database type '{database_type}'. "
            f"Supported: {', '.join(supported_database_types())}"
        )
    return _REGISTRY[database_type](configuration)
