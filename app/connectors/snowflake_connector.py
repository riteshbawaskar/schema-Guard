from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

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
    import snowflake.connector
    _HAS_SNOWFLAKE = True
except ImportError:  # pragma: no cover
    _HAS_SNOWFLAKE = False


class SnowflakeConnector(DatabaseConnector):
    """Connects with a PAT or Snowflake browser-based SSO."""

    database_type = "snowflake"

    def connect(self) -> None:
        if not _HAS_SNOWFLAKE:
            raise RuntimeError(
                "snowflake-connector-python is not installed. Install it to enable Snowflake connectivity."
            )
        cfg = self.configuration
        connection_args = {
            "account": cfg["account"],
            "user": cfg["username"],
            "warehouse": cfg.get("warehouse"),
            "database": cfg.get("database"),
            "schema": cfg.get("schema"),
            "role": cfg.get("role"),
            "login_timeout": 15,
        }
        authentication = cfg.get("authentication", "pat")
        if authentication == "sso":
            connection_args["authenticator"] = "externalbrowser"
        else:
            connection_args["password"] = cfg.get("pat")

        url = cfg.get("url")
        if url:
            parsed = urlparse(url if "://" in url else f"https://{url}")
            if not parsed.hostname:
                raise ValueError("Snowflake URL must include a host")
            connection_args["host"] = parsed.hostname
            if parsed.port:
                connection_args["port"] = parsed.port

        self._conn = snowflake.connector.connect(**connection_args)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def test_connection(self) -> ConnectionTestResult:
        try:
            self.connect()
            cur = self._conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            return ConnectionTestResult(True, "Connection successful")
        except Exception as e:  # noqa: BLE001
            return ConnectionTestResult(False, f"Connection failed: {e}")
        finally:
            self.close()

    def get_databases(self) -> list[str]:
        cur = self._conn.cursor()
        cur.execute("SHOW DATABASES")
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        name_idx = cols.index("name")
        cur.close()
        return [r[name_idx] for r in rows]

    def get_schemas(self, database: str | None = None) -> list[str]:
        database = database or self.configuration.get("database")
        cur = self._conn.cursor()
        cur.execute(f"SHOW SCHEMAS IN DATABASE {database}")
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        name_idx = cols.index("name")
        cur.close()
        return [r[name_idx] for r in rows]

    def get_tables(self, database: str | None, schema: str | None) -> list[str]:
        database = database or self.configuration.get("database")
        schema = schema or self.configuration.get("schema")
        cur = self._conn.cursor()
        cur.execute(
            "SELECT table_name FROM %s.information_schema.tables "
            "WHERE table_schema = %%s AND table_type='BASE TABLE' ORDER BY table_name" % database,
            (schema,),
        )
        result = [r[0] for r in cur.fetchall()]
        cur.close()
        return result

    def extract_schema(
        self,
        database: str | None,
        schema: str | None,
        table_names: list[str] | None = None,
    ) -> CanonicalSchema:
        database = database or self.configuration.get("database")
        schema = schema or self.configuration.get("schema")
        owns_connection = self._conn is None
        if owns_connection:
            self.connect()
        try:
            tables_to_extract = table_names if table_names is not None else self.get_tables(database, schema)
            tables = [self._extract_table(database, schema, t) for t in tables_to_extract]
            meta = SchemaMetadata(database_type=self.database_type, database=database, schema=schema)
            return CanonicalSchema(metadata=meta, tables=tables).sorted()
        finally:
            if owns_connection:
                self.close()

    def _extract_table(self, database: str, schema: str, table_name: str) -> TableModel:
        cur = self._conn.cursor()
        cur.execute(
            f"""
            SELECT column_name, ordinal_position, data_type, character_maximum_length,
                   numeric_precision, numeric_scale, is_nullable, column_default,
                   is_identity, comment
            FROM {database}.information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema, table_name),
        )
        columns = []
        for row in cur.fetchall():
            (cname, pos, dtype, clen, prec, scale, nullable, default, identity, comment) = row
            columns.append(
                ColumnModel(
                    name=cname, ordinal_position=pos, native_datatype=dtype,
                    normalized_datatype=normalize_datatype(self.database_type, dtype),
                    length=clen, precision=prec, scale=scale,
                    nullable=(nullable == "YES"), default=default,
                    is_identity=(identity == "YES"), comment=comment,
                )
            )
        pk = self._extract_primary_key(database, schema, table_name)
        fks = self._extract_foreign_keys(database, schema, table_name)
        indexes: list[IndexModel] = []  # Snowflake does not expose classic secondary indexes
        checks: list[CheckConstraintModel] = []  # Snowflake does not enforce CHECK constraints
        cur.close()
        return TableModel(
            name=table_name, columns=columns, primary_key=pk, foreign_keys=fks,
            unique_constraints=self._extract_unique_constraints(database, schema, table_name),
            indexes=indexes, check_constraints=checks,
        )

    def _extract_primary_key(self, database, schema, table_name) -> PrimaryKeyModel | None:
        cur = self._conn.cursor()
        cur.execute(f"SHOW PRIMARY KEYS IN TABLE {database}.{schema}.{table_name}")
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        cur.close()
        if not rows:
            return None
        col_idx = cols.index("column_name")
        key_idx = cols.index("key_sequence") if "key_sequence" in cols else None
        pk_name_idx = cols.index("constraint_name") if "constraint_name" in cols else None
        ordered = sorted(rows, key=lambda r: r[key_idx]) if key_idx is not None else rows
        return PrimaryKeyModel(
            name=ordered[0][pk_name_idx] if pk_name_idx is not None else f"pk_{table_name}",
            columns=[r[col_idx] for r in ordered],
        )

    def _extract_foreign_keys(self, database, schema, table_name) -> list[ForeignKeyModel]:
        cur = self._conn.cursor()
        cur.execute(f"SHOW IMPORTED KEYS IN TABLE {database}.{schema}.{table_name}")
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        cur.close()
        if not rows:
            return []
        fk_name_idx = cols.index("fk_name")
        fk_col_idx = cols.index("fk_column_name")
        pk_table_idx = cols.index("pk_table_name")
        pk_col_idx = cols.index("pk_column_name")
        grouped: dict[str, dict[str, Any]] = {}
        for r in rows:
            g = grouped.setdefault(r[fk_name_idx], {"columns": [], "ref_table": r[pk_table_idx], "ref_columns": []})
            g["columns"].append(r[fk_col_idx])
            g["ref_columns"].append(r[pk_col_idx])
        return [ForeignKeyModel(name=n, columns=d["columns"], referenced_table=d["ref_table"], referenced_columns=d["ref_columns"]) for n, d in grouped.items()]

    def _extract_unique_constraints(self, database, schema, table_name) -> list[UniqueConstraintModel]:
        cur = self._conn.cursor()
        cur.execute(f"SHOW UNIQUE KEYS IN TABLE {database}.{schema}.{table_name}")
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        cur.close()
        if not rows:
            return []
        name_idx = cols.index("constraint_name")
        col_idx = cols.index("column_name")
        grouped: dict[str, list[str]] = {}
        for r in rows:
            grouped.setdefault(r[name_idx], []).append(r[col_idx])
        return [UniqueConstraintModel(name=n, columns=c) for n, c in grouped.items()]
