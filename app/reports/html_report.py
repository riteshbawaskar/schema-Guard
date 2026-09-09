from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.comparison.models import ComparisonResult

_TEMPLATE_DIR = Path(__file__).parent
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)


def render_html_report(result: ComparisonResult, comparison_id: str) -> str:
    template = _env.get_template("report_template.html")
    result_dict = result.model_dump(mode="json", exclude_none=True)
    # Content inside a <script> element is HTML "raw text": the browser does
    # NOT decode HTML entities there, so Jinja's normal autoescaping (which
    # turns '"' into '&#34;' etc.) would corrupt embedded JSON. We build safe
    # JSON ourselves (escaping any '</' sequence so a value can never
    # prematurely close the <script> tag) and mark it `|safe` in the template.
    tables_json = _script_safe_json(result_dict["table_diffs"])
    result_json_urlencoded = urllib.parse.quote(json.dumps(result_dict, indent=2))
    return template.render(
        result=result,
        comparison_id=comparison_id,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        tables_json=tables_json,
        result_json_urlencoded=result_json_urlencoded,
    )


def _script_safe_json(data) -> str:
    raw = json.dumps(data)
    return raw.replace("</", "<\\/")
