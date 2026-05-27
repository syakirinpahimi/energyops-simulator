"""Report generation routes.

Three endpoints power the reports flow:

- ``GET /reports/energy/summary`` -> JSON summary cards (no download)
- ``GET /reports/energy.csv``      -> per-reading CSV download
- ``GET /reports/energy.pdf``      -> single-page PDF energy report

Reports are streamed inline so a manager can ``curl > file`` directly. A
row is also written to the ``reports`` table plus an audit entry for the
download trail.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import roles_at_least
from app.models import Area, Asset, Report, Sensor, Site, Telemetry, User
from app.services.audit import write_audit
from app.services.report_service import (
    AlarmSummary,
    EnergySummary,
    compute_alarm_summary,
    compute_energy_summary,
)

router = APIRouter(prefix="/reports", tags=["reports"])

_REPORT_GUARD = roles_at_least("manager")
_PDF_TITLE = "Industrial EnergyOps Energy Report"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_window(
    site_id: Optional[UUID],
    asset_id: Optional[UUID],
    start: Optional[datetime],
    end: Optional[datetime],
    db: Session,
    user: User,
) -> Tuple[List[Asset], datetime, datetime, Optional[Site]]:
    """Resolve the asset list + time window for a report request.

    Returns ``(assets, start_ts, end_ts, site)`` where ``site`` is the
    resolved site row when ``site_id`` was supplied (used for the PDF
    header) or ``None`` otherwise.
    """
    end_ts = end or datetime.now(timezone.utc)
    start_ts = start or (end_ts - timedelta(days=7))
    if start_ts >= end_ts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_RANGE", "message": "start must be before end"}},
        )

    stmt = (
        select(Asset)
        .join(Area, Asset.area_id == Area.id)
        .join(Site, Area.site_id == Site.id)
        .where(Site.company_id == user.company_id)
    )
    if site_id is not None:
        stmt = stmt.where(Area.site_id == site_id)
    if asset_id is not None:
        stmt = stmt.where(Asset.id == asset_id)
    assets = list(db.scalars(stmt))

    site = db.get(Site, site_id) if site_id is not None else None
    return assets, start_ts, end_ts, site


def _energy_summary(
    db: Session,
    assets: List[Asset],
    start_ts: datetime,
    end_ts: datetime,
) -> EnergySummary:
    """Thin wrapper kept so route handlers and tests can share one symbol."""
    return compute_energy_summary(db, assets, start_ts, end_ts)


def _alarm_summary(
    db: Session,
    assets: List[Asset],
    start_ts: datetime,
    end_ts: datetime,
) -> AlarmSummary:
    """Thin wrapper around the service so the routes stay flat."""
    return compute_alarm_summary(db, assets, start_ts, end_ts)


def _record_report(
    db: Session,
    *,
    user: User,
    fmt: str,
    site_id: Optional[UUID],
    asset_id: Optional[UUID],
    start_ts: datetime,
    end_ts: datetime,
    size_bytes: int,
) -> Report:
    report = Report(
        kind="energy",
        format=fmt,
        status="ready",
        params={
            "site_id": str(site_id) if site_id else None,
            "asset_id": str(asset_id) if asset_id else None,
            "from": start_ts.isoformat(),
            "to": end_ts.isoformat(),
        },
        file_size_bytes=size_bytes,
        created_by=user.id,
        finished_at=datetime.now(timezone.utc),
    )
    db.add(report)
    write_audit(
        db,
        actor=user,
        action="report.create",
        target_type="report",
        metadata={"kind": "energy", "format": fmt, "size_bytes": size_bytes},
    )
    db.commit()
    db.refresh(report)
    return report


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/energy/summary")
def energy_report_summary(
    site_id: Optional[UUID] = Query(default=None),
    asset_id: Optional[UUID] = Query(default=None),
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(_REPORT_GUARD),
) -> Dict[str, Any]:
    """Summary numbers that back the ``Reports`` page cards.

    No file is written; this is intentionally cheap so the UI can call it
    on every filter change.
    """
    assets, start_ts, end_ts, site = _resolve_window(site_id, asset_id, start, end, db, user)
    energy = _energy_summary(db, assets, start_ts, end_ts)
    alarms = _alarm_summary(db, assets, start_ts, end_ts)
    payload = energy.as_summary_dict()
    payload["alarms"] = alarms.as_dict()
    payload["site"] = {"id": str(site.id), "name": site.name} if site else None
    payload["asset_id"] = str(asset_id) if asset_id else None
    return payload

@router.get("/energy.csv")
def energy_report_csv(
    site_id: Optional[UUID] = Query(default=None),
    asset_id: Optional[UUID] = Query(default=None),
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(_REPORT_GUARD),
) -> StreamingResponse:
    """Per-reading CSV download.

    Columns: ``timestamp, site, area, asset, sensor, metric, value, unit,
    quality``. The CSV is one row per telemetry point so an analyst can
    reconstruct the trend in their tool of choice. Capped to 100k rows;
    managers who need more should narrow the window or use the PDF
    summary.
    """
    assets, start_ts, end_ts, _site = _resolve_window(site_id, asset_id, start, end, db, user)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["timestamp", "site", "area", "asset", "sensor", "metric", "value", "unit", "quality"]
    )

    if assets:
        asset_ids = [a.id for a in assets]
        stmt = (
            select(
                Telemetry.ts,
                Site.name,
                Area.name,
                Asset.name,
                Sensor.metric,
                Telemetry.metric,
                Telemetry.value,
                Telemetry.unit,
                Telemetry.quality,
            )
            .join(Asset, Asset.id == Telemetry.asset_id)
            .join(Area, Area.id == Asset.area_id)
            .join(Site, Site.id == Area.site_id)
            .join(Sensor, Sensor.id == Telemetry.sensor_id, isouter=True)
            .where(
                and_(
                    Telemetry.asset_id.in_(asset_ids),
                    Telemetry.ts >= start_ts,
                    Telemetry.ts < end_ts,
                )
            )
            .order_by(Telemetry.ts.asc())
            .limit(100_000)
        )
        for ts, site_name, area_name, asset_name, sensor_label, metric, value, unit, quality in db.execute(stmt).all():
            writer.writerow(
                [
                    ts.isoformat(),
                    site_name or "",
                    area_name or "",
                    asset_name or "",
                    sensor_label or metric,
                    metric,
                    f"{float(value):.6g}",
                    unit or "",
                    str(quality) if quality is not None else "",
                ]
            )

    payload = buf.getvalue().encode("utf-8")
    _record_report(
        db,
        user=user,
        fmt="csv",
        site_id=site_id,
        asset_id=asset_id,
        start_ts=start_ts,
        end_ts=end_ts,
        size_bytes=len(payload),
    )

    return StreamingResponse(
        iter([payload]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="energy-report.csv"'},
    )
@router.get("/energy.pdf")
def energy_report_pdf(
    site_id: Optional[UUID] = Query(default=None),
    asset_id: Optional[UUID] = Query(default=None),
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(_REPORT_GUARD),
) -> StreamingResponse:
    """Single-page PDF energy report."""
    # Lazy import so the server can start even if reportlab is missing.
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    assets, start_ts, end_ts, site = _resolve_window(site_id, asset_id, start, end, db, user)
    energy = _energy_summary(db, assets, start_ts, end_ts)
    alarms = _alarm_summary(db, assets, start_ts, end_ts)
    top_assets = energy.top_assets()
    generated_at = datetime.now(timezone.utc)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        title=_PDF_TITLE,
        author=user.email,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    story: list = [Paragraph(_PDF_TITLE, styles["Title"])]

    site_label = site.name if site else "All sites"
    meta_rows = [
        ["Site", site_label],
        ["Date range", f"{start_ts.isoformat()}  ->  {end_ts.isoformat()}"],
        ["Generated", generated_at.isoformat()],
        ["Assets", str(energy.asset_count)],
    ]
    meta_table = Table(meta_rows, hAlign="LEFT", colWidths=[35 * mm, 130 * mm])
    meta_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.extend([Spacer(1, 6), meta_table, Spacer(1, 12)])

    sev = alarms.by_severity
    totals_rows = [
        ["Total energy", f"{energy.total_kwh:.2f} kWh"],
        ["Peak power", f"{energy.peak_kw:.2f} kW"],
        [
            "Alarms (status)",
            f"active {alarms.by_status.get('active', 0)} / "
            f"acknowledged {alarms.by_status.get('acknowledged', 0)} / "
            f"resolved {alarms.by_status.get('resolved', 0)}",
        ],
        [
            "Alarms (severity)",
            f"info {sev.get('info', 0)} / warning {sev.get('warning', 0)} / "
            f"critical {sev.get('critical', 0)}",
        ],
    ]
    totals_table = Table(totals_rows, hAlign="LEFT", colWidths=[35 * mm, 130 * mm])
    totals_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f3f4f6")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([Paragraph("Summary", styles["Heading2"]), totals_table, Spacer(1, 12)])

    story.append(Paragraph("Top energy-consuming assets", styles["Heading2"]))
    top_data = [["Rank", "Asset", "Energy (kWh)", "Avg kW", "Peak kW"]]
    for idx, row in enumerate(top_assets, start=1):
        top_data.append(
            [
                str(idx),
                row.asset_name,
                f"{row.energy_kwh:.2f}",
                f"{row.avg_power_kw:.2f}",
                f"{row.peak_kw:.2f}",
            ]
        )
    if len(top_data) == 1:
        top_data.append(["-", "(no data)", "-", "-", "-"])
    top_table = Table(top_data, hAlign="LEFT", colWidths=[15 * mm, 70 * mm, 30 * mm, 25 * mm, 25 * mm])
    top_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
            ]
        )
    )
    story.append(top_table)

    story.append(Spacer(1, 16))
    story.append(
        Paragraph(
            f"<font size=8 color='#6b7280'>Generated by EnergyOps for {user.email}</font>",
            styles["Normal"],
        )
    )

    doc.build(story)
    payload = buf.getvalue()
    _record_report(
        db,
        user=user,
        fmt="pdf",
        site_id=site_id,
        asset_id=asset_id,
        start_ts=start_ts,
        end_ts=end_ts,
        size_bytes=len(payload),
    )

    return StreamingResponse(
        iter([payload]),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="energy-report.pdf"'},
    )