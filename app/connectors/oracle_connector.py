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
    import oracledb
    _HAS_ORACLEDB = True
except ImportError:  # pragma: no cover
    _HAS_ORACLEDB = False


class OracleConnector(DatabaseConnector):
    database_type = "oracle"

    def connect(self) -> None:
        if not _HAS_ORACLEDB:
            raise RuntimeError("oracledb is not installed. Install it to enable Oracle connectivity.")
        cfg = self.configuration
        dsn = oracledb.makedsn(cfg["host"], cfg.get("port", 1521), service_name=cfg["service_name"])
        # Uses the thin (driverless) mode by default - no Oracle Instant Client required.
        self._conn = oracledb.connect(user=cfg["username"], password=cfg.get("password"), dsn=dsn)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def test_connection(self) -> ConnectionTestResult:
        try:
            self.connect()
            cur = self._conn.cursor()
            cur.execute("SELECT 1 FROM DUAL")
            cur.close()
            return ConnectionTestResult(True, "Connection successful")
        except Exception as e:  # noqa: BLE001
            return ConnectionTestResult(False, f"Connection failed: {e}")
        finally:
            self.close()

    def get_databases(self) -> list[str]:
        # Oracle conflates "database" with the service/instance connected to.
        return [self.configuration.get("service_name", "ORCL")]

    def get_schemas(self, database: str | None = None) -> list[str]:
        cur = self._conn.cursor()
        cur.execute("SELECT username FROM all_users ORDER BY username")
        result = [r[0] for r in cur.fetchall()]
        cur.close()
        return result

    def get_tables(self, database: str | None, schema: str | None) -> list[str]:
        schema = (schema or self.configuration.get("schema") or self.configuration["username"]).upper()
        cur = self._conn.cursor()
        cur.execute("SELECT table_name FROM all_tables WHERE owner = :owner ORDER BY table_name", owner=schema)
        result = [r[0] for r in cur.fetchall()]
        cur.close()
        return result

    def extract_schema(
        self,
        database: str | None,
        schema: str | None,
        table_names: list[str] | None = None,
    ) -> CanonicalSchema:
        schema = (schema or self.configuration.get("schema") or self.configuration["username"]).upper()
        owns_connection = self._conn is None
        if owns_connection:
            self.connect()
        try:
            tables_to_extract = table_names if table_names is not None else self.get_tables(database, schema)
            tables = [self._extract_table(schema, t) for t in tables_to_extract]
            meta = SchemaMetadata(database_type=self.database_type, database=self.get_databases()[0], schema=schema)
            return CanonicalSchema(metadata=meta, tables=tables).sorted()
        finally:
            if owns_connection:
                self.close()

    def _extract_table(self, schema: str, table_name: str) -> TableModel:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT column_name, column_id, data_type, data_length, data_precision,
                   data_scale, nullable, data_default, identity_column
            FROM all_tab_columns
            WHERE owner = :owner AND table_name = :tname
            ORDER BY column_id
            """,
            owner=schema, tname=table_name,
        )
        columns = []
        for row in cur.fetchall():
            (cname, cid, dtype, dlen, dprec, dscale, nullable, ddefault, identity) = row
            columns.append(
                ColumnModel(
                    name=cname,
                    ordinal_position=cid,
                    native_datatype=dtype,
                    normalized_datatype=normalize_datatype(self.database_type, dtype),
                    length=dlen,
                    precision=dprec,
                    scale=dscale,
                    nullable=(nullable == "Y"),
                    default=str(ddefault).strip() if ddefault is not None else None,
                    is_identity=(identity == "YES"),
                )
            )
        pk = self._extract_primary_key(cur, schema, table_name)
        fks = self._extract_foreign_keys(cur, schema, table_name)
        uniques = self._extract_unique_constraints(cur, schema, table_name)
        indexes = self._extract_indexes(cur, schema, table_name)
        checks = self._extract_check_constraints(cur, schema, table_name)
        cur.close()
        return TableModel(
            name=table_name, columns=columns, primary_key=pk, foreign_keys=fks,
            unique_constraints=uniques, indexes=indexes, check_constraints=checks,
        )

    def _extract_primary_key(self, cur, schema, table_name) -> PrimaryKeyModel | None:
        cur.execute(
            """
            SELECT cons.constraint_name, cols.column_name, cols.position
            FROM all_constraints cons
            JOIN all_cons_columns cols ON cons.constraint_name = cols.constraint_name AND cons.owner = cols.owner
            WHERE cons.constraint_type = 'P' AND cons.owner = :owner AND cons.table_name = :tname
            ORDER BY cols.position
            """,
            owner=schema, tname=table_name,
        )
        rows = cur.fetchall()
        if not rows:
            return None
        return PrimaryKeyModel(name=rows[0][0], columns=[r[1] for r in rows])

    def _extract_foreign_keys(self, cur, schema, table_name) -> list[ForeignKeyModel]:
        cur.execute(
            """
            SELECT a.constraint_name, a.column_name, a.position,
                   c_pk.table_name AS ref_table, b.column_name AS ref_column
            FROM all_cons_columns a
            JOIN all_constraints c ON a.owner = c.owner AND a.constraint_name = c.constraint_name
            JOIN all_constraints c_pk ON c.r_owner = c_pk.owner AND c.r_constraint_name = c_pk.constraint_name
            JOIN all_cons_columns b ON b.owner = c_pk.owner AND b.constraint_name = c_pk.constraint_name AND b.position = a.position
            WHERE c.constraint_type = 'R' AND a.owner = :owner AND a.table_name = :tname
            ORDER BY a.constraint_name, a.position
            """,
            owner=schema, tname=table_name,
        )
        grouped: dict[str, dict[str, Any]] = {}
        for name, col, pos, ref_table, ref_col in cur.fetchall():
            g = grouped.setdefault(name, {"columns": [], "ref_table": ref_table, "ref_columns": []})
            g["columns"].append(col)
            g["ref_columns"].append(ref_col)
        return [ForeignKeyModel(name=n, columns=d["columns"], referenced_table=d["ref_table"], referenced_columns=d["ref_columns"]) for n, d in grouped.items()]

    def _extract_unique_constraints(self, cur, schema, table_name) -> list[UniqueConstraintModel]:
        cur.execute(
            """
            SELECT cons.constraint_name, cols.column_name, cols.position
            FROM all_constraints cons
            JOIN all_cons_columns cols ON cons.constraint_name = cols.constraint_name AND cons.owner = cols.owner
            WHERE cons.constraint_type = 'U' AND cons.owner = :owner AND cons.table_name = :tname
            ORDER BY cons.constraint_name, cols.position
            """,
            owner=schema, tname=table_name,
        )
        grouped: dict[str, list[str]] = {}
        for name, col, pos in cur.fetchall():
            grouped.setdefault(name, []).append(col)
        return [UniqueConstraintModel(name=n, columns=c) for n, c in grouped.items()]

    def _extract_indexes(self, cur, schema, table_name) -> list[IndexModel]:
        cur.execute(
            """
            SELECT i.index_name, i.uniqueness, c.column_name, c.column_position, i.index_type
            FROM all_indexes i
            JOIN all_ind_columns c ON i.index_name = c.index_name AND i.owner = c.index_owner
            WHERE i.table_owner = :owner AND i.table_name = :tname
            ORDER BY i.index_name, c.column_position
            """,
            owner=schema, tname=table_name,
        )
        grouped: dict[str, dict[str, Any]] = {}
        for name, uniqueness, col, pos, itype in cur.fetchall():
            g = grouped.setdefault(name, {"unique": uniqueness == "UNIQUE", "columns": [], "type": itype})
            g["columns"].append(col)
        return [IndexModel(name=n, columns=d["columns"], unique=d["unique"], index_type=d["type"]) for n, d in grouped.items()]

    def _extract_check_constraints(self, cur, schema, table_name) -> list[CheckConstraintModel]:
        cur.execute(
            """
            SELECT constraint_name, search_condition
            FROM all_constraints
            WHERE constraint_type = 'C' AND owner = :owner AND table_name = :tname
              AND generated = 'USER NAME'
            """,
            owner=schema, tname=table_name,
        )
        return [CheckConstraintModel(name=n, expression=str(cond) if cond is not None else None) for n, cond in cur.fetchall()]
