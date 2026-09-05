from app.connectors.sqlite_connector import SQLiteConnector


def test_sqlite_extraction_returns_expected_table_names(test_databases):
    connector = SQLiteConnector({"database_file": test_databases["source"]})
    with connector:
        tables = connector.get_tables(None, None)
    assert "CUSTOMER" in tables
    assert "AX_CUSTOMER" in tables
    assert "AX_TRANSACTION" in tables


def test_sqlite_extraction_produces_canonical_schema_with_pk_and_fk(test_databases):
    connector = SQLiteConnector({"database_file": test_databases["source"]})
    with connector:
        schema = connector.extract_schema(None, None)
    customer = next(t for t in schema.tables if t.name == "CUSTOMER")
    assert customer.primary_key is not None
    assert "customer_id" in customer.primary_key.columns

    account = next(t for t in schema.tables if t.name == "ACCOUNT")
    assert any(fk.referenced_table == "CUSTOMER" for fk in account.foreign_keys)


def test_sqlite_extraction_respects_table_filter(test_databases):
    connector = SQLiteConnector({"database_file": test_databases["source"]})
    with connector:
        all_tables = connector.get_tables(None, None)
        schema = connector.extract_schema(None, None, table_names=["CUSTOMER", "ACCOUNT"])
    assert len(schema.tables) == 2
    assert {t.name for t in schema.tables} == {"CUSTOMER", "ACCOUNT"}
    assert len(all_tables) > 2


def test_sqlite_extraction_captures_check_constraint(test_databases):
    connector = SQLiteConnector({"database_file": test_databases["source"]})
    with connector:
        schema = connector.extract_schema(None, None)
    customer = next(t for t in schema.tables if t.name == "CUSTOMER")
    assert len(customer.check_constraints) >= 1


def test_sqlite_extraction_captures_indexes(test_databases):
    connector = SQLiteConnector({"database_file": test_databases["source"]})
    with connector:
        schema = connector.extract_schema(None, None)
    customer = next(t for t in schema.tables if t.name == "CUSTOMER")
    index_names = {i.name for i in customer.indexes}
    assert "idx_customer_status" in index_names


def test_connection_test_reports_success_for_valid_sqlite_file(test_databases):
    connector = SQLiteConnector({"database_file": test_databases["source"]})
    result = connector.test_connection()
    assert result.success is True


def test_connection_test_reports_failure_for_missing_file(tmp_path):
    connector = SQLiteConnector({"database_file": str(tmp_path / "does_not_exist.db")})
    result = connector.test_connection()
    assert result.success is False
