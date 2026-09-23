"""El prompt de sistema le dice al modelo qué día es.

Sin eso, "¿cuánto vendimos este mes?" dependía de lo que el modelo
supusiera: gpt-6-luna consultó marzo de 2025 un 23 de septiembre de 2026.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.modules.chat.infrastructure.llm.system_prompt import (
    SYSTEM_PROMPT,
    build_system_prompt,
    today_in,
)


def test_prompt_states_today_in_words_and_iso() -> None:
    prompt = build_system_prompt(date(2026, 9, 23))

    assert "miércoles 23 de septiembre de 2026" in prompt
    assert "2026-09-23" in prompt


def test_the_static_prompt_stays_a_prefix() -> None:
    """La fecha va al final: el resto sigue siendo un prefijo estable para
    el caché del proveedor."""
    assert build_system_prompt(date(2026, 9, 23)).startswith(SYSTEM_PROMPT)


def test_today_uses_the_reporting_timezone_not_utc() -> None:
    """A las 20:00 de Bogotá (UTC-5) en UTC ya es el día siguiente."""
    ocho_de_la_noche_en_bogota = datetime(2026, 9, 24, 1, 0, tzinfo=UTC)

    assert today_in("America/Bogota", ocho_de_la_noche_en_bogota) == date(2026, 9, 23)
