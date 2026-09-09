from app.comparison.engine import compare_schemas
from app.reports.html_report import render_html_report
from app.schema.axiom_xml import parse_axiom_xml
from app.services import xml_mapping_service


def test_compare_false_hides_xml_attribute_from_diff_and_report(tmp_path, monkeypatch):
    policy = tmp_path / "mapping.yaml"
    policy.write_text("""attribute_mappings:
  - {source: name, target: name, enabled: true, compare: true}
  - {source: type, target: datatype, enabled: true, compare: true}
  - {source: allowNulls, target: nullable, enabled: true, compare: false}
xml:
  validate_object_types: [DataSource:field]
""", encoding="utf-8")
    monkeypatch.setattr(xml_mapping_service, "MAPPING_PATH", policy)
    xml = b'''<object type="DataSource"><property name="name" value="Source"/><property name="layout" valueType="table"><object type="DataSource:field"><property name="name" value="amount"/><property name="type" value="TEXT"/><property name="allowNulls" value="false"/></object></property></object>'''
    changed = xml.replace(b'value="false"', b'value="true"')
    result = compare_schemas(parse_axiom_xml(xml), parse_axiom_xml(changed))
    assert not any(diff.field == "allowNulls" for diff in result.table_diffs[0].column_diffs[0].field_diffs)
    report = render_html_report(result, "compare-flag")
    assert '"allowNulls"' not in report


def test_xml_report_attributes_are_not_prefixed():
    xml = b'''<object type="DataSource"><property name="name" value="Source"/><property name="layout" valueType="table"><object type="DataSource:field"><property name="name" value="amount"/><property name="type" value="TEXT"/></object></property></object>'''
    result = compare_schemas(parse_axiom_xml(xml), parse_axiom_xml(xml))
    report = render_html_report(result, "xml-label")
    assert '"type"' in report
    assert 'XML: type' not in report
