from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import report_service

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {"active": "dashboard"})


@router.get("/database-configurations", response_class=HTMLResponse)
def database_configurations_page(request: Request):
    return templates.TemplateResponse(request, "database_configurations.html", {"active": "configs"})


@router.get("/table-filters", response_class=HTMLResponse)
def table_filters_page(request: Request):
    return templates.TemplateResponse(request, "table_filters.html", {"active": "filters"})


@router.get("/schema-extraction", response_class=HTMLResponse)
def schema_extraction_page(request: Request):
    return templates.TemplateResponse(request, "schema_extraction.html", {"active": "extraction"})


@router.get("/schema-versions", response_class=HTMLResponse)
def schema_versions_page(request: Request):
    return templates.TemplateResponse(request, "schema_versions.html", {"active": "versions"})


@router.get("/compare", response_class=HTMLResponse)
def compare_page(request: Request):
    return templates.TemplateResponse(request, "compare.html", {"active": "compare"})


@router.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request):
    return templates.TemplateResponse(request, "reports.html", {"active": "reports"})


@router.get("/reports/view/{comparison_id}", response_class=HTMLResponse)
def view_report(comparison_id: str, db: Session = Depends(get_db)):
    """Stable, shareable local report URL (section 15: 'Share' = a stable
    local report URL for V1)."""
    try:
        comparison = report_service.get_comparison_or_404(db, comparison_id)
        if not comparison.report_path:
            raise HTTPException(status_code=404, detail="No report available for this comparison")
        from app.storage import report_storage
        html = report_storage.load_report(comparison.report_path)
        return HTMLResponse(html)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
