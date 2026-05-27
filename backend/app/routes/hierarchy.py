"""Hierarchy CRUD routes: companies, sites, areas, assets, sensors.

Reads are open to any authenticated user; writes require manager+ per
``docs/API_CONTRACT.md``. We expose write endpoints as a thin layer for
the seed script and admin tooling. They are not the focus of the MVP UI.
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, roles_at_least
from app.models import Area, Asset, Company, Sensor, Site, User
from app.schemas import AreaOut, AssetOut, CompanyOut, SensorOut, SiteOut

router = APIRouter(tags=["hierarchy"])


def _not_found(resource: str, id_: UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": {
                "code": f"{resource.upper()}_NOT_FOUND",
                "message": f"{resource} {id_} does not exist",
                "details": {f"{resource}_id": str(id_)},
            }
        },
    )


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------


@router.get("/companies", response_model=List[CompanyOut])
def list_companies(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[CompanyOut]:
    """List companies the current user can see (MVP: their own company only)."""
    rows = db.scalars(select(Company).where(Company.id == user.company_id)).all()
    return [CompanyOut.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------


@router.get("/sites", response_model=List[SiteOut])
def list_sites(
    company_id: Optional[UUID] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[SiteOut]:
    """List sites filtered by company. Defaults to the user's company."""
    cid = company_id or user.company_id
    rows = db.scalars(select(Site).where(Site.company_id == cid)).all()
    return [SiteOut.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# Areas
# ---------------------------------------------------------------------------


@router.get("/areas", response_model=List[AreaOut])
def list_areas(
    site_id: Optional[UUID] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[AreaOut]:
    """List areas. ``site_id`` is optional; without it, all areas in the user's company."""
    stmt = select(Area).join(Site, Area.site_id == Site.id).where(Site.company_id == user.company_id)
    if site_id is not None:
        stmt = stmt.where(Area.site_id == site_id)
    rows = db.scalars(stmt).all()
    return [AreaOut.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


@router.get("/assets", response_model=List[AssetOut])
def list_assets(
    area_id: Optional[UUID] = Query(default=None),
    site_id: Optional[UUID] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[AssetOut]:
    """List assets. Filterable by area or site."""
    stmt = (
        select(Asset)
        .join(Area, Asset.area_id == Area.id)
        .join(Site, Area.site_id == Site.id)
        .where(Site.company_id == user.company_id)
    )
    if area_id is not None:
        stmt = stmt.where(Asset.area_id == area_id)
    if site_id is not None:
        stmt = stmt.where(Area.site_id == site_id)
    rows = db.scalars(stmt).all()
    return [AssetOut.model_validate(r) for r in rows]


@router.get("/assets/{asset_id}", response_model=AssetOut)
def get_asset(
    asset_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AssetOut:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise _not_found("asset", asset_id)
    return AssetOut.model_validate(asset)


# ---------------------------------------------------------------------------
# Sensors
# ---------------------------------------------------------------------------


@router.get("/sensors", response_model=List[SensorOut])
def list_sensors(
    asset_id: Optional[UUID] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[SensorOut]:
    """List sensors. Optionally filtered by ``asset_id``."""
    stmt = select(Sensor)
    if asset_id is not None:
        stmt = stmt.where(Sensor.asset_id == asset_id)
    else:
        # Constrain to user's company via asset/area/site joins.
        stmt = (
            stmt.join(Asset, Sensor.asset_id == Asset.id)
            .join(Area, Asset.area_id == Area.id)
            .join(Site, Area.site_id == Site.id)
            .where(Site.company_id == user.company_id)
        )
    rows = db.scalars(stmt).all()
    return [SensorOut.model_validate(r) for r in rows]


@router.get("/assets/{asset_id}/sensors", response_model=List[SensorOut])
def list_asset_sensors(
    asset_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[SensorOut]:
    if db.get(Asset, asset_id) is None:
        raise _not_found("asset", asset_id)
    rows = db.scalars(select(Sensor).where(Sensor.asset_id == asset_id)).all()
    return [SensorOut.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# Manager+ writes (minimal; the seed script does the heavy lifting)
# ---------------------------------------------------------------------------
# TODO(backend): expand POST/PATCH/DELETE handlers per API_CONTRACT.md when
# the frontend needs them. Read endpoints are sufficient for the MVP UI.
_WRITE_GUARD = roles_at_least("manager")


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_asset(
    asset_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(_WRITE_GUARD),
) -> Response:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise _not_found("asset", asset_id)
    db.delete(asset)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
