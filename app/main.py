from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import comparison, database_configurations, extraction, filters, reports, schemas
from app.database import init_db
from app.logging_config import configure_logging
from app.services import comparison_service, config_service
from app.web import router as ui_router

configure_logging()

app = FastAPI(
    title="SchemaSentry",
    description="SchemaSentry - extract, validate, version and compare database schemas.",
    version="1.0.0",
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.on_event("shutdown")
def on_shutdown() -> None:
    config_service.close_all_persistent_connectors()
    comparison_service.shutdown_comparison_jobs()


app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(database_configurations.router)
app.include_router(filters.router)
app.include_router(extraction.router)
app.include_router(schemas.router)
app.include_router(comparison.router)
app.include_router(reports.router)
app.include_router(ui_router)
