from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import comparison_service, report_service
from app.services.comparison_service import SourceType

router = APIRouter(prefix="/api/compare", tags=["comparison"])


class CompareRequest(BaseModel):
    source_type: SourceType
    source_reference: str
    destination_type: SourceType
    destination_reference: str
    source_filter_id: Optional[str] = None
    destination_filter_id: Optional[str] = None
    source_database: Optional[str] = None
    source_schema: Optional[str] = None
    destination_database: Optional[str] = None
    destination_schema: Optional[str] = None
    normalization_mode: str = "compatible"
    fail_on: Optional[list[str]] = None


def _serialize_comparison(obj) -> dict:
    return {
        "id": obj.id, "source_type": obj.source_type, "source_reference": obj.source_reference,
        "destination_type": obj.destination_type, "destination_reference": obj.destination_reference,
        "source_label": obj.source_label, "destination_label": obj.destination_label,
        "status": obj.status, "table_count": obj.table_count, "column_count": obj.column_count,
        "difference_count": obj.difference_count, "critical_count": obj.critical_count,
        "high_count": obj.high_count, "medium_count": obj.medium_count, "low_count": obj.low_count,
        "info_count": obj.info_count, "report_path": obj.report_path, "error_message": obj.error_message,
        "created_at": obj.created_at, "duration": obj.duration,
    }


@router.post("")
def run_comparison(payload: CompareRequest, db: Session = Depends(get_db)):
    try:
        comparison_row = comparison_service.create_comparison_job(
            db,
            payload.source_type, payload.source_reference,
            payload.destination_type, payload.destination_reference,
            payload.source_filter_id, payload.destination_filter_id,
            payload.source_database, payload.source_schema,
            payload.destination_database, payload.destination_schema,
            payload.normalization_mode, payload.fail_on,
        )
        return {"comparison": _serialize_comparison(comparison_row)}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{comparison_id}")
def get_comparison(comparison_id: str, db: Session = Depends(get_db)):
    try:
        return _serialize_comparison(report_service.get_comparison_or_404(db, comparison_id))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{comparison_id}")
def delete_comparison(comparison_id: str, db: Session = Depends(get_db)):
    try:
        report_service.delete_comparison(db, comparison_id)
        return {"deleted": True}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("")
def list_comparisons(limit: int = 50, db: Session = Depends(get_db)):
    return [_serialize_comparison(o) for o in report_service.list_comparisons(db, limit)]
