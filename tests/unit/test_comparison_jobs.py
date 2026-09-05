from types import SimpleNamespace

from app.services import comparison_service


def test_create_comparison_job_persists_running_and_submits(monkeypatch):
    submitted = {}

    class FakeExecutor:
        def submit(self, function, *args):
            submitted["function"] = function
            submitted["args"] = args

    class FakeDb:
        def get(self, _, config_id):
            return SimpleNamespace(
                id=config_id,
                name="Source Config" if config_id == "source" else "Destination Config",
                configuration={"database": "APP", "schema": "PUBLIC"},
            )

        def add(self, obj):
            self.obj = obj
            obj.id = "comparison-id"

        def commit(self):
            submitted["committed"] = True

        def refresh(self, obj):
            pass

    monkeypatch.setattr(comparison_service, "_JOB_EXECUTOR", FakeExecutor())
    row = comparison_service.create_comparison_job(
        FakeDb(), "live", "source", "live", "destination"
    )

    assert row.id == "comparison-id"
    assert row.status == "RUNNING"
    assert row.source_label == "Source Config (APP.PUBLIC)"
    assert row.destination_label == "Destination Config (APP.PUBLIC)"
    assert submitted["committed"] is True
    assert submitted["args"][0] == "comparison-id"