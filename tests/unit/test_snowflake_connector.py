from app.connectors.snowflake_connector import SnowflakeConnector


def test_snowflake_pat_uses_custom_url_host(monkeypatch):
    captured = {}

    class FakeConnector:
        def connect(self, **kwargs):
            captured.update(kwargs)
            return object()

    class FakeSnowflake:
        connector = FakeConnector()

    import app.connectors.snowflake_connector as module
    monkeypatch.setattr(module, "snowflake", FakeSnowflake(), raising=False)
    monkeypatch.setattr(module, "_HAS_SNOWFLAKE", True)

    connector = SnowflakeConnector({
        "account": "org-account",
        "username": "user",
        "pat": "token",
        "url": "https://localhost:8443",
        "warehouse": "wh",
        "database": "db",
        "schema": "public",
    })
    connector.connect()

    assert captured["password"] == "token"
    assert captured["host"] == "localhost"
    assert captured["port"] == 8443
    assert "authenticator" not in captured


def test_snowflake_sso_uses_externalbrowser(monkeypatch):
    captured = {}

    class FakeConnector:
        def connect(self, **kwargs):
            captured.update(kwargs)
            return object()

    class FakeSnowflake:
        connector = FakeConnector()

    import app.connectors.snowflake_connector as module
    monkeypatch.setattr(module, "snowflake", FakeSnowflake(), raising=False)
    monkeypatch.setattr(module, "_HAS_SNOWFLAKE", True)

    SnowflakeConnector({
        "account": "org-account",
        "username": "user",
        "authentication": "sso",
        "warehouse": "wh",
        "database": "db",
        "schema": "public",
    }).connect()

    assert captured["authenticator"] == "externalbrowser"
    assert "password" not in captured