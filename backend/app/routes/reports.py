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
from app.models import Alarm, Area, Asset, Report, Sensor, Site, Telemetry, User
from app.services.audit import write_audit

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
) -> Dict[str, Any]:
    """Compute summary numbers used by the cards + PDF.

    ``avg(power_kw) * window_hours`` is a coarse but defensible energy
    estimate; we also surface ``peak_kw`` directly. ``top_assets`` is the
    five largest energy consumers in the window.
    """
    duration_hours = max((end_ts - start_ts).total_seconds() / 3600.0, 0.0)
    out: Dict[str, Any] = {
        "from": start_ts.isoformat(),
        "to": end_ts.isoformat(),
        "duration_hours": round(duration_hours, 3),
        "asset_count": len(assets),
        "total_kwh": 0.0,
        "peak_kw": 0.0,
        "top_assets": [],
    }
    if not assets or duration_hours == 0.0:
        return out

    asset_ids = [a.id for a in assets]
    name_by_id = {a.id: a.name for a in assets}

    stmt = (
        select(
            Telemetry.asset_id,
            func.avg(Telemetry.value),
            func.max(Telemetry.value),
        )
        .where(
            and_(
                Telemetry.asset_id.in_(asset_ids),
                Telemetry.metric == "power_kw",
                Telemetry.ts >= start_ts,
                Telemetry.ts < end_ts,
            )
        )
        .group_by(Telemetry.asset_id)
    )
    per_asset: List[Tuple[UUID, float, float]] = []
    for aid, avg_kw, max_kw in db.execute(stmt).all():
        per_asset.append((aid, float(avg_kw or 0.0), float(max_kw or 0.0)))

    total_kwh = 0.0
    peak_kw = 0.0
    rows: List[Dict[str, Any]] = []
    for aid, avg_kw, max_kw in per_asset:
        kwh = avg_kw * duration_hours
        total_kwh += kwh
        if max_kw > peak_kw:
            peak_kw = max_kw
        rows.append({"asset_id": str(aid), "asset_name": name_by_id.get(aid, "?"), "energy_kwh": round(kwh, 2), "avg_power_kw": round(avg_kw, 3), "peak_kw": round(max_kw, 3)})

    rows.sort(key=lambda r: r["energy_kwh"], reverse=True)
    out["total_kwh"] = round(total_kwh, 2)
    out["peak_kw"] = round(peak_kw, 3)
    out["top_assets"] = rows[:5]
    return out


def _alarm_summary(
    db: Session,
    assets: List[Asset],
    start_ts: datetime,
    end_ts: datetime,
) -> Dict[str, int]:
    """Count alarms opened in the window by state."""
    if not assets:
        return {"active": 0, "acknowledged": 0, "resolved": 0, "total": 0}
    asset_ids = [a.id for a in assets]
    rows = db.execute(
        select(Alarm.state, func.count())
        .where(
            and_(
                Alarm.asset_id.in_(asset_ids),
                Alarm.opened_at >= start_ts,
                Alarm.opened_at < end_ts,
            )
        )
        .group_by(Alarm.state)
    ).all()
    by_state = {state: int(n) for state, n in rows}
    return {
        "active": by_state.get("OPEN", 0),
        "acknowledged": by_state.get("ACK", 0),
        "resolved": by_state.get("RESOLVED", 0),
        "total": sum(by_state.values()),
    }


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
    summary = _energy_summary(db, assets, start_ts, end_ts)
    summary["alarms"] = _alarm_summary(db, assets, start_ts, end_ts)
    summary["site"] = {"id": str(site.id), "name": site.name} if site else None
    summary["asset_id"] = str(asset_id) if asset_id else None
    return summary

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

    Columns: ``timestamp, site, area, asset, sensor, metric, value, unit``.
    The CSV is one row per telemetry point so an analyst can reconstruct
    the trend in their tool of choice. Capped to 100k rows; managers who
    need more should narrow the window or use the PDF summary.
    """
    assets, start_ts, end_ts, _site = _resolve_window(site_id, asset_id, start, end, db, user)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp", "site", "area", "asset", "sensor", "metric", "value", "unit"])

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
        for ts, site_name, area_name, asset_name, sensor_label, metric, value, unit in db.execute(stmt).all():
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
    summary = _energy_summary(db, assets, start_ts, end_ts)
    alarms = _alarm_summary(db, assets, start_ts, end_ts)
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
        ["Assets", str(summary["asset_count"])],
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

    totals_rows = [
        ["Total energy", f"{summary['total_kwh']:.2f} kWh"],
        ["Peak power", f"{summary['peak_kw']:.2f} kW"],
        [
            "Alarms",
            f"active {alarms['active']} / acknowledged {alarms['acknowledged']} / resolved {alarms['resolved']}",
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
    for idx, row in enumerate(summary["top_assets"], start=1):
        top_data.append(
            [
                str(idx),
                row["asset_name"],
                f"{row['energy_kwh']:.2f}",
                f"{row['avg_power_kw']:.2f}",
                f"{row['peak_kw']:.2f}",
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