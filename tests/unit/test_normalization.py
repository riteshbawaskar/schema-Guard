from app.schema.normalization import normalize_datatype


def test_strict_mode_returns_bare_native_type():
    assert normalize_datatype("snowflake", "NUMBER(38,0)", mode="strict") == "NUMBER"
    assert normalize_datatype("postgresql", "numeric(10,2)", mode="strict") == "NUMERIC"


def test_strict_mode_never_equates_different_native_types():
    a = normalize_datatype("snowflake", "NUMBER", mode="strict")
    b = normalize_datatype("postgresql", "NUMERIC", mode="strict")
    assert a != b


def test_compatible_mode_maps_numeric_family_across_databases():
    a = normalize_datatype("snowflake", "NUMBER(38,0)", mode="compatible")
    b = normalize_datatype("oracle", "NUMBER", mode="compatible")
    c = normalize_datatype("postgresql", "NUMERIC(10,2)", mode="compatible")
    assert a == b == c == "NUMERIC"


def test_compatible_mode_maps_text_family():
    a = normalize_datatype("snowflake", "VARCHAR(255)", mode="compatible")
    b = normalize_datatype("postgresql", "character varying", mode="compatible")
    assert a == b == "TEXT"


def test_compatible_mode_does_not_equate_unrelated_types():
    a = normalize_datatype("postgresql", "NUMERIC", mode="compatible")
    b = normalize_datatype("postgresql", "TEXT", mode="compatible")
    assert a != b


def test_compatible_mode_falls_back_to_bare_type_when_unmapped():
    result = normalize_datatype("oracle", "XMLTYPE", mode="compatible")
    assert result == "XMLTYPE"
