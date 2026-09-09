from app.comparison.engine import compare_schemas
from app.schema.axiom_xml import parse_axiom_xml


_XML = b'''<object type="DataSource">
  <property name="name" value="Mizuho_Guarantee_Monthly" />
  <property name="layout" valueType="table">
    <object type="DataSource:field">
      <property name="name" value="asof_date" />
      <property name="type" value="DATE" />
    </object>
  </property>
</object>'''


def test_xml_comparison_result_uses_filename_metadata():
    source = parse_axiom_xml(_XML)
    destination = parse_axiom_xml(_XML)
    source.metadata.database_configuration = "guarantee_monthly.xml"
    destination.metadata.database_configuration = "other_monthly.xml"

    result = compare_schemas(source, destination)

    assert result.source_label == "guarantee_monthly.xml"
    assert result.destination_label == "other_monthly.xml"
