from types import SimpleNamespace

from app.services import config_service


class FakeConnector:
    def __init__(self, configuration):
        self.configuration = configuration
        self._conn = None
        self.connect_count = 0
        self.close_count = 0

    def connect(self):
        self.connect_count += 1
        self._conn = object()

    def close(self):
        self.close_count += 1
        self._conn = None


def test_sso_connection_is_reused_per_configuration(monkeypatch):
    config_service.close_all_persistent_connectors()
    connectors = []

    def fake_create_connector(_, configuration):
        connector = FakeConnector(configuration)
        connectors.append(connector)
        return connector

    monkeypatch.setattr(config_service, "create_connector", fake_create_connector)
    configs = {
        "dev": SimpleNamespace(
            id="dev", database_type="snowflake", configuration={"authentication": "sso"}, name="Dev"
        ),
        "prod": SimpleNamespace(
            id="prod", database_type="snowflake", configuration={"authentication": "sso"}, name="Prod"
        ),
    }
    monkeypatch.setattr(config_service, "get_configuration_or_404", lambda _, config_id: configs[config_id])

    with config_service.connection_scope(None, "dev") as first:
        pass
    with config_service.connection_scope(None, "dev") as second:
        pass
    with config_service.connection_scope(None, "prod") as other:
        pass

    assert first is second
    assert first is not other
    assert connectors[0].connect_count == 1
    assert connectors[2].connect_count == 1
    config_service.close_all_persistent_connectors()
    assert first.close_count == 1
    assert other.close_count == 1