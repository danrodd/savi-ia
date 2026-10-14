"""Panel del administrador: feedback del piloto, resumen y export CSV.

Guard: administrador de la EMPRESA (igual que el resto de `/admin`). Todo se
acota a la base con la que inició sesión quien administra.
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Response

from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http.admin import require_unlocked_company_admin
from app.modules.feedback.application.csv_export import build_feedback_csv
from app.modules.feedback.application.responses import (
    AdminFeedbackPageResponse,
    FeedbackSummaryResponse,
)
from app.modules.feedback.domain.value_objects import (
    FeedbackFilters,
    FeedbackRating,
    FeedbackReason,
)
from app.modules.feedback.infrastructure.http.dependencies import (
    ExportFeedbackUseCaseDep,
    GetFeedbackSummaryUseCaseDep,
    ListFeedbackUseCaseDep,
    SettingsDep,
)
from app.shared.exceptions import ValidationError

router = APIRouter(prefix="/admin/feedback", tags=["feedback-admin"])

CompanyAdminDep = Annotated[AuthenticatedUser, Depends(require_unlocked_company_admin)]

_LIMIT_DEFAULT = 25
_LIMIT_MAX = 200


def _admin_database(user: AuthenticatedUser) -> UUID:
    assert user.erp_database_id is not None  # noqa: S101 — el token no decodifica sin base
    return user.erp_database_id


def _filters(
    settings_tz: str,
    *,
    rating: FeedbackRating | None,
    reason: FeedbackReason | None,
    from_date: date | None,
    to_date: date | None,
    provider: str | None,
    model: str | None,
    user: str | None,
    text: str | None,
) -> FeedbackFilters:
    """Arma los filtros. `from`/`to` son días calendario de la zona de reporte,
    ambos inclusivos (el fin real es el arranque del día siguiente)."""
    tz = ZoneInfo(settings_tz)
    if from_date is not None and to_date is not None and to_date < from_date:
        raise ValidationError("'to' no puede ser anterior a 'from'.")
    start = (
        datetime.combine(from_date, time.min, tzinfo=tz).astimezone(UTC)
        if from_date is not None
        else None
    )
    end = (
        datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
        if to_date is not None
        else None
    )
    return FeedbackFilters(
        rating=rating,
        reason=reason,
        start=start,
        end=end,
        provider=(provider or "").strip() or None,
        model=(model or "").strip() or None,
        user=(user or "").strip() or None,
        text=(text or "").strip() or None,
    )


_RATING = Query(default=None, description="Calificación: up | down.")
_REASON = Query(default=None, description="Motivo (solo existe con 👎).")
_FROM = Query(default=None, alias="from", description="Desde (AAAA-MM-DD, inclusive).")
_TO = Query(default=None, alias="to", description="Hasta (AAAA-MM-DD, inclusive).")
_PROVIDER = Query(default=None, description="Proveedor del modelo.")
_MODEL = Query(default=None, description="Modelo.")
_USER = Query(default=None, description="Código de usuario (contiene).")
_TEXT = Query(default=None, alias="q", description="Texto dentro del comentario.")


@router.get("", response_model=AdminFeedbackPageResponse)
async def list_feedback(
    use_case: ListFeedbackUseCaseDep,
    admin: CompanyAdminDep,
    settings: SettingsDep,
    rating: FeedbackRating | None = _RATING,
    reason: FeedbackReason | None = _REASON,
    from_date: date | None = _FROM,
    to_date: date | None = _TO,
    provider: str | None = _PROVIDER,
    model: str | None = _MODEL,
    user: str | None = _USER,
    text: str | None = _TEXT,
    limit: int = Query(default=_LIMIT_DEFAULT, ge=1, le=_LIMIT_MAX),
    offset: int = Query(default=0, ge=0),
) -> AdminFeedbackPageResponse:
    """Calificaciones con su pregunta y respuesta, más recientes primero."""
    filters = _filters(
        settings.reporting_timezone,
        rating=rating,
        reason=reason,
        from_date=from_date,
        to_date=to_date,
        provider=provider,
        model=model,
        user=user,
        text=text,
    )
    page = await use_case.execute(
        owner_erp_database_id=_admin_database(admin), filters=filters, limit=limit, offset=offset
    )
    return AdminFeedbackPageResponse.from_vo(page)


@router.get("/summary", response_model=FeedbackSummaryResponse)
async def feedback_summary(
    use_case: GetFeedbackSummaryUseCaseDep,
    admin: CompanyAdminDep,
    settings: SettingsDep,
    rating: FeedbackRating | None = _RATING,
    reason: FeedbackReason | None = _REASON,
    from_date: date | None = _FROM,
    to_date: date | None = _TO,
    provider: str | None = _PROVIDER,
    model: str | None = _MODEL,
    user: str | None = _USER,
    text: str | None = _TEXT,
) -> FeedbackSummaryResponse:
    """Conteos por día, % de positivas, motivos principales y por modelo."""
    filters = _filters(
        settings.reporting_timezone,
        rating=rating,
        reason=reason,
        from_date=from_date,
        to_date=to_date,
        provider=provider,
        model=model,
        user=user,
        text=text,
    )
    summary = await use_case.execute(owner_erp_database_id=_admin_database(admin), filters=filters)
    return FeedbackSummaryResponse.from_vo(summary)


@router.get("/export.csv")
async def export_feedback_csv(
    use_case: ExportFeedbackUseCaseDep,
    admin: CompanyAdminDep,
    settings: SettingsDep,
    rating: FeedbackRating | None = _RATING,
    reason: FeedbackReason | None = _REASON,
    from_date: date | None = _FROM,
    to_date: date | None = _TO,
    provider: str | None = _PROVIDER,
    model: str | None = _MODEL,
    user: str | None = _USER,
    text: str | None = _TEXT,
) -> Response:
    """CSV (UTF-8 con BOM, separador `;`) con los mismos filtros del listado."""
    filters = _filters(
        settings.reporting_timezone,
        rating=rating,
        reason=reason,
        from_date=from_date,
        to_date=to_date,
        provider=provider,
        model=model,
        user=user,
        text=text,
    )
    items = await use_case.execute(owner_erp_database_id=_admin_database(admin), filters=filters)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return Response(
        content=build_feedback_csv(items),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="feedback-piloto-{stamp}.csv"'},
    )
