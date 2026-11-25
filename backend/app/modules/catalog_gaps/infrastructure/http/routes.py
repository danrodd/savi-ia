"""Vacíos del catálogo para el administrador de la empresa.

Mismo guard que Turnos fallidos: administrador de la empresa, acotado a la base
con la que inició sesión. Las preguntas no salen de la instalación.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from app.infrastructure.config import Settings, get_settings
from app.infrastructure.database.session import AgentSessionDep
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http.admin import require_company_admin
from app.modules.catalog_gaps.application.csv_export import build_gaps_csv
from app.modules.catalog_gaps.application.use_cases import GetCatalogGapsUseCase
from app.modules.catalog_gaps.domain.value_objects import CatalogGapReport, GapKind
from app.modules.catalog_gaps.infrastructure.sqlalchemy_gap_reader import (
    SqlAlchemyGapEventReader,
)
from app.shared.exceptions import ValidationError

router = APIRouter(prefix="/admin/catalog-gaps", tags=["catalog-gaps-admin"])

CompanyAdminDep = Annotated[AuthenticatedUser, Depends(require_company_admin)]


def _settings() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(_settings)]

DEFAULT_DAYS = 30
MAX_DAYS = 366


class CatalogGapResponse(BaseModel):
    question: str
    kinds: list[GapKind]
    times: int
    last_at: datetime
    tables: list[str]
    conversation_id: UUID


class TableCountResponse(BaseModel):
    table: str
    times: int


class CatalogGapReportResponse(BaseModel):
    start: datetime
    end: datetime
    totals: dict[GapKind, int]
    gaps: list[CatalogGapResponse]
    top_tables: list[TableCountResponse]

    @classmethod
    def from_report(cls, report: CatalogGapReport) -> CatalogGapReportResponse:
        return cls(
            start=report.start,
            end=report.end,
            totals=report.totals,
            gaps=[
                CatalogGapResponse(
                    question=g.question,
                    kinds=list(g.kinds),
                    times=g.times,
                    last_at=g.last_at,
                    tables=list(g.tables),
                    conversation_id=g.conversation_id,
                )
                for g in report.gaps
            ],
            top_tables=[
                TableCountResponse(table=t.table, times=t.times) for t in report.top_tables
            ],
        )


def get_use_case(session: AgentSessionDep, settings: SettingsDep) -> GetCatalogGapsUseCase:
    return GetCatalogGapsUseCase(
        SqlAlchemyGapEventReader(session), query_limit=settings.erp_queries_per_turn
    )


UseCaseDep = Annotated[GetCatalogGapsUseCase, Depends(get_use_case)]

_FROM = Query(default=None, alias="from", description="Desde (AAAA-MM-DD, inclusive).")
_TO = Query(default=None, alias="to", description="Hasta (AAAA-MM-DD, inclusive).")


def period(
    tz_name: str, from_date: date | None, to_date: date | None, today: date | None = None
) -> tuple[datetime, datetime]:
    """Días calendario de la zona de reporte, ambos inclusivos. Sin fechas, los
    últimos 30 días."""
    tz = ZoneInfo(tz_name)
    last = to_date or today or datetime.now(tz).date()
    first = from_date or (last - timedelta(days=DEFAULT_DAYS - 1))
    if last < first:
        raise ValidationError("'to' no puede ser anterior a 'from'.")
    if (last - first).days >= MAX_DAYS:
        raise ValidationError(f"El periodo no puede pasar de {MAX_DAYS} días.")
    start = datetime.combine(first, time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(last + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    return start, end


def _owner(user: AuthenticatedUser) -> UUID:
    assert user.erp_database_id is not None  # noqa: S101 — el token no decodifica sin base
    return user.erp_database_id


@router.get("", response_model=CatalogGapReportResponse)
async def catalog_gaps(
    user: CompanyAdminDep,
    use_case: UseCaseDep,
    settings: SettingsDep,
    from_date: date | None = _FROM,
    to_date: date | None = _TO,
) -> CatalogGapReportResponse:
    """Preguntas que el catálogo no cubrió, agrupadas, más las tablas más pedidas."""
    start, end = period(settings.reporting_timezone, from_date, to_date)
    report = await use_case.execute(_owner(user), start, end)
    return CatalogGapReportResponse.from_report(report)


@router.get("/export.csv")
async def export_catalog_gaps(
    user: CompanyAdminDep,
    use_case: UseCaseDep,
    settings: SettingsDep,
    from_date: date | None = _FROM,
    to_date: date | None = _TO,
) -> Response:
    """El mismo reporte en CSV para Excel."""
    start, end = period(settings.reporting_timezone, from_date, to_date)
    report = await use_case.execute(_owner(user), start, end)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return Response(
        content=build_gaps_csv(report),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="vacios-catalogo-{stamp}.csv"'},
    )
