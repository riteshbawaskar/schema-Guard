"""Shared pytest fixtures. Every test run gets its own isolated app.db and
data/ directory (via env vars + monkeypatched settings cache) so tests never
touch the real data/app.db used by a running instance of the app.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def tmp_app_env(tmp_path, monkeypatch):
    """Points the app at a throwaway SQLite app.db and data dir, and resets
    all module-level singletons (engine, sessionmaker, settings cache,
    secret service) so each test is fully isolated."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("DB_VALIDATOR_APP_DB", str(data_dir / "app.db"))
    monkeypatch.setenv("DB_VALIDATOR_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DB_VALIDATOR_MASTER_KEY", "test-master-key-0123456789")

    from app import config as config_module
    config_module.get_settings.cache_clear()

    import app.database as database_module
    database_module._engine = None
    database_module._SessionLocal = None

    import app.security.secret_service as secret_module
    secret_module._default_service = None

    from app.database import init_db
    init_db()

    yield data_dir

    database_module._engine = None
    database_module._SessionLocal = None
    secret_module._default_service = None
    config_module.get_settings.cache_clear()


@pytest.fixture()
def test_databases(tmp_path):
    """Builds fresh source.db / destination.db in a temp dir using the
    project's official test-data generator, so tests exercise the exact
    same intentional differences documented in scripts/create_test_databases.py.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "create_test_databases", ROOT / "scripts" / "create_test_databases.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    src_conn = module._fresh_db(tmp_path / "source.db")
    module.build_source(src_conn)
    src_conn.close()

    dst_conn = module._fresh_db(tmp_path / "destination.db")
    module.build_destination(dst_conn)
    dst_conn.close()

    return {"source": str(tmp_path / "source.db"), "destination": str(tmp_path / "destination.db")}
