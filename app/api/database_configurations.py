from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.connectors.factory import supported_database_types
from app.database import get_db
from app.services import config_service, extraction_service

router = APIRouter(prefix="/api/database-configurations", tags=["database-configurations"])


class ConfigCreateRequest(BaseModel):
    name: str
    database_type: str
    configuration: dict[str, Any]
    enabled: bool = True
    is_default: bool = False


class ConfigUpdateRequest(BaseModel):
    name: Optional[str] = None
    configuration: Optional[dict[str, Any]] = None
    enabled: Optional[bool] = None
    is_default: Optional[bool] = None


class CloneRequest(BaseModel):
    new_name: str


def _serialize(obj) -> dict:
    return {
        "id": obj.id,
        "name": obj.name,
        "database_type": obj.database_type,
        "configuration": config_service.mask_configuration(obj.database_type, obj.configuration),
        "enabled": obj.enabled,
        "is_default": obj.is_default,
        "last_tested_at": obj.last_tested_at,
        "last_test_status": obj.last_test_status,
        "last_test_message": obj.last_test_message,
        "created_at": obj.created_at,
        "updated_at": obj.updated_at,
    }


@router.get("")
def list_configurations(db: Session = Depends(get_db)):
    return [_serialize(o) for o in config_service.list_configurations(db)]


@router.get("/supported-types")
def list_supported_types():
    return {"types": supported_database_types()}


@router.post("")
def create_configuration(payload: ConfigCreateRequest, db: Session = Depends(get_db)):
    try:
        obj = config_service.create_configuration(
            db, payload.name, payload.database_type, payload.configuration, payload.enabled, payload.is_default
        )
        return _serialize(obj)
    except config_service.ConfigValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/{config_id}")
def get_configuration(config_id: str, db: Session = Depends(get_db)):
    try:
        return _serialize(config_service.get_configuration_or_404(db, config_id))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{config_id}")
def update_configuration(config_id: str, payload: ConfigUpdateRequest, db: Session = Depends(get_db)):
    try:
        obj = config_service.update_configuration(
            db, config_id, payload.name, payload.configuration, payload.enabled, payload.is_default
        )
        return _serialize(obj)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except config_service.ConfigValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/{config_id}")
def delete_configuration(config_id: str, db: Session = Depends(get_db)):
    try:
        config_service.delete_configuration(db, config_id)
        return {"deleted": True}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{config_id}/clone")
def clone_configuration(config_id: str, payload: CloneRequest, db: Session = Depends(get_db)):
    try:
        obj = config_service.clone_configuration(db, config_id, payload.new_name)
        return _serialize(obj)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


class TestAdhocRequest(BaseModel):
    database_type: str
    configuration: dict[str, Any]
    existing_config_id: Optional[str] = None


@router.post("/test")
def test_adhoc_configuration(payload: TestAdhocRequest, db: Session = Depends(get_db)):
    """Tests connectivity using the current (possibly unsaved/edited) form
    values directly - does not require the configuration to exist yet and
    never persists anything. Always reflects the latest field values."""
    try:
        result = config_service.test_adhoc_configuration(
            db, payload.database_type, payload.configuration, payload.existing_config_id
        )
        return {"success": result.success, "message": result.message}
    except config_service.ConfigValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001
        return {"success": False, "message": f"Test failed: {e}"}


@router.post("/{config_id}/test")
def test_configuration(config_id: str, db: Session = Depends(get_db)):
    try:
        result = config_service.test_configuration(db, config_id)
        return {"success": result.success, "message": result.message}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Test failed: {e}")


@router.get("/{config_id}/databases")
def get_databases(config_id: str, db: Session = Depends(get_db)):
    try:
        return {"databases": extraction_service.list_databases(db, config_id)}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{config_id}/schemas")
def get_schemas(config_id: str, database: Optional[str] = None, db: Session = Depends(get_db)):
    try:
        return {"schemas": extraction_service.list_schemas(db, config_id, database)}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{config_id}/tables")
def get_tables(config_id: str, database: Optional[str] = None, schema: Optional[str] = None, db: Session = Depends(get_db)):
    try:
        return {"tables": extraction_service.list_tables(db, config_id, database, schema)}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
