from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.schema.canonical import CanonicalSchema
from app.schema.axiom_xml import parse_axiom_xml
from app.services import extraction_service, filter_service, schema_service

router = APIRouter(prefix="/api/schema", tags=["schema"])


class ExtractRequest(BaseModel):
    database_configuration_id: str
    database: Optional[str] = None
    schema_name: Optional[str] = None
    filter_id: Optional[str] = None
    version_name: str
    description: Optional[str] = None
    save: bool = True


def _serialize_version(obj) -> dict:
    return {
        "id": obj.id, "name": obj.name, "version": obj.version, "description": obj.description,
        "database_configuration_id": obj.database_configuration_id,
        "database_type": obj.database_type, "database_name": obj.database_name,
        "schema_name": obj.schema_name, "filter_id": obj.filter_id,
        "checksum": obj.checksum, "table_count": obj.table_count, "column_count": obj.column_count,
        "created_at": obj.created_at,
    }


@router.post("/extract")
def extract_schema(payload: ExtractRequest, db: Session = Depends(get_db)):
    try:
        filter_name = None
        if payload.filter_id:
            filter_name = filter_service.get_filter_or_404(db, payload.filter_id).name
        canonical = extraction_service.extract_schema(
            db, payload.database_configuration_id, payload.database, payload.schema_name,
            payload.filter_id, filter_name,
        )
        response: dict = {"schema": canonical.model_dump(mode="json", by_alias=True, exclude_unset=True)}
        if payload.save:
            version = schema_service.save_new_schema_version(
                db, payload.version_name, canonical, payload.description,
                payload.database_configuration_id, payload.filter_id,
            )
            response["version"] = _serialize_version(version)
        return response
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/upload")
async def upload_schema(file: UploadFile = File(...)):
    """Upload canonical JSON or an Axiom DataSource XML for ad-hoc comparison."""
    import uuid
    from app.config import get_settings
    try:
        content = await file.read()
        if (file.filename or "").lower().endswith(".xml"):
            canonical = parse_axiom_xml(content)
            # Keep the user-facing filename in metadata; the stored artifact
            # intentionally continues to use a generated name.
            canonical.metadata.database_configuration = Path(file.filename or "schema.xml").name
        else:
            canonical = CanonicalSchema.model_validate_json(content)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid schema upload: {e}")
    settings = get_settings()
    dest = settings.uploads_dir / f"{uuid.uuid4()}.json"
    dest.write_text(canonical.to_canonical_json(), encoding="utf-8")
    return {"path": str(dest)}


@router.get("/versions")
def list_versions(db: Session = Depends(get_db)):
    return [_serialize_version(v) for v in schema_service.list_versions(db)]


@router.post("/versions/import")
async def import_version(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        content = await file.read()
        canonical = CanonicalSchema.model_validate_json(content)
        version = schema_service.import_uploaded_schema(db, name, canonical, description)
        return _serialize_version(version)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid schema JSON: {e}")


@router.get("/versions/{version_id}")
def get_version(version_id: str, db: Session = Depends(get_db)):
    try:
        return _serialize_version(schema_service.get_version_or_404(db, version_id))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/versions/{version_id}/download", response_class=PlainTextResponse)
def download_version(version_id: str, db: Session = Depends(get_db)):
    try:
        version = schema_service.get_version_or_404(db, version_id)
        canonical = schema_service.load_canonical_schema(version)
        return PlainTextResponse(canonical.to_canonical_json(), media_type="application/json")
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/versions/{version_id}")
def delete_version(version_id: str, db: Session = Depends(get_db)):
    try:
        schema_service.delete_version(db, version_id)
        return {"deleted": True}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/versions/{version_id}/rename")
def rename_version(version_id: str, new_name: str, db: Session = Depends(get_db)):
    try:
        return _serialize_version(schema_service.rename_version(db, version_id, new_name))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
