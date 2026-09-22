"""Resolución del período de consumo — el corte de día en zona local.

"Hoy" y "Ayer" (los presets que se necesitan para cuadrar contra el
crédito cargado en un proveedor) tienen que cortar el día calendario de
`reporting_timezone`, no instantes UTC crudos: un turno de las 11pm de
Bogotá cae en UTC del día siguiente.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.modules.usage.infrastructure.http.routes import _period_from_dates, _resolve_period
from app.shared.exceptions import ValidationError

_TZ = "America/Bogota"  # UTC-5 fijo, sin horario de verano.


def test_today_covers_the_local_calendar_day() -> None:
    period = _period_from_dates(date(2026, 9, 21), date(2026, 9, 21), _TZ)

    # Bogotá 00:00 = UTC 05:00 del mismo día.
    assert period.start == datetime(2026, 9, 21, 5, 0, tzinfo=UTC)
    # Fin exclusivo: arranque del día siguiente en Bogotá.
    assert period.end == datetime(2026, 9, 22, 5, 0, tzinfo=UTC)


def test_yesterday_and_today_spans_two_calendar_days() -> None:
    period = _period_from_dates(date(2026, 9, 20), date(2026, 9, 21), _TZ)

    assert period.start == datetime(2026, 9, 20, 5, 0, tzinfo=UTC)
    assert period.end == datetime(2026, 9, 22, 5, 0, tzinfo=UTC)


def test_a_late_night_turn_belongs_to_its_local_day() -> None:
    """Un turno a las 11pm de Bogotá del 20/09 es 04:00 UTC del 21/09 —
    tiene que caer DENTRO del rango de "20 de septiembre", no afuera."""
    period = _period_from_dates(date(2026, 9, 20), date(2026, 9, 20), _TZ)
    turno_utc = datetime(2026, 9, 21, 4, 0, tzinfo=UTC)  # 11pm Bogotá del 20

    assert period.start <= turno_utc < period.end


def test_resolve_period_prefers_dates_over_instants_when_both_given() -> None:
    period = _resolve_period(
        datetime(2020, 1, 1, tzinfo=UTC),
        datetime(2020, 1, 2, tzinfo=UTC),
        date(2026, 9, 21),
        date(2026, 9, 21),
        reporting_timezone=_TZ,
    )
    assert period.start == datetime(2026, 9, 21, 5, 0, tzinfo=UTC)


def test_resolve_period_requires_from_and_to_together() -> None:
    with pytest.raises(ValidationError):
        _resolve_period(None, None, date(2026, 9, 21), None, reporting_timezone=_TZ)


def test_resolve_period_falls_back_to_default_window() -> None:
    period = _resolve_period(None, None, None, None, reporting_timezone=_TZ)
    assert (period.end - period.start).days == 30
