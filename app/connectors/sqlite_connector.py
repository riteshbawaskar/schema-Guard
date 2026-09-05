from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from app.connectors.base import ConnectionTestResult, DatabaseConnector
from app.schema.canonical import (
    CanonicalSchema,
    CheckConstraintModel,
    ColumnModel,
    ForeignKeyModel,
    IndexModel,
    PrimaryKeyModel,
    SchemaMetadata,
    TableModel,
    UniqueConstraintModel,
)
from app.schema.normalization import normalize_datatype


class SQLiteConnector(DatabaseConnector):
    database_type = "sqlite"

    def connect(self) -> None:
        db_file = self.configuration.get("database_file")
        if not db_file:
            raise ValueError("SQLite configuration requires 'database_file'")
        if not Path(db_file).exists():
            raise FileNotFoundError(f"SQLite database file not found: {db_file}")
        self._conn = sqlite3.connect(db_file)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def test_connection(self) -> ConnectionTestResult:
        try:
            self.connect()
            self._conn.execute("SELECT 1")
            return ConnectionTestResult(True, "Connection successful")
        except Exception as e:  # noqa: BLE001
            return ConnectionTestResult(False, f"Connection failed: {e}")
        finally:
            self.close()

    def get_databases(self) -> list[str]:
        # SQLite has a single implicit database (the file itself).
        return [Path(self.configuration.get("database_file", "main")).stem]

    def get_schemas(self, database: str | None = None) -> list[str]:
        # SQLite has no schema concept beyond "main".
        return ["main"]

    def get_tables(self, database: str | None, schema: str | None) -> list[str]:
        cur = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        return [row["name"] for row in cur.fetchall()]

    def extract_schema(
        self,
        database: str | None,
        schema: str | None,
        table_names: list[str] | None = None,
    ) -> CanonicalSchema:
        owns_connection = self._conn is None
        if owns_connection:
            self.connect()
        try:
            tables_to_extract = table_names if table_names is not None else self.get_tables(database, schema)
            tables: list[TableModel] = []
            for tname in tables_to_extract:
                tables.append(self._extract_table(tname))
            meta = SchemaMetadata(
                database_type=self.database_type,
                database=database or self.get_databases()[0],
                schema="main",
            )
            return CanonicalSchema(metadata=meta, tables=tables).sorted()
        finally:
            if owns_connection:
                self.close()

    # -- internals ----------------------------------------------------------
    def _extract_table(self, table_name: str) -> TableModel:
        columns = self._extract_columns(table_name)
        pk = self._extract_primary_key(table_name)
        fks = self._extract_foreign_keys(table_name)
        indexes, unique_constraints = self._extract_indexes(table_name)
        checks = self._extract_check_constraints(table_name)
        return TableModel(
            name=table_name,
            type="TABLE",
            columns=columns,
            primary_key=pk,
            foreign_keys=fks,
            unique_constraints=unique_constraints,
            indexes=indexes,
            check_constraints=checks,
        )

    def _extract_columns(self, table_name: str) -> list[ColumnModel]:
        cur = self._conn.execute(f"PRAGMA table_info('{table_name}')")
        columns = []
        for row in cur.fetchall():
            native = row["type"] or "TEXT"
            columns.append(
                ColumnModel(
                    name=row["name"],
                    ordinal_position=row["cid"] + 1,
                    native_datatype=native,
                    normalized_datatype=normalize_datatype(self.database_type, native),
                    nullable=not bool(row["notnull"]),
                    default=row["dflt_value"],
                    is_identity=bool(row["pk"]) and native.upper() == "INTEGER",
                )
            )
        return columns

    def _extract_primary_key(self, table_name: str) -> PrimaryKeyModel | None:
        cur = self._conn.execute(f"PRAGMA table_info('{table_name}')")
        pk_cols = [(row["pk"], row["name"]) for row in cur.fetchall() if row["pk"] > 0]
        if not pk_cols:
            return None
        pk_cols.sort(key=lambda x: x[0])
        return PrimaryKeyModel(name=f"pk_{table_name}", columns=[c[1] for c in pk_cols])

    def _extract_foreign_keys(self, table_name: str) -> list[ForeignKeyModel]:
        cur = self._conn.execute(f"PRAGMA foreign_key_list('{table_name}')")
        grouped: dict[int, dict[str, Any]] = {}
        for row in cur.fetchall():
            gid = row["id"]
            grouped.setdefault(
                gid, {"table": row["table"], "from": [], "to": []}
            )
            grouped[gid]["from"].append(row["from"])
            grouped[gid]["to"].append(row["to"])
        fks = []
        for gid, data in grouped.items():
            fks.append(
                ForeignKeyModel(
                    name=f"fk_{table_name}_{gid}",
                    columns=data["from"],
                    referenced_table=data["table"],
                    referenced_columns=data["to"],
                )
            )
        return fks

    def _extract_indexes(self, table_name: str) -> tuple[list[IndexModel], list[UniqueConstraintModel]]:
        cur = self._conn.execute(f"PRAGMA index_list('{table_name}')")
        indexes = []
        unique_constraints = []
        for row in cur.fetchall():
            idx_name = row["name"]
            is_unique = bool(row["unique"])
            origin = row["origin"] if "origin" in row.keys() else None
            col_cur = self._conn.execute(f"PRAGMA index_info('{idx_name}')")
            cols = [c["name"] for c in col_cur.fetchall()]
            if origin == "u":
                # Implicit unique constraint (not an explicit CREATE INDEX)
                unique_constraints.append(UniqueConstraintModel(name=idx_name, columns=cols))
            else:
                indexes.append(IndexModel(name=idx_name, columns=cols, unique=is_unique))
        return indexes, unique_constraints

    def _extract_check_constraints(self, table_name: str) -> list[CheckConstraintModel]:
        cur = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
        )
        row = cur.fetchone()
        checks: list[CheckConstraintModel] = []
        if row and row["sql"]:
            sql = row["sql"]
            import re
            for i, match in enumerate(re.finditer(r"CHECK\s*\((.*?)\)(?=[,\n]|$)", sql, re.IGNORECASE | re.DOTALL)):
                checks.append(CheckConstraintModel(name=f"chk_{table_name}_{i+1}", expression=match.group(1).strip()))
        return checks
