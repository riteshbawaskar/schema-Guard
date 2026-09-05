from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import report_service

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _serialize(obj) -> dict:
    return {
        "id": obj.id, "comparison_id": obj.comparison_id, "file_path": obj.file_path,
        "file_size": obj.file_size, "created_at": obj.created_at,
    }


@router.get("")
def list_reports(limit: int = 50, db: Session = Depends(get_db)):
    return [_serialize(o) for o in report_service.list_reports(db, limit)]


@router.get("/{report_id}")
def get_report(report_id: str, db: Session = Depends(get_db)):
    try:
        return _serialize(report_service.get_report_or_404(db, report_id))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{report_id}/html", response_class=HTMLResponse)
def get_report_html(report_id: str, db: Session = Depends(get_db)):
    try:
        return HTMLResponse(report_service.get_report_html(db, report_id))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{report_id}")
def delete_report(report_id: str, db: Session = Depends(get_db)):
    try:
        report_service.delete_report(db, report_id)
        return {"deleted": True}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
