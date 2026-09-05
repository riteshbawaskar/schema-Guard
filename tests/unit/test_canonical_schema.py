import json

from app.schema.canonical import CanonicalSchema, ColumnModel, SchemaMetadata, TableModel


def _sample_schema(table_order=("B_TABLE", "A_TABLE"), col_order=("z_col", "a_col")):
    tables = []
    for tname in table_order:
        cols = [
            ColumnModel(name=c, ordinal_position=i + 1, native_datatype="VARCHAR", normalized_datatype="TEXT")
            for i, c in enumerate(col_order)
        ]
        tables.append(TableModel(name=tname, columns=cols))
    meta = SchemaMetadata(database_type="sqlite", database="test", schema="main", extracted_at="2026-01-01T00:00:00+00:00")
    return CanonicalSchema(metadata=meta, tables=tables)


def test_sorted_orders_tables_and_columns_deterministically():
    schema = _sample_schema()
    sorted_schema = schema.sorted()
    assert [t.name for t in sorted_schema.tables] == ["A_TABLE", "B_TABLE"]
    assert [c.name for c in sorted_schema.tables[0].columns] == ["a_col", "z_col"]


def test_to_canonical_json_is_deterministic_regardless_of_input_order():
    schema_a = _sample_schema(table_order=("B_TABLE", "A_TABLE"))
    schema_b = _sample_schema(table_order=("A_TABLE", "B_TABLE"))
    assert schema_a.to_canonical_json() == schema_b.to_canonical_json()


def test_to_canonical_json_never_contains_secret_looking_fields():
    schema = _sample_schema()
    data = json.loads(schema.to_canonical_json())
    serialized = json.dumps(data).lower()
    for forbidden in ("password", "pat", "secret"):
        assert forbidden not in serialized


def test_table_and_column_counts():
    schema = _sample_schema()
    assert schema.table_count() == 2
    assert schema.column_count() == 4


def test_round_trip_via_model_validate_json():
    schema = _sample_schema()
    raw = schema.to_canonical_json()
    restored = CanonicalSchema.model_validate_json(raw)
    assert restored.table_count() == schema.table_count()
    assert restored.metadata.database_type == "sqlite"
