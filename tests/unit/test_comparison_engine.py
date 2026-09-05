from app.comparison.engine import compare_schemas
from app.schema.canonical import CanonicalSchema, ColumnModel, PrimaryKeyModel, SchemaMetadata, TableModel


def _schema(tables):
    return CanonicalSchema(metadata=SchemaMetadata(database_type="sqlite", database="t", schema="main"), tables=tables)


def _col(name, dtype="TEXT", **kwargs):
    defaults = dict(ordinal_position=1, native_datatype=dtype, normalized_datatype=dtype)
    defaults.update(kwargs)
    return ColumnModel(name=name, **defaults)


def test_identical_schemas_produce_pass_with_no_differences():
    t = TableModel(name="CUSTOMER", columns=[_col("id"), _col("name")])
    result = compare_schemas(_schema([t]), _schema([t.model_copy(deep=True)]))
    assert result.status == "PASS"
    assert result.summary.difference_count == 0
    assert result.summary.tables_unchanged == 1


def test_added_table_detected():
    src = _schema([])
    dst = _schema([TableModel(name="NEW_TABLE", columns=[_col("id")])])
    result = compare_schemas(src, dst)
    added = [t for t in result.table_diffs if t.diff_type == "ADDED"]
    assert len(added) == 1
    assert added[0].table_name == "NEW_TABLE"
    assert result.summary.tables_added == 1


def test_removed_table_detected_and_marked_critical():
    src = _schema([TableModel(name="OLD_TABLE", columns=[_col("id")])])
    dst = _schema([])
    result = compare_schemas(src, dst)
    removed = [t for t in result.table_diffs if t.diff_type == "REMOVED"]
    assert len(removed) == 1
    assert removed[0].severity == "CRITICAL"
    assert result.status == "FAIL"


def test_column_added_and_removed():
    src = TableModel(name="T", columns=[_col("a"), _col("b")])
    dst = TableModel(name="T", columns=[_col("a"), _col("c")])
    result = compare_schemas(_schema([src]), _schema([dst]))
    td = result.table_diffs[0]
    diff_types = {(d.name, d.diff_type) for d in td.column_diffs}
    assert ("b", "REMOVED") in diff_types
    assert ("c", "ADDED") in diff_types


def test_datatype_change_is_critical():
    src = TableModel(name="T", columns=[_col("amount", dtype="NUMERIC")])
    dst = TableModel(name="T", columns=[_col("amount", dtype="TEXT")])
    result = compare_schemas(_schema([src]), _schema([dst]))
    col_diff = result.table_diffs[0].column_diffs[0]
    assert col_diff.diff_type == "MODIFIED"
    assert any(fd.category == "datatype" for fd in col_diff.field_diffs)
    assert col_diff.severity == "CRITICAL"


def test_nullable_change_is_high_severity():
    src = TableModel(name="T", columns=[_col("x", nullable=True)])
    dst = TableModel(name="T", columns=[_col("x", nullable=False)])
    result = compare_schemas(_schema([src]), _schema([dst]))
    col_diff = result.table_diffs[0].column_diffs[0]
    nullable_fd = next(fd for fd in col_diff.field_diffs if fd.category == "nullable")
    assert nullable_fd.severity == "HIGH"


def test_primary_key_removed_is_critical():
    src = TableModel(name="T", columns=[_col("id")], primary_key=PrimaryKeyModel(name="pk_t", columns=["id"]))
    dst = TableModel(name="T", columns=[_col("id")], primary_key=None)
    result = compare_schemas(_schema([src]), _schema([dst]))
    assert result.table_diffs[0].primary_key_diff.diff_type == "REMOVED"
    assert result.table_diffs[0].primary_key_diff.severity == "CRITICAL"


def test_composite_primary_key_change_detected():
    src = TableModel(name="T", columns=[_col("a"), _col("b")], primary_key=PrimaryKeyModel(name="pk", columns=["a"]))
    dst = TableModel(name="T", columns=[_col("a"), _col("b")], primary_key=PrimaryKeyModel(name="pk", columns=["a", "b"]))
    result = compare_schemas(_schema([src]), _schema([dst]))
    assert result.table_diffs[0].primary_key_diff.diff_type == "MODIFIED"


def test_fail_on_respects_configured_severities():
    src = TableModel(name="T", columns=[_col("x", ordinal_position=1)])
    dst = TableModel(name="T", columns=[_col("x", ordinal_position=2)])  # LOW severity only
    result = compare_schemas(_schema([src]), _schema([dst]), fail_on=["CRITICAL", "HIGH"])
    assert result.status == "PASS"  # only a LOW-severity position diff
    result_strict = compare_schemas(_schema([src]), _schema([dst]), fail_on=["LOW"])
    assert result_strict.status == "FAIL"


def test_unchanged_column_produces_no_field_diffs():
    col = _col("a")
    src = TableModel(name="T", columns=[col])
    dst = TableModel(name="T", columns=[col.model_copy(deep=True)])
    result = compare_schemas(_schema([src]), _schema([dst]))
    assert result.table_diffs[0].column_diffs[0].diff_type == "UNCHANGED"
