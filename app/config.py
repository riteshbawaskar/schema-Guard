"""Application-wide configuration, loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_validator_master_key: str = ""
    db_validator_app_db: str = "data/app.db"
    db_validator_data_dir: str = "data"
    db_validator_log_level: str = "INFO"

    @property
    def data_dir(self) -> Path:
        p = Path(self.db_validator_data_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def schemas_dir(self) -> Path:
        p = self.data_dir / "schemas"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def reports_dir(self) -> Path:
        p = self.data_dir / "reports"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def uploads_dir(self) -> Path:
        p = self.data_dir / "uploads"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def app_db_path(self) -> Path:
        p = Path(self.db_validator_app_db)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def app_db_url(self) -> str:
        return f"sqlite:///{self.app_db_path.as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
