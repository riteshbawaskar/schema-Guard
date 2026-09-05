from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.filters.engine import FilterDefinition, apply_filter
from app.models import TableFilter


def to_filter_definition(obj: TableFilter) -> FilterDefinition:
    return FilterDefinition(
        name=obj.name, match_mode=obj.match_mode,
        include_patterns=obj.include_patterns or [], exclude_patterns=obj.exclude_patterns or [],
    )


def create_filter(db: Session, name: str, match_mode: str, include_patterns: list[str],
                   exclude_patterns: list[str], description: str | None = None) -> TableFilter:
    obj = TableFilter(
        name=name, description=description, match_mode=match_mode,
        include_patterns=include_patterns, exclude_patterns=exclude_patterns,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_filter(db: Session, filter_id: str, **kwargs) -> TableFilter:
    obj = get_filter_or_404(db, filter_id)
    for k, v in kwargs.items():
        if v is not None and hasattr(obj, k):
            setattr(obj, k, v)
    obj.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return obj


def clone_filter(db: Session, filter_id: str, new_name: str) -> TableFilter:
    src = get_filter_or_404(db, filter_id)
    obj = TableFilter(
        name=new_name, description=src.description, match_mode=src.match_mode,
        include_patterns=list(src.include_patterns), exclude_patterns=list(src.exclude_patterns),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def delete_filter(db: Session, filter_id: str) -> None:
    obj = get_filter_or_404(db, filter_id)
    db.delete(obj)
    db.commit()


def get_filter_or_404(db: Session, filter_id: str) -> TableFilter:
    obj = db.get(TableFilter, filter_id)
    if obj is None:
        raise LookupError(f"Filter not found: {filter_id}")
    return obj


def list_filters(db: Session) -> list[TableFilter]:
    return list(db.scalars(select(TableFilter).order_by(TableFilter.name)))


def preview_filter(db: Session, filter_id: str, candidate_names: list[str]) -> list[str]:
    obj = get_filter_or_404(db, filter_id)
    return apply_filter(candidate_names, to_filter_definition(obj))
