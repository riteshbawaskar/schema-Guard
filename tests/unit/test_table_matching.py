from app.comparison.engine import compare_schemas
from app.schema.canonical import CanonicalSchema, SchemaMetadata, TableModel
from app.services import xml_mapping_service


def _schema(*names):
    return CanonicalSchema(
        metadata=SchemaMetadata(database_type="sqlite"),
        tables=[TableModel(name=name) for name in names],
    )


def test_table_mapping_matches_different_names(tmp_path, monkeypatch):
    path = tmp_path / "mapping.yaml"
    path.write_text("""table_matching:
  enabled: true
  ignore_names: false
  mappings:
    - {source: XML_TABLE, destination: DB_TABLE, enabled: true}
""", encoding="utf-8")
    monkeypatch.setattr(xml_mapping_service, "MAPPING_PATH", path)

    result = compare_schemas(_schema("XML_TABLE"), _schema("DB_TABLE"))

    assert result.table_diffs[0].table_name == "XML_TABLE"
    assert result.table_diffs[0].diff_type == "UNCHANGED"


def test_ignore_table_names_pairs_remaining_tables(tmp_path, monkeypatch):
    path = tmp_path / "mapping.yaml"
    path.write_text("""table_matching:
  enabled: true
  ignore_names: true
  mappings: []
""", encoding="utf-8")
    monkeypatch.setattr(xml_mapping_service, "MAPPING_PATH", path)

    result = compare_schemas(_schema("XML_TABLE"), _schema("DB_TABLE"))

    assert len(result.table_diffs) == 1
    assert result.table_diffs[0].diff_type == "UNCHANGED"
    assert result.table_diffs[0].table_name == "XML_TABLE"
