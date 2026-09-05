from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Comparison, Report
from app.storage import report_storage


def list_comparisons(db: Session, limit: int = 50) -> list[Comparison]:
    return list(db.scalars(select(Comparison).order_by(Comparison.created_at.desc()).limit(limit)))


def get_comparison_or_404(db: Session, comparison_id: str) -> Comparison:
    obj = db.get(Comparison, comparison_id)
    if obj is None:
        raise LookupError(f"Comparison not found: {comparison_id}")
    return obj


def list_reports(db: Session, limit: int = 50) -> list[Report]:
    return list(db.scalars(select(Report).order_by(Report.created_at.desc()).limit(limit)))


def get_report_or_404(db: Session, report_id: str) -> Report:
    obj = db.get(Report, report_id)
    if obj is None:
        raise LookupError(f"Report not found: {report_id}")
    return obj


def get_report_html(db: Session, report_id: str) -> str:
    report = get_report_or_404(db, report_id)
    return report_storage.load_report(report.file_path)


def delete_report(db: Session, report_id: str) -> None:
    """Delete a report and the comparison represented by that report."""
    report = get_report_or_404(db, report_id)
    from pathlib import Path
    try:
        Path(report.file_path).unlink(missing_ok=True)
    except Exception:
        pass
    comparison = db.get(Comparison, report.comparison_id)
    db.delete(report)
    if comparison is not None:
        db.delete(comparison)
    db.commit()


def delete_comparison(db: Session, comparison_id: str) -> None:
    """Delete a comparison whether or not report generation completed."""
    comparison = get_comparison_or_404(db, comparison_id)
    report = db.scalar(select(Report).where(Report.comparison_id == comparison_id))
    if report is not None:
        from pathlib import Path
        try:
            Path(report.file_path).unlink(missing_ok=True)
        except Exception:
            pass
        db.delete(report)
    db.delete(comparison)
    db.commit()


def dashboard_stats(db: Session) -> dict:
    from app.models import DatabaseConfiguration, SchemaVersion, TableFilter
    comparisons = list(db.scalars(select(Comparison)))
    return {
        "config_count": db.query(DatabaseConfiguration).count(),
        "filter_count": db.query(TableFilter).count(),
        "schema_version_count": db.query(SchemaVersion).count(),
        "comparison_count": len(comparisons),
        "passed_count": sum(1 for c in comparisons if c.status == "PASS"),
        "failed_count": sum(1 for c in comparisons if c.status in ("FAIL", "ERROR")),
        "tables_compared_total": sum(c.table_count or 0 for c in comparisons),
        "differences_found_total": sum(c.difference_count or 0 for c in comparisons),
    }
