from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services import xml_mapping_service

router = APIRouter(prefix="/api/compare-config", tags=["compare-config"])


@router.get("")
def get_xml_mapping():
    return xml_mapping_service.load_mapping()


@router.put("")
def update_xml_mapping(payload: dict):
    try:
        return xml_mapping_service.save_mapping(payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc