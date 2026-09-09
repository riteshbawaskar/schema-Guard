from app.schema.axiom_xml import parse_axiom_xml, parse_axiom_xml_file
from app.schema.normalization import normalize_datatype
from app.comparison.engine import compare_schemas
from app.reports.html_report import render_html_report


def test_axiom_xml_extracts_datasource_fields(tmp_path):
    xml = b'''<?xml version="1.0"?>
    <object type="DataSource">
      <property name="name" value="Guarantees" />
      <property name="layout" valueType="table">
        <object type="DataSource:field">
          <property name="name" value="asof_date" />
          <property name="type" value="DATETIME" />
          <property name="allowNulls" value="false" />
          <property name="description" value="Instance Date" />
        </object>
        <object type="DataSource:field">
          <property name="name" value="customer_name" />
          <property name="type" value="STRING" />
        </object>
        <object type="Other" />
      </property>
    </object>'''

    schema = parse_axiom_xml(xml)
    assert schema.tables[0].name == "Guarantees"
    assert [column.name for column in schema.tables[0].columns] == ["asof_date", "customer_name"]
    assert schema.tables[0].columns[0].native_datatype == "DATETIME"
    assert schema.tables[0].columns[0].normalized_datatype == "TEMPORAL"
    assert "parentFields" not in schema.tables[0].columns[0].source_properties
    assert "description" in schema.tables[0].columns[0].source_properties
    assert schema.tables[0].columns[1].normalized_datatype == "TEXT"
    assert schema.tables[0].columns[0].nullable is False

    path = tmp_path / "schema.xml"
    path.write_bytes(xml)
    assert parse_axiom_xml_file(path).column_count() == 2


def test_axiom_temporal_and_text_types_are_compatible():
    assert normalize_datatype("axiom", "DATE") == normalize_datatype("sqlite", "DATETIME")
    assert normalize_datatype("axiom", "STRING") == normalize_datatype("postgresql", "VARCHAR")


def test_report_uses_xml_fields_only_for_xml_to_xml(tmp_path):
    xml = b'''<object type="DataSource">
      <property name="name" value="Source" />
      <property name="layout" valueType="table">
        <object type="DataSource:field">
          <property name="name" value="event_date" />
          <property name="type" value="DATE" />
          <property name="description" value="Event date" />
        </object>
      </property>
    </object>'''
    first = parse_axiom_xml(xml)
    second = parse_axiom_xml(xml.replace(b"Event date", b"Changed"))
    xml_result = compare_schemas(first, second)
    xml_report = render_html_report(xml_result, "xml-xml")
    assert "const XML_XML_MODE = true" in xml_report
    assert '"description"' in xml_report
    assert '"type"' in xml_report

    database = first.model_copy(deep=True)
    database.metadata.database_type = "sqlite"
    database.tables[0].columns[0].source_properties = {}
    db_result = compare_schemas(first, database)
    db_report = render_html_report(db_result, "xml-db")
    assert "const XML_XML_MODE = false" in db_report
    assert '"description"' in db_report
    assert "datatype" in db_report
