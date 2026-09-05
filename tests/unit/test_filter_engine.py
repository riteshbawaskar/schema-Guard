from app.filters.engine import FilterDefinition, apply_filter, matches


def test_starts_with():
    f = FilterDefinition("f", "starts_with", ["AX"], [])
    assert matches("AX_CUSTOMER", f)
    assert not matches("CUSTOMER_AX", f)


def test_ends_with():
    f = FilterDefinition("f", "ends_with", ["_HIST"], [])
    assert matches("CUSTOMER_HIST", f)
    assert not matches("HIST_CUSTOMER", f)


def test_contains():
    f = FilterDefinition("f", "contains", ["CUST"], [])
    assert matches("AX_CUSTOMER", f)
    assert not matches("AX_ACCOUNT", f)


def test_exact():
    f = FilterDefinition("f", "exact", ["CUSTOMER"], [])
    assert matches("CUSTOMER", f)
    assert not matches("CUSTOMERS", f)


def test_wildcard():
    f = FilterDefinition("f", "wildcard", ["AX*"], [])
    assert matches("AX_CUSTOMER", f)
    assert not matches("BX_CUSTOMER", f)


def test_regex():
    f = FilterDefinition("f", "regex", [r"^AX_[A-Z]+$"], [])
    assert matches("AX_CUSTOMER", f)
    assert not matches("AX_CUSTOMER_1", f)


def test_case_insensitivity_for_non_regex_modes():
    f = FilterDefinition("f", "starts_with", ["ax"], [])
    assert matches("AX_CUSTOMER", f)


def test_include_and_exclude_combination():
    f = FilterDefinition("f", "wildcard", ["AX*"], ["AX_TEMP*", "AX_BACKUP*"])
    assert matches("AX_CUSTOMER", f)
    assert not matches("AX_TEMP_STAGING", f)
    assert not matches("AX_BACKUP_2024", f)


def test_empty_include_matches_everything_except_excludes():
    f = FilterDefinition("f", "contains", [], ["TEMP"])
    assert matches("CUSTOMER", f)
    assert not matches("CUSTOMER_TEMP", f)


def test_apply_filter_returns_matching_subset():
    f = FilterDefinition("f", "wildcard", ["AX*"], ["AX_TEMP*"])
    names = ["AX_CUSTOMER", "AX_ACCOUNT", "CUSTOMER", "AX_TEMP_STAGING"]
    assert apply_filter(names, f) == ["AX_CUSTOMER", "AX_ACCOUNT"]


def test_apply_filter_none_is_passthrough():
    names = ["A", "B", "C"]
    assert apply_filter(names, None) == names


def test_independent_filter_evaluation_does_not_hide_differences():
    """Per spec section 9: applying the SAME filter independently to source
    and destination table lists must surface (not hide) a table that only
    exists on one side."""
    f = FilterDefinition("f", "wildcard", ["AX*"], [])
    source_tables = ["AX_CUSTOMER", "AX_ACCOUNT", "AX_TRANSACTION"]
    destination_tables = ["AX_CUSTOMER", "AX_ACCOUNT"]
    src_matched = set(apply_filter(source_tables, f))
    dst_matched = set(apply_filter(destination_tables, f))
    assert src_matched - dst_matched == {"AX_TRANSACTION"}
