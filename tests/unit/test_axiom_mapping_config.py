from app.schema.axiom_xml import parse_axiom_xml


def test_axiom_mapping_is_loaded_per_parse(tmp_path):
    mapping = tmp_path / "mapping.yaml"
    mapping.write_text(
        """xml:
  object_type: CustomSource
  field_object_type: CustomSource:field
  field_properties:
    name: columnName
    datatype: dataType
    nullable: nullableFlag
    comment: notes
    default: defaultValue
  ignored_properties: [internal]
  datatype_map:
    TEXTUAL: VARCHAR2
""",
        encoding="utf-8",
    )
    xml = b'''<object type="CustomSource">
      <property name="name" value="Configured Source" />
      <property name="layout" valueType="table">
        <object type="CustomSource:field">
          <property name="columnName" value="customer_name" />
          <property name="dataType" value="TEXTUAL" />
          <property name="nullableFlag" value="false" />
          <property name="notes" value="Customer" />
          <property name="defaultValue" value="N/A" />
          <property name="internal" value="hidden" />
        </object>
      </property>
    </object>'''

    schema = parse_axiom_xml(xml, mapping_path=mapping)
    column = schema.tables[0].columns[0]
    assert column.name == "customer_name"
    assert column.native_datatype == "VARCHAR2"
    assert column.nullable is False
    assert column.comment == "Customer"
    assert column.default == "N/A"
    assert "internal" not in column.source_properties
