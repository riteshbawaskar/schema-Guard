from app.database import session_scope
from app.services import comparison_service, config_service, filter_service, report_service


def _setup_configs(db, test_databases):
    src = config_service.create_configuration(db, "Src", "sqlite", {"database_file": test_databases["source"]})
    dst = config_service.create_configuration(db, "Dst", "sqlite", {"database_file": test_databases["destination"]})
    return src.id, dst.id


def test_live_to_live_comparison_persists_and_generates_report(tmp_app_env, test_databases):
    with session_scope() as db:
        src_id, dst_id = _setup_configs(db, test_databases)
        comparison_row, result, report_path = comparison_service.run_comparison(
            db, "live", src_id, "live", dst_id
        )
        assert comparison_row.status in ("PASS", "FAIL")
        assert result.summary.tables_compared > 0
        assert comparison_row.report_path is not None

    import os
    assert os.path.exists(report_path)
    with open(report_path) as f:
        html = f.read()
    assert "<!DOCTYPE html>" in html
    assert "Schema Comparison Report" in html


def test_filter_applied_independently_shows_removed_table(tmp_app_env, test_databases):
    with session_scope() as db:
        src_id, dst_id = _setup_configs(db, test_databases)
        f = filter_service.create_filter(db, "AX Tables", "wildcard", ["AX*"], ["AX_TEMP*"])
        comparison_row, result, _ = comparison_service.run_comparison(
            db, "live", src_id, "live", dst_id,
            source_filter_id=f.id, destination_filter_id=f.id,
        )
        removed = [t.table_name for t in result.table_diffs if t.diff_type == "REMOVED"]
        added = [t.table_name for t in result.table_diffs if t.diff_type == "ADDED"]
        assert "AX_TRANSACTION" in removed
        assert "AX_BALANCE_SNAPSHOT" in added
        # AX_TEMP_STAGING must be excluded from consideration entirely.
        assert all(t.table_name != "AX_TEMP_STAGING" for t in result.table_diffs)


def test_comparison_persists_across_sessions(tmp_app_env, test_databases):
    with session_scope() as db:
        src_id, dst_id = _setup_configs(db, test_databases)
        comparison_row, _, _ = comparison_service.run_comparison(db, "live", src_id, "live", dst_id)
        comparison_id = comparison_row.id

    from app.services import report_service
    with session_scope() as db:
        reloaded = report_service.get_comparison_or_404(db, comparison_id)
        assert reloaded.id == comparison_id
        assert reloaded.table_count > 0


def test_schema_version_to_schema_version_comparison(tmp_app_env, test_databases):
    from app.connectors.sqlite_connector import SQLiteConnector
    from app.services import schema_service

    with session_scope() as db:
        src_connector = SQLiteConnector({"database_file": test_databases["source"]})
        with src_connector:
            src_schema = src_connector.extract_schema(None, None)
        dst_connector = SQLiteConnector({"database_file": test_databases["destination"]})
        with dst_connector:
            dst_schema = dst_connector.extract_schema(None, None)

        v1 = schema_service.save_new_schema_version(db, "V1", src_schema)
        v2 = schema_service.save_new_schema_version(db, "V2", dst_schema)

        comparison_row, result, _ = comparison_service.run_comparison(
            db, "schema_version", v1.id, "schema_version", v2.id
        )
        assert result.summary.tables_compared == src_schema.table_count() or result.summary.tables_compared >= 1
        assert comparison_row.status in ("PASS", "FAIL")


def test_comparison_labels_are_persisted_and_human_readable(tmp_app_env, test_databases):
    with session_scope() as db:
        src_id, dst_id = _setup_configs(db, test_databases)
        comparison_row, result, _ = comparison_service.run_comparison(db, "live", src_id, "live", dst_id)
        assert comparison_row.source_label == "Src"
        assert comparison_row.destination_label == "Dst"
        assert comparison_row.source_label == result.source_label
        comparison_id = comparison_row.id

    from app.services import report_service
    with session_scope() as db:
        reloaded = report_service.get_comparison_or_404(db, comparison_id)
        assert reloaded.source_label == "Src"
        assert reloaded.destination_label == "Dst"


def test_delete_report_removes_file_and_comparison_history(tmp_app_env, test_databases):
    import os

    from app.services import report_service

    with session_scope() as db:
        src_id, dst_id = _setup_configs(db, test_databases)
        comparison_row, _, report_path = comparison_service.run_comparison(db, "live", src_id, "live", dst_id)
        comparison_id = comparison_row.id
        reports = report_service.list_reports(db)
        report_id = next(r.id for r in reports if r.comparison_id == comparison_id)

    assert os.path.exists(report_path)

    with session_scope() as db:
        report_service.delete_report(db, report_id)

    assert not os.path.exists(report_path)

    with session_scope() as db:
        # Report row is gone.
        import pytest as _pytest
        with _pytest.raises(LookupError):
            report_service.get_report_or_404(db, report_id)
        # The comparison no longer appears in recent comparisons.
        with _pytest.raises(LookupError):
            report_service.get_comparison_or_404(db, comparison_id)


def test_failed_comparison_persists_error_message(tmp_app_env, test_databases):
    with session_scope() as db:
        _, destination_id = _setup_configs(db, test_databases)
        failed_source = config_service.create_configuration(
            db, "Missing Source", "sqlite",
            {"database_file": "does-not-exist.db"},
        )
        comparison_row = None
        try:
            comparison_service.run_comparison(
                db, "live", failed_source.id, "live", destination_id
            )
        except Exception:
            comparison_row = report_service.list_comparisons(db, 1)[0]

        assert comparison_row is not None
        assert comparison_row.status == "ERROR"
        assert comparison_row.error_message
