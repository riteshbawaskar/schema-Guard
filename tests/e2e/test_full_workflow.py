"""End-to-end test replicating section 24/28 of the spec:

Create test DBs -> Create Database Configurations -> Test DB -> Create Filter
-> Extract Source -> Extract Destination -> Save Versions -> Compare
-> Validate expected differences -> Generate HTML -> Validate report
-> Simulate restart -> Versions/comparisons/reports still available.
"""
from __future__ import annotations

import os

from app.database import session_scope
from app.services import comparison_service, config_service, extraction_service, filter_service, report_service, schema_service


def test_full_workflow_end_to_end(tmp_app_env, test_databases):
    # 1. Create Database Configurations
    with session_scope() as db:
        src_cfg = config_service.create_configuration(
            db, "E2E SQLite Source", "sqlite", {"database_file": test_databases["source"]}
        )
        dst_cfg = config_service.create_configuration(
            db, "E2E SQLite Destination", "sqlite", {"database_file": test_databases["destination"]}
        )
        src_cfg_id, dst_cfg_id = src_cfg.id, dst_cfg.id

    # 2. Test configurations
    with session_scope() as db:
        src_result = config_service.test_configuration(db, src_cfg_id)
        dst_result = config_service.test_configuration(db, dst_cfg_id)
        assert src_result.success is True
        assert dst_result.success is True

    # 3. Create a reusable AX* filter
    with session_scope() as db:
        ax_filter = filter_service.create_filter(db, "AX Tables", "wildcard", ["AX*"], ["AX_TEMP*"])
        filter_id = ax_filter.id

    # --- simulate restart: fresh sessions, singletons already isolated by fixture ---

    # 4. Extract source & destination, save as versions
    with session_scope() as db:
        src_schema = extraction_service.extract_schema(db, src_cfg_id, None, None, filter_id, "AX Tables")
        src_version = schema_service.save_new_schema_version(
            db, "E2E Source AX", src_schema, database_configuration_id=src_cfg_id, filter_id=filter_id
        )
        dst_schema = extraction_service.extract_schema(db, dst_cfg_id, None, None, filter_id, "AX Tables")
        dst_version = schema_service.save_new_schema_version(
            db, "E2E Destination AX", dst_schema, database_configuration_id=dst_cfg_id, filter_id=filter_id
        )
        src_version_id, dst_version_id = src_version.id, dst_version.id

    # Source has AX_CUSTOMER, AX_ACCOUNT, AX_TRANSACTION (AX_TEMP_STAGING doesn't
    # exist in source at all); destination has AX_CUSTOMER, AX_ACCOUNT,
    # AX_BALANCE_SNAPSHOT after AX_TEMP_STAGING is excluded by the filter.
    assert src_schema.table_count() == 3
    assert dst_schema.table_count() == 3

    # 5. Compare source vs destination LIVE with the SAME filter applied independently
    with session_scope() as db:
        comparison_row, result, report_path = comparison_service.run_comparison(
            db, "live", src_cfg_id, "live", dst_cfg_id,
            source_filter_id=filter_id, destination_filter_id=filter_id,
        )
        comparison_id = comparison_row.id

    # 6. Validate expected differences (per scripts/create_test_databases.py)
    removed = {t.table_name for t in result.table_diffs if t.diff_type == "REMOVED"}
    added = {t.table_name for t in result.table_diffs if t.diff_type == "ADDED"}
    assert "AX_TRANSACTION" in removed
    assert "AX_BALANCE_SNAPSHOT" in added
    assert result.status == "FAIL"  # REMOVED table => CRITICAL => FAIL

    # 7. Generate + validate HTML report
    assert report_path is not None
    assert os.path.exists(report_path)
    with open(report_path, encoding="utf-8") as f:
        html = f.read()
    assert "AX_TRANSACTION" in html
    assert "AX_BALANCE_SNAPSHOT" in html
    assert "Schema Comparison Report" in html

    # 8. Simulate a full application restart and verify everything survived
    import app.database as database_module
    database_module._engine = None
    database_module._SessionLocal = None

    with session_scope() as db:
        reloaded_src_cfg = config_service.get_configuration_or_404(db, src_cfg_id)
        assert reloaded_src_cfg.name == "E2E SQLite Source"

        reloaded_filter = filter_service.get_filter_or_404(db, filter_id)
        assert reloaded_filter.name == "AX Tables"

        reloaded_src_version = schema_service.get_version_or_404(db, src_version_id)
        assert reloaded_src_version.table_count > 0

        reloaded_comparison = report_service.get_comparison_or_404(db, comparison_id)
        assert reloaded_comparison.status == "FAIL"
        assert reloaded_comparison.report_path == report_path

        reports = report_service.list_reports(db)
        assert any(r.comparison_id == comparison_id for r in reports)

    assert os.path.exists(report_path)  # report file itself survived "restart"


def test_full_workflow_without_filter_matches_direct_engine_comparison(tmp_app_env, test_databases):
    """Sanity cross-check: unfiltered live-to-live comparison produces the
    same summary counts as comparing the two raw extracted schemas directly."""
    from app.comparison.engine import compare_schemas
    from app.connectors.sqlite_connector import SQLiteConnector

    with session_scope() as db:
        src_cfg = config_service.create_configuration(db, "Direct Src", "sqlite", {"database_file": test_databases["source"]})
        dst_cfg = config_service.create_configuration(db, "Direct Dst", "sqlite", {"database_file": test_databases["destination"]})
        _, result, _ = comparison_service.run_comparison(db, "live", src_cfg.id, "live", dst_cfg.id)

    src_connector = SQLiteConnector({"database_file": test_databases["source"]})
    with src_connector:
        src_schema = src_connector.extract_schema(None, None)
    dst_connector = SQLiteConnector({"database_file": test_databases["destination"]})
    with dst_connector:
        dst_schema = dst_connector.extract_schema(None, None)
    direct_result = compare_schemas(src_schema, dst_schema)

    assert result.summary.tables_compared == direct_result.summary.tables_compared
    assert result.summary.difference_count == direct_result.summary.difference_count
    assert result.status == direct_result.status
