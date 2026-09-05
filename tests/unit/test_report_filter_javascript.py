"""Runs the report's client-side filtering logic (severity/type pills,
diff-only toggle, search) headlessly via Node.js against a real generated
report, to catch regressions in report_template.html's JavaScript that pure
Python tests of the backend can never see.

Skips cleanly if Node.js isn't available in the environment.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import textwrap

import pytest

from app.comparison.engine import compare_schemas
from app.reports.html_report import render_html_report

NODE = shutil.which("node")


def _generate_report(test_databases) -> str:
    from app.connectors.sqlite_connector import SQLiteConnector

    src = SQLiteConnector({"database_file": test_databases["source"]})
    with src:
        s = src.extract_schema(None, None)
    dst = SQLiteConnector({"database_file": test_databases["destination"]})
    with dst:
        d = dst.extract_schema(None, None)
    result = compare_schemas(s, d)
    return render_html_report(result, "node-regression-test")


def _extract_table_data_and_logic(html: str) -> tuple[str, str]:
    data_match = re.search(
        r'<script id="report-data" type="application/json">(.*?)</script>', html, re.DOTALL
    )
    assert data_match is not None
    table_data = data_match.group(1)

    logic_match = re.search(r"<script>\s*const ALL_TABLES.*?</script>", html, re.DOTALL)
    assert logic_match is not None
    logic = re.sub(r"^<script>", "", logic_match.group(0))
    logic = re.sub(r"</script>$", "", logic)
    # Strip DOM event wiring so the harness can drive functions manually.
    logic = re.sub(r"document\.getElementById\('search'\)\.addEventListener[\s\S]*$", "", logic)
    return table_data, logic


_NODE_HARNESS_TEMPLATE = """
const tableDataRaw = %(table_data)s;

class FakeElement {
  constructor() { this.textContent = ''; this.innerHTML = ''; this.style = {};
    this.classList = { add(){}, remove(){}, toggle(){}, contains(){return false;} }; }
  addEventListener() {}
}
global.document = {
  getElementById(id) {
    if (id === 'report-data') { const el = new FakeElement(); el.textContent = tableDataRaw; return el; }
    return new FakeElement();
  },
  querySelectorAll() { return []; },
};

require('vm').runInThisContext(%(logic)s);

const output = {};
output.default_count = getFiltered().length;

activeSevs = new Set(['CRITICAL']);
const criticalOnly = getFiltered();
output.critical_only_count = criticalOnly.length;
output.critical_only_has_leak = criticalOnly.some(t => {
  const v = visibleChildren(t);
  for (const key of CHILD_COLLECTIONS) { if (v[key].some(d => d.severity !== 'CRITICAL')) return true; }
  if (v.primary_key_diff && v.primary_key_diff.severity !== 'CRITICAL') return true;
  if ((t.diff_type === 'ADDED' || t.diff_type === 'REMOVED') && t.severity !== 'CRITICAL') return true;
  return false;
});

activeSevs = new Set([]);
output.no_severity_count = getFiltered().length;

activeSevs = new Set(['CRITICAL','HIGH','MEDIUM','LOW','INFO']);
activeTypes = new Set(['ADDED','REMOVED','MODIFIED']);
output.restored_count = getFiltered().length;

console.log(JSON.stringify(output));
"""


@pytest.mark.skipif(NODE is None, reason="Node.js not available in this environment")
def test_report_severity_filters_actually_filter_rows(test_databases):
    html = _generate_report(test_databases)
    table_data, logic = _extract_table_data_and_logic(html)

    harness = _NODE_HARNESS_TEMPLATE % {
        "table_data": json.dumps(table_data),
        "logic": json.dumps(logic),
    }
    proc = subprocess.run([NODE, "-e", harness], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, f"Node harness failed: {proc.stderr}"
    output = json.loads(proc.stdout.strip().splitlines()[-1])

    assert output["default_count"] > 0
    # Restricting to CRITICAL must shrink (or at least not grow) the visible set.
    assert output["critical_only_count"] <= output["default_count"]
    assert output["critical_only_count"] > 0  # this fixture has CRITICAL diffs
    # No row of a severity other than CRITICAL may be shown when only CRITICAL is active.
    assert output["critical_only_has_leak"] is False
    # Disabling every severity must hide everything.
    assert output["no_severity_count"] == 0
    # Restoring all severities/types returns to the original default view.
    assert output["restored_count"] == output["default_count"]
