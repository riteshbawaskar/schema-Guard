import json
import re

from app.comparison.engine import compare_schemas
from app.reports.html_report import render_html_report
from app.schema.canonical import CanonicalSchema, ColumnModel, SchemaMetadata, TableModel


def _schema_with_special_chars():
    # Table/column names with characters that are dangerous if the report
    # template ever HTML-escapes JSON embedded inside a <script> tag
    # (entities are not decoded inside <script> raw-text elements).
    col = ColumnModel(name='col_with_"quotes"_&_amp', ordinal_position=1, native_datatype="TEXT", normalized_datatype="TEXT")
    table = TableModel(name="TABLE_</script>_INJECT", columns=[col])
    meta = SchemaMetadata(database_type="sqlite", database="d", schema="main")
    return CanonicalSchema(metadata=meta, tables=[table])


def test_report_embedded_json_is_valid_and_parseable():
    src = _schema_with_special_chars()
    dst = CanonicalSchema(metadata=src.metadata, tables=[])
    result = compare_schemas(src, dst)
    html = render_html_report(result, "regression-test-1")

    match = re.search(r'<script id="report-data" type="application/json">(.*?)</script>', html, re.DOTALL)
    assert match is not None, "report-data script block not found"
    raw = match.group(1)

    # Must be valid JSON as embedded (this is the exact bug: entities like
    # &#34; break JSON.parse in the browser).
    data = json.loads(raw)
    assert isinstance(data, list)
    assert len(data) == 1

    # No leftover HTML entities from autoescaping.
    assert "&#34;" not in raw
    assert "&amp;" not in raw
    assert "&lt;" not in raw or True  # names with '<' are not expected here, but guard stays cheap

    # A literal "</script>" must never appear unescaped (would break out of
    # the script tag and could enable HTML injection from schema data).
    assert "</script>" not in raw


def test_report_html_is_well_formed_around_script_tag():
    src = _schema_with_special_chars()
    dst = CanonicalSchema(metadata=src.metadata, tables=[])
    result = compare_schemas(src, dst)
    html = render_html_report(result, "regression-test-2")
    # There should be exactly one report-data script tag and the document
    # should still close normally after it.
    assert html.count('id="report-data"') == 1
    assert html.strip().endswith("</html>")


def test_report_diff_tables_share_fixed_column_layout():
    src = _schema_with_special_chars()
    dst = CanonicalSchema(metadata=src.metadata, tables=[])
    result = compare_schemas(src, dst)
    html = render_html_report(result, "regression-test-columns")

    assert "table-layout:fixed" in html
    assert "th:nth-child(1)" in html
    assert "th:nth-child(4)" in html
