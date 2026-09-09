from app.comparison.engine import compare_schemas
from app.schema.axiom_xml import parse_axiom_xml
from app.services import xml_mapping_service


_XML = b'''<object type="DataSource">
  <property name="name" value="Source" />
  <property name="layout" valueType="table">
    <object type="DataSource:field">
      <property name="name" value="amount" />
      <property name="type" value="STRING" />
      <property name="description" value="Amount" />
    </object>
  </property>
</object>'''


def test_missing_xml_attribute_is_warning_and_does_not_fail(tmp_path, monkeypatch):
    policy = tmp_path / "mapping.yaml"
    policy.write_text("""xml:
  attribute_mappings:
    - {source: name, target: name, enabled: true, compare: true}
    - {source: type, target: datatype, enabled: true, compare: true}
    - {source: description, target: comment, enabled: true, compare: true}
  ignored_attributes: []
  missing_attribute: {severity: WARNING, fail: false}
""", encoding="utf-8")
    monkeypatch.setattr(xml_mapping_service, "MAPPING_PATH", policy)
    source = parse_axiom_xml(_XML)
    destination = parse_axiom_xml(_XML.replace(b' name="description" value="Amount"', b''))
    result = compare_schemas(source, destination)
    diffs = result.table_diffs[0].column_diffs[0].field_diffs
    assert any(diff.field == "description" and diff.severity == "WARNING" for diff in diffs)
    assert result.status == "PASS"
    assert result.summary.warning_count == 1


def test_disabled_mapping_is_not_compared(tmp_path, monkeypatch):
    policy = tmp_path / "mapping.yaml"
    policy.write_text("""xml:
  attribute_mappings:
    - {source: name, target: name, enabled: true, compare: true}
    - {source: type, target: datatype, enabled: true, compare: true}
    - {source: description, target: comment, enabled: false, compare: true}
""", encoding="utf-8")
    monkeypatch.setattr(xml_mapping_service, "MAPPING_PATH", policy)
    source = parse_axiom_xml(_XML)
    destination = parse_axiom_xml(_XML.replace(b' value="Amount"', b' value="Changed"'))
    assert destination.tables[0].columns[0].source_properties == {"name": "amount", "type": "STRING"}
    result = compare_schemas(source, destination)
    assert result.summary.difference_count == 0
