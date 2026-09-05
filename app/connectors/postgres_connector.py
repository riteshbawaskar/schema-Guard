from __future__ import annotations

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

try:
    import psycopg2
    import psycopg2.extras
    _HAS_PSYCOPG2 = True
except ImportError:  # pragma: no cover
    _HAS_PSYCOPG2 = False


class PostgreSQLConnector(DatabaseConnector):
    database_type = "postgresql"

    def connect(self) -> None:
        if not _HAS_PSYCOPG2:
            raise RuntimeError(
                "psycopg2-binary is not installed. Install it to enable PostgreSQL connectivity."
            )
        cfg = self.configuration
        self._conn = psycopg2.connect(
            host=cfg["host"],
            port=cfg.get("port", 5432),
            dbname=cfg["database"],
            user=cfg["username"],
            password=cfg.get("password"),
            sslmode=cfg.get("ssl_mode", "prefer"),
            connect_timeout=10,
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def test_connection(self) -> ConnectionTestResult:
        try:
            self.connect()
            with self._conn.cursor() as cur:
                cur.execute("SELECT 1")
            return ConnectionTestResult(True, "Connection successful")
        except Exception as e:  # noqa: BLE001
            return ConnectionTestResult(False, f"Connection failed: {e}")
        finally:
            self.close()

    def get_databases(self) -> list[str]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname")
            return [r[0] for r in cur.fetchall()]

    def get_schemas(self, database: str | None = None) -> list[str]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name NOT IN ('pg_catalog','information_schema') ORDER BY schema_name"
            )
            return [r[0] for r in cur.fetchall()]

    def get_tables(self, database: str | None, schema: str | None) -> list[str]:
        schema = schema or self.configuration.get("schema", "public")
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s AND table_type='BASE TABLE' ORDER BY table_name",
                (schema,),
            )
            return [r[0] for r in cur.fetchall()]

    def extract_schema(
        self,
        database: str | None,
        schema: str | None,
        table_names: list[str] | None = None,
    ) -> CanonicalSchema:
        schema = schema or self.configuration.get("schema", "public")
        owns_connection = self._conn is None
        if owns_connection:
            self.connect()
        try:
            tables_to_extract = table_names if table_names is not None else self.get_tables(database, schema)
            tables = [self._extract_table(schema, t) for t in tables_to_extract]
            meta = SchemaMetadata(
                database_type=self.database_type,
                database=self.configuration.get("database"),
                schema=schema,
            )
            return CanonicalSchema(metadata=meta, tables=tables).sorted()
        finally:
            if owns_connection:
                self.close()

    def _extract_table(self, schema: str, table_name: str) -> TableModel:
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(
            """
            SELECT column_name, ordinal_position, data_type, character_maximum_length,
                   numeric_precision, numeric_scale, is_nullable, column_default,
                   is_identity
            FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s
            ORDER BY ordinal_position
            """,
            (schema, table_name),
        )
        columns = []
        for row in cur.fetchall():
            columns.append(
                ColumnModel(
                    name=row["column_name"],
                    ordinal_position=row["ordinal_position"],
                    native_datatype=row["data_type"],
                    normalized_datatype=normalize_datatype(self.database_type, row["data_type"]),
                    length=row["character_maximum_length"],
                    precision=row["numeric_precision"],
                    scale=row["numeric_scale"],
                    nullable=row["is_nullable"] == "YES",
                    default=row["column_default"],
                    is_identity=row["is_identity"] == "YES",
                )
            )

        pk = self._extract_primary_key(cur, schema, table_name)
        fks = self._extract_foreign_keys(cur, schema, table_name)
        uniques = self._extract_unique_constraints(cur, schema, table_name)
        indexes = self._extract_indexes(cur, schema, table_name)
        checks = self._extract_check_constraints(cur, schema, table_name)
        cur.close()
        return TableModel(
            name=table_name,
            columns=columns,
            primary_key=pk,
            foreign_keys=fks,
            unique_constraints=uniques,
            indexes=indexes,
            check_constraints=checks,
        )

    def _extract_primary_key(self, cur, schema, table_name) -> PrimaryKeyModel | None:
        cur.execute(
            """
            SELECT tc.constraint_name, kcu.column_name, kcu.ordinal_position
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type='PRIMARY KEY' AND tc.table_schema=%s AND tc.table_name=%s
            ORDER BY kcu.ordinal_position
            """,
            (schema, table_name),
        )
        rows = cur.fetchall()
        if not rows:
            return None
        return PrimaryKeyModel(name=rows[0]["constraint_name"], columns=[r["column_name"] for r in rows])

    def _extract_foreign_keys(self, cur, schema, table_name) -> list[ForeignKeyModel]:
        cur.execute(
            """
            SELECT tc.constraint_name, kcu.column_name, kcu.ordinal_position,
                   ccu.table_name AS ref_table, ccu.column_name AS ref_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
            WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema=%s AND tc.table_name=%s
            ORDER BY tc.constraint_name, kcu.ordinal_position
            """,
            (schema, table_name),
        )
        grouped: dict[str, dict[str, Any]] = {}
        for row in cur.fetchall():
            g = grouped.setdefault(row["constraint_name"], {"columns": [], "ref_table": row["ref_table"], "ref_columns": []})
            g["columns"].append(row["column_name"])
            g["ref_columns"].append(row["ref_column"])
        return [
            ForeignKeyModel(name=name, columns=d["columns"], referenced_table=d["ref_table"], referenced_columns=d["ref_columns"])
            for name, d in grouped.items()
        ]

    def _extract_unique_constraints(self, cur, schema, table_name) -> list[UniqueConstraintModel]:
        cur.execute(
            """
            SELECT tc.constraint_name, kcu.column_name, kcu.ordinal_position
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type='UNIQUE' AND tc.table_schema=%s AND tc.table_name=%s
            ORDER BY tc.constraint_name, kcu.ordinal_position
            """,
            (schema, table_name),
        )
        grouped: dict[str, list[str]] = {}
        for row in cur.fetchall():
            grouped.setdefault(row["constraint_name"], []).append(row["column_name"])
        return [UniqueConstraintModel(name=name, columns=cols) for name, cols in grouped.items()]

    def _extract_indexes(self, cur, schema, table_name) -> list[IndexModel]:
        cur.execute(
            """
            SELECT i.relname AS index_name, ix.indisunique AS is_unique,
                   a.attname AS column_name, array_position(ix.indkey, a.attnum) AS pos,
                   am.amname AS index_type
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_am am ON i.relam = am.oid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE t.relname = %s AND n.nspname = %s AND NOT ix.indisprimary
            ORDER BY i.relname, pos
            """,
            (table_name, schema),
        )
        grouped: dict[str, dict[str, Any]] = {}
        for row in cur.fetchall():
            g = grouped.setdefault(row["index_name"], {"unique": row["is_unique"], "columns": [], "type": row["index_type"]})
            g["columns"].append(row["column_name"])
        return [IndexModel(name=n, columns=d["columns"], unique=d["unique"], index_type=d["type"]) for n, d in grouped.items()]

    def _extract_check_constraints(self, cur, schema, table_name) -> list[CheckConstraintModel]:
        cur.execute(
            """
            SELECT con.conname AS name, pg_get_constraintdef(con.oid) AS definition
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
            WHERE con.contype = 'c' AND rel.relname = %s AND nsp.nspname = %s
            """,
            (table_name, schema),
        )
        return [CheckConstraintModel(name=row["name"], expression=row["definition"]) for row in cur.fetchall()]
