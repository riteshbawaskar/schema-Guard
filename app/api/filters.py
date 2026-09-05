from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import filter_service

router = APIRouter(prefix="/api/filters", tags=["filters"])


class FilterCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    match_mode: str
    include_patterns: list[str] = []
    exclude_patterns: list[str] = []


class FilterUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    match_mode: Optional[str] = None
    include_patterns: Optional[list[str]] = None
    exclude_patterns: Optional[list[str]] = None


class CloneRequest(BaseModel):
    new_name: str


class PreviewRequest(BaseModel):
    candidate_names: list[str]


def _serialize(obj) -> dict:
    return {
        "id": obj.id, "name": obj.name, "description": obj.description,
        "match_mode": obj.match_mode, "include_patterns": obj.include_patterns,
        "exclude_patterns": obj.exclude_patterns,
        "created_at": obj.created_at, "updated_at": obj.updated_at,
    }


@router.get("")
def list_filters(db: Session = Depends(get_db)):
    return [_serialize(o) for o in filter_service.list_filters(db)]


@router.post("")
def create_filter(payload: FilterCreateRequest, db: Session = Depends(get_db)):
    obj = filter_service.create_filter(
        db, payload.name, payload.match_mode, payload.include_patterns, payload.exclude_patterns, payload.description
    )
    return _serialize(obj)


@router.get("/{filter_id}")
def get_filter(filter_id: str, db: Session = Depends(get_db)):
    try:
        return _serialize(filter_service.get_filter_or_404(db, filter_id))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{filter_id}")
def update_filter(filter_id: str, payload: FilterUpdateRequest, db: Session = Depends(get_db)):
    try:
        obj = filter_service.update_filter(db, filter_id, **payload.model_dump(exclude_unset=True))
        return _serialize(obj)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{filter_id}")
def delete_filter(filter_id: str, db: Session = Depends(get_db)):
    try:
        filter_service.delete_filter(db, filter_id)
        return {"deleted": True}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{filter_id}/clone")
def clone_filter(filter_id: str, payload: CloneRequest, db: Session = Depends(get_db)):
    try:
        obj = filter_service.clone_filter(db, filter_id, payload.new_name)
        return _serialize(obj)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{filter_id}/preview")
def preview_filter(filter_id: str, payload: PreviewRequest, db: Session = Depends(get_db)):
    try:
        matched = filter_service.preview_filter(db, filter_id, payload.candidate_names)
        return {
            "matched": matched,
            "matched_count": len(matched),
            "excluded": sorted(set(payload.candidate_names) - set(matched)),
        }
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
