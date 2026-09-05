from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import extraction_service

router = APIRouter(prefix="/api/extraction", tags=["extraction"])


class PreviewRequest(BaseModel):
    database_configuration_id: str
    database: Optional[str] = None
    schema_name: Optional[str] = None
    filter_id: Optional[str] = None


@router.post("/preview")
def preview_tables(payload: PreviewRequest, db: Session = Depends(get_db)):
    try:
        return extraction_service.preview_tables(
            db, payload.database_configuration_id, payload.database, payload.schema_name, payload.filter_id
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
