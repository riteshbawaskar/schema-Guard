from app.database import session_scope
from app.services import config_service, filter_service, schema_service


def test_database_configuration_persists_and_masks_secrets(tmp_app_env):
    with session_scope() as db:
        obj = config_service.create_configuration(
            db, "Test Postgres", "postgresql",
            {"host": "localhost", "port": 5432, "database": "app", "username": "u", "password": "supersecret"},
        )
        config_id = obj.id

    # Simulate an application restart: reload via a new session against the same file.
    with session_scope() as db:
        reloaded = config_service.get_configuration_or_404(db, config_id)
        assert reloaded.name == "Test Postgres"
        # Secret must be encrypted at rest, not stored in plaintext.
        assert reloaded.configuration["password"] != "supersecret"
        assert reloaded.configuration["password"].startswith("enc::")

        masked = config_service.mask_configuration(reloaded.database_type, reloaded.configuration)
        assert masked["password"] == "********"

        # Decrypt only for runtime use.
        decrypted = config_service.decrypt_configuration(reloaded.database_type, reloaded.configuration)
        assert decrypted["password"] == "supersecret"


def test_secrets_never_returned_by_masked_configuration(tmp_app_env):
    with session_scope() as db:
        obj = config_service.create_configuration(
            db, "Snowflake QA", "snowflake",
            {"account": "acct", "username": "u", "pat": "super-secret-pat", "warehouse": "wh", "database": "db", "schema": "sch"},
        )
        masked = config_service.mask_configuration(obj.database_type, obj.configuration)
    assert "super-secret-pat" not in str(masked)
    assert masked["pat"] == "********"


def test_table_filter_persists(tmp_app_env):
    with session_scope() as db:
        f = filter_service.create_filter(db, "AX Tables", "wildcard", ["AX*"], ["AX_TEMP*"])
        filter_id = f.id

    with session_scope() as db:
        reloaded = filter_service.get_filter_or_404(db, filter_id)
        assert reloaded.name == "AX Tables"
        assert reloaded.include_patterns == ["AX*"]
        assert reloaded.exclude_patterns == ["AX_TEMP*"]


def test_schema_version_persists_with_file_artifact(tmp_app_env, test_databases):
    from app.connectors.sqlite_connector import SQLiteConnector

    connector = SQLiteConnector({"database_file": test_databases["source"]})
    with connector:
        canonical = connector.extract_schema(None, None)

    with session_scope() as db:
        version = schema_service.save_new_schema_version(db, "Source v1", canonical)
        version_id = version.id
        file_path = version.file_path

    import os
    assert os.path.exists(file_path)

    with session_scope() as db:
        reloaded = schema_service.get_version_or_404(db, version_id)
        loaded_schema = schema_service.load_canonical_schema(reloaded)
        assert loaded_schema.table_count() == canonical.table_count()


def test_update_configuration_preserves_unchanged_masked_secret(tmp_app_env):
    with session_scope() as db:
        obj = config_service.create_configuration(
            db, "Preserve Secret Test", "postgresql",
            {"host": "h", "port": 5432, "database": "d", "username": "u", "password": "original-secret"},
        )
        config_id = obj.id

    with session_scope() as db:
        # Simulate a UI edit that sends back the masked placeholder for password.
        config_service.update_configuration(
            db, config_id, configuration={"host": "h2", "port": 5432, "database": "d", "username": "u", "password": "********"}
        )

    with session_scope() as db:
        reloaded = config_service.get_configuration_or_404(db, config_id)
        decrypted = config_service.decrypt_configuration(reloaded.database_type, reloaded.configuration)
        assert decrypted["password"] == "original-secret"
        assert reloaded.configuration["host"] == "h2"


def test_update_configuration_clears_optional_snowflake_url(tmp_app_env):
    with session_scope() as db:
        obj = config_service.create_configuration(
            db, "Snowflake URL Clear Test", "snowflake",
            {
                "account": "acct", "username": "u", "pat": "secret",
                "url": "https://old.example", "warehouse": "wh",
                "database": "db", "schema": "sch",
            },
        )
        config_id = obj.id

    with session_scope() as db:
        config_service.update_configuration(
            db, config_id,
            configuration={
                "account": "acct", "username": "u", "pat": "********",
                "url": "", "warehouse": "wh", "database": "db", "schema": "sch",
            },
        )

    with session_scope() as db:
        reloaded = config_service.get_configuration_or_404(db, config_id)
        assert reloaded.configuration["url"] == ""


def test_adhoc_test_uses_current_form_values_not_stale_saved_ones(tmp_app_env, test_databases):
    """Regression test: the 'Test Connection' button must always test the
    CURRENT (possibly unsaved/edited) field values, never a stale saved
    configuration from an earlier click."""
    with session_scope() as db:
        # First ad-hoc test against a file that doesn't exist - should fail.
        bad_result = config_service.test_adhoc_configuration(
            db, "sqlite", {"database_file": "/nonexistent/path.db"}
        )
        assert bad_result.success is False

        # User edits the field to point at a real file and tests again -
        # the SAME call path must reflect the new value, not the old one.
        good_result = config_service.test_adhoc_configuration(
            db, "sqlite", {"database_file": test_databases["source"]}
        )
        assert good_result.success is True


def test_adhoc_test_does_not_persist_anything(tmp_app_env, test_databases):
    with session_scope() as db:
        config_service.test_adhoc_configuration(db, "sqlite", {"database_file": test_databases["source"]})

    with session_scope() as db:
        assert config_service.list_configurations(db) == []


def test_adhoc_test_substitutes_existing_secret_for_masked_placeholder(tmp_app_env):
    with session_scope() as db:
        obj = config_service.create_configuration(
            db, "Adhoc Secret Test", "postgresql",
            {"host": "bad-host-should-fail-dns", "port": 5432, "database": "d", "username": "u", "password": "real-secret-value"},
        )
        config_id = obj.id

        # Ad-hoc test with an edited host but the masked placeholder for password
        # must decrypt and use the REAL existing password, not the literal "********".
        import app.services.config_service as cs
        original_create_connector = cs.create_connector
        captured = {}

        def spy_create_connector(database_type, configuration):
            captured["password"] = configuration.get("password")
            return original_create_connector(database_type, configuration)

        cs.create_connector = spy_create_connector
        try:
            config_service.test_adhoc_configuration(
                db, "postgresql",
                {"host": "new-host", "port": 5432, "database": "d", "username": "u", "password": "********"},
                existing_config_id=config_id,
            )
        finally:
            cs.create_connector = original_create_connector

        assert captured["password"] == "real-secret-value"
