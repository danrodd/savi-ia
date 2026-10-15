"""Motor de alertas (§5, §8.1): cada regla abre y resuelve según su condición."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.modules.alerts.infrastructure import AlertModel
from app.modules.alerts.runner import run_evaluation
from app.modules.ingest.infrastructure import EvTurnModel
from app.modules.staff.domain import Role
from tests.console_helpers import ConsoleEnv
from tests.test_console_api import API, Fixture, Linked, link_instance, make_client
from tests.test_console_metrics import DB_A, INSTANCE, utc


@pytest.fixture
async def fx(console: ConsoleEnv) -> Fixture:
    admin = await console.onboard("admin@seo.example", Role.ADMIN)
    soporte = await console.onboard("soporte@seo.example", Role.SOPORTE)
    comercial = await console.onboard("comercial@seo.example", Role.COMERCIAL)
    return Fixture(console, admin, soporte, comercial)


def settings_of(fx: Fixture, **overrides: Any) -> Settings:
    base: Settings = fx.console.app.state.settings
    return base.model_copy(update=overrides)


async def evaluate(fx: Fixture, **overrides: Any) -> tuple[int, int, int]:
    result = await run_evaluation(fx.console.maker, settings_of(fx, **overrides), fx.console.clock)
    return result.opened, result.updated, result.resolved


async def alerts(fx: Fixture, *, status: str | None = None) -> list[dict[str, Any]]:
    who = await fx.console.login("admin@seo.example")
    suffix = f"?status={status}" if status else ""
    res = await fx.console.http.get(f"{API}/alerts{suffix}", headers=who.auth)
    assert res.status_code == 200, res.text
    return list(res.json())


def live_codes(rows: list[dict[str, Any]]) -> list[str]:
    return sorted(a["rule_code"] for a in rows if a["status"] != "resolved")


async def beat(fx: Fixture, who: Linked, **extra: Any) -> None:
    body: dict[str, Any] = {
        "sent_at": fx.console.clock.now.isoformat(),
        "fingerprint": "fp-1",
        "version": "v1.1.0",
        "deployment_mode": "server",
    }
    body.update(extra)
    res = await fx.console.http.post("/api/v1/instances/heartbeat", json=body, headers=who.auth)
    assert res.status_code == 200, res.text


async def add_turns(
    fx: Fixture,
    client_id: str,
    *,
    at: str,
    count: int,
    errors: int = 0,
    cost: str = "0.010000",
    prefix: str = "t",
) -> None:
    rows = [
        EvTurnModel(
            instance_id=INSTANCE,
            source_id=f"{prefix}-{at}-{n}",
            client_id=UUID(client_id),
            occurred_at=utc(at),
            conversation_ref=uuid4(),
            database_ref=DB_A,
            user_ref="u1",
            provider="claude",
            model="sonnet",
            finish_reason="error" if n < errors else "complete",
            input_tokens=10,
            output_tokens=10,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
            cost_usd=Decimal(cost),
            tools=[],
            latency_ms=100,
            action="send",
        )
        for n in range(count)
    ]
    async with fx.console.maker() as s, s.begin():
        s.add_all(rows)


async def busy_client(fx: Fixture) -> str:
    """Cliente con un turno hoy: así `no_usage` no se mezcla en las pruebas de otras reglas."""
    client_id = await make_client(fx)
    await add_turns(fx, client_id, at="2026-01-01T10:00:00Z", count=1, prefix="busy")
    return client_id


# ------------------------------------------------------------------ conexión


async def test_offline_escalates_and_auto_resolves(fx: Fixture) -> None:
    client_id = await busy_client(fx)
    linked = await link_instance(fx, client_id)
    await beat(fx, linked)
    assert await evaluate(fx) == (0, 0, 0)

    fx.console.clock.advance(minutes=61)
    assert await evaluate(fx) == (1, 0, 0)
    rows = await alerts(fx)
    assert [(a["rule_code"], a["severity"]) for a in rows] == [("instance_offline", "warning")]
    assert rows[0]["client_name"]  # la lista trae el nombre del cliente

    # Evaluar de nuevo no duplica la alerta abierta.
    assert await evaluate(fx) == (0, 0, 0)
    assert len(await alerts(fx)) == 1

    fx.console.clock.advance(hours=24)
    assert await evaluate(fx) == (0, 1, 0)  # sube a crítica
    assert (await alerts(fx))[0]["severity"] == "critical"

    await beat(fx, linked)  # vuelve a hablar
    assert await evaluate(fx) == (0, 0, 1)
    resolved = (await alerts(fx, status="resolved"))[0]
    assert resolved["resolved_by"] == "sistema"
    assert live_codes(await alerts(fx)) == []


async def test_offline_threshold_is_configurable(fx: Fixture) -> None:
    client_id = await busy_client(fx)
    linked = await link_instance(fx, client_id)
    await beat(fx, linked)
    fx.console.clock.advance(minutes=30)
    assert await evaluate(fx) == (0, 0, 0)

    admin = await fx.console.login("admin@seo.example")
    res = await fx.console.http.patch(
        f"{API}/alert-rules/instance_offline", json={"threshold": 20}, headers=admin.auth
    )
    assert res.status_code == 200
    assert res.json()["threshold"] == 20
    assert await evaluate(fx) == (1, 0, 0)


async def test_suspended_client_instances_do_not_alert(fx: Fixture) -> None:
    client_id = await busy_client(fx)
    linked = await link_instance(fx, client_id)
    await beat(fx, linked)
    fx.console.clock.advance(hours=3)
    assert live_codes(await _after(fx)) == ["instance_offline"]

    admin = await fx.console.login("admin@seo.example")
    await fx.console.http.post(f"{API}/clients/{client_id}/suspend", headers=admin.auth)
    assert (await evaluate(fx))[2] == 1
    assert live_codes(await alerts(fx)) == []


async def _after(fx: Fixture) -> list[dict[str, Any]]:
    await evaluate(fx)
    return await alerts(fx)


async def test_fingerprint_mismatch_opens_and_resolves_on_confirmation(fx: Fixture) -> None:
    linked = await link_instance(fx, await busy_client(fx))
    await beat(fx, linked, fingerprint="otra-maquina")
    rows = await _after(fx)
    assert [(a["rule_code"], a["severity"]) for a in rows] == [
        ("instance_fingerprint_mismatch", "critical")
    ]

    admin = await fx.console.login("admin@seo.example")
    await fx.console.http.post(
        f"{API}/instances/{linked.instance_id}/confirm-fingerprint", headers=admin.auth
    )
    assert (await evaluate(fx))[2] == 1
    assert live_codes(await alerts(fx)) == []


async def test_clock_skew(fx: Fixture) -> None:
    linked = await link_instance(fx, await busy_client(fx))
    skewed = (fx.console.clock.now - timedelta(minutes=10)).isoformat()
    await beat(fx, linked, sent_at=skewed)
    assert live_codes(await _after(fx)) == ["clock_skew"]
    await beat(fx, linked)
    assert (await evaluate(fx))[2] == 1


# ------------------------------------------------------------------ avisos de la instancia


async def test_instance_warnings_and_contract_rejected(fx: Fixture) -> None:
    linked = await link_instance(fx, await busy_client(fx))
    await beat(
        fx,
        linked,
        warnings=["cert_expired", "http_without_tls"],
        sync={"streams": {}, "last_error": "contract_rejected"},
    )
    rows = await _after(fx)
    assert live_codes(rows) == ["contract_rejected", "instance_warning"]
    warning = next(a for a in rows if a["rule_code"] == "instance_warning")
    assert warning["details"]["warnings"] == ["cert_expired"]  # solo los que cuentan

    await beat(fx, linked, warnings=[], sync={"streams": {}, "last_error": None})
    assert (await evaluate(fx))[2] == 2


async def test_sync_stalled_needs_online_instance_with_activity(fx: Fixture) -> None:
    linked = await link_instance(fx, await busy_client(fx))
    old = (fx.console.clock.now - timedelta(hours=7)).isoformat()
    streams = {"turn": {"watermark_at": old, "last_ok_at": old}}

    await beat(fx, linked, active_sessions=0, sync={"streams": streams, "last_error": None})
    assert live_codes(await _after(fx)) == []  # sin actividad no se infiere nada

    await beat(fx, linked, active_sessions=3, sync={"streams": streams, "last_error": None})
    rows = await _after(fx)
    assert live_codes(rows) == ["sync_stalled"]
    assert rows[0]["details"]["streams"] == {"turn": 7}


# ------------------------------------------------------------------ uso y costo


async def test_error_rate_spike_requires_minimum_turns_and_threshold(fx: Fixture) -> None:
    client_id = await make_client(fx)
    await add_turns(fx, client_id, at="2026-01-01T10:00:00Z", count=19, errors=19, prefix="a")
    assert await evaluate(fx) == (0, 0, 0)  # 19 turnos: debajo del mínimo

    await add_turns(fx, client_id, at="2026-01-01T10:01:00Z", count=1, errors=0, prefix="b")
    assert await evaluate(fx) == (1, 0, 0)  # 20 turnos, 95 % de error
    assert live_codes(await alerts(fx)) == ["error_rate_spike"]


async def test_error_rate_below_threshold_does_not_alert(fx: Fixture) -> None:
    client_id = await make_client(fx)
    await add_turns(fx, client_id, at="2026-01-01T10:00:00Z", count=25, errors=3)  # 12 %
    assert await evaluate(fx) == (0, 0, 0)


async def test_cost_spike_is_resolved_manually(fx: Fixture) -> None:
    client_id = await make_client(fx)
    for n in range(1, 15):  # 14 días previos a USD 1
        day = (utc("2026-01-01T10:00:00Z") - timedelta(days=n)).isoformat()
        await add_turns(fx, client_id, at=day, count=1, cost="1.000000", prefix=f"d{n}")
    await add_turns(fx, client_id, at="2026-01-01T10:00:00Z", count=1, cost="10.000000")
    assert await evaluate(fx) == (1, 0, 0)
    rows = await alerts(fx)
    assert rows[0]["rule_code"] == "cost_spike"
    assert rows[0]["details"]["median_14d_usd"] == "1.000000"

    # Pasa un día: la condición ya no se cumple pero esta regla no se auto-resuelve.
    fx.console.clock.advance(days=1)
    assert await evaluate(fx) == (0, 0, 0)
    assert live_codes(await alerts(fx)) == ["cost_spike"]

    admin = await fx.console.login("admin@seo.example")
    res = await fx.console.http.post(
        f"{API}/alerts/{rows[0]['id']}/resolve",
        json={"note": "Campaña puntual"},
        headers=admin.auth,
    )
    assert res.json()["status"] == "resolved"
    assert res.json()["resolved_by"] == "admin@seo.example"
    assert res.json()["resolution_note"] == "Campaña puntual"


async def test_cost_spike_needs_minimum_amount(fx: Fixture) -> None:
    client_id = await make_client(fx)
    await add_turns(fx, client_id, at="2026-01-01T10:00:00Z", count=1, cost="4.000000")
    assert await evaluate(fx) == (0, 0, 0)  # 4 USD: bajo el mínimo de 5


async def test_no_usage_and_outdated(fx: Fixture) -> None:
    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)
    await beat(fx, linked)
    settings = {
        "latest_version": "v1.2.0",
        "latest_version_published_at": fx.console.clock.now - timedelta(days=40),
    }
    assert (await evaluate(fx, **settings))[0] == 2
    assert live_codes(await alerts(fx)) == ["instance_outdated", "no_usage"]

    await add_turns(fx, client_id, at="2026-01-01T11:00:00Z", count=1)
    assert (await evaluate(fx, **settings))[2] == 1  # vuelve a haber uso
    assert live_codes(await alerts(fx)) == ["instance_outdated"]

    # Sin fecha de publicación no se puede saber desde cuándo: la regla no se activa.
    assert (await evaluate(fx, latest_version="v1.2.0"))[2] == 1


# ------------------------------------------------------------------ gestión


async def test_acknowledge_keeps_alert_live_without_duplicating(fx: Fixture) -> None:
    linked = await link_instance(fx, await busy_client(fx))
    await beat(fx, linked, warnings=["cert_expired"])
    alert_id = (await _after(fx))[0]["id"]

    soporte = await fx.console.login("soporte@seo.example")
    ack = await fx.console.http.post(f"{API}/alerts/{alert_id}/ack", headers=soporte.auth)
    assert ack.json()["status"] == "acknowledged"
    assert ack.json()["acknowledged_by"] == "soporte@seo.example"

    assert await evaluate(fx) == (0, 0, 0)  # reconocida sigue viva: no se abre otra
    assert len([a for a in await alerts(fx) if a["status"] != "resolved"]) == 1

    # Al desaparecer la condición se resuelve sola, aun reconocida.
    await beat(fx, linked, warnings=[])
    assert (await evaluate(fx))[2] == 1


async def test_permissions_for_alert_management(fx: Fixture) -> None:
    linked = await link_instance(fx, await busy_client(fx))
    await beat(fx, linked, warnings=["cert_expired"])
    alert_id = (await _after(fx))[0]["id"]

    comercial = await fx.console.login("comercial@seo.example")
    assert (await fx.console.http.get(f"{API}/alerts", headers=comercial.auth)).status_code == 200
    denied = await fx.console.http.post(f"{API}/alerts/{alert_id}/ack", headers=comercial.auth)
    assert denied.status_code == 403

    soporte = await fx.console.login("soporte@seo.example")
    rule = await fx.console.http.patch(
        f"{API}/alert-rules/clock_skew", json={"enabled": False}, headers=soporte.auth
    )
    assert rule.status_code == 403  # configurar reglas es solo de admin


async def test_disabling_a_rule_resolves_its_alerts(fx: Fixture) -> None:
    linked = await link_instance(fx, await busy_client(fx))
    await beat(fx, linked, warnings=["cert_expired"])
    assert live_codes(await _after(fx)) == ["instance_warning"]

    admin = await fx.console.login("admin@seo.example")
    await fx.console.http.patch(
        f"{API}/alert-rules/instance_warning", json={"enabled": False}, headers=admin.auth
    )
    assert (await evaluate(fx))[2] == 1
    resolved = (await alerts(fx, status="resolved"))[0]
    assert "ya no está activa" in resolved["resolution_note"]


async def test_rule_validation(fx: Fixture) -> None:
    admin = await fx.console.login("admin@seo.example")
    unknown = await fx.console.http.patch(
        f"{API}/alert-rules/no_existe", json={"enabled": False}, headers=admin.auth
    )
    assert unknown.status_code == 404
    no_threshold = await fx.console.http.patch(
        f"{API}/alert-rules/contract_rejected", json={"threshold": 5}, headers=admin.auth
    )
    assert no_threshold.status_code == 422
    assert no_threshold.json()["errorCode"] == "invalid_alert_rule"
    negative = await fx.console.http.patch(
        f"{API}/alert-rules/clock_skew", json={"threshold": -1}, headers=admin.auth
    )
    assert negative.status_code == 422

    rules = await fx.console.http.get(f"{API}/alert-rules", headers=admin.auth)
    codes = {r["code"] for r in rules.json()}
    assert {"instance_offline", "cost_spike", "no_usage"} <= codes
    assert len(codes) == 11


async def test_rule_and_alert_changes_are_audited(fx: Fixture) -> None:
    linked = await link_instance(fx, await busy_client(fx))
    await beat(fx, linked, warnings=["cert_expired"])
    alert_id = (await _after(fx))[0]["id"]
    admin = await fx.console.login("admin@seo.example")
    await fx.console.http.post(f"{API}/alerts/{alert_id}/ack", headers=admin.auth)
    await fx.console.http.patch(
        f"{API}/alert-rules/clock_skew", json={"threshold": 600}, headers=admin.auth
    )
    actions = await fx.console.audit_actions()
    assert "alert.acknowledge" in actions
    assert "alert_rule.update" in actions


async def test_overview_counts_open_alerts(fx: Fixture) -> None:
    linked = await link_instance(fx, await busy_client(fx))
    await beat(fx, linked, warnings=["cert_expired"])
    await evaluate(fx)
    admin = await fx.console.login("admin@seo.example")
    body = (await fx.console.http.get(f"{API}/overview", headers=admin.auth)).json()
    assert body["open_alerts"] == {"info": 0, "warning": 0, "critical": 1}


async def test_alert_summary_counts_by_status_and_client(fx: Fixture) -> None:
    client_id = await busy_client(fx)
    linked = await link_instance(fx, client_id)
    await beat(fx, linked, warnings=["cert_expired"])
    await evaluate(fx)
    admin = await fx.console.login("admin@seo.example")

    total = (await fx.console.http.get(f"{API}/alerts/summary", headers=admin.auth)).json()
    assert total == {"open": 1, "acknowledged": 0}
    mine = await fx.console.http.get(
        f"{API}/alerts/summary?client_id={client_id}", headers=admin.auth
    )
    assert mine.json() == {"open": 1, "acknowledged": 0}
    other = await fx.console.http.get(
        f"{API}/alerts/summary?client_id={uuid4()}", headers=admin.auth
    )
    assert other.json() == {"open": 0, "acknowledged": 0}

    alert_id = (await alerts(fx))[0]["id"]
    await fx.console.http.post(f"{API}/alerts/{alert_id}/ack", headers=admin.auth)
    after = (await fx.console.http.get(f"{API}/alerts/summary", headers=admin.auth)).json()
    assert after == {"open": 0, "acknowledged": 1}


async def test_client_counts_people_and_open_alerts(fx: Fixture) -> None:
    client_id = await busy_client(fx)  # un turno de "u1"
    linked = await link_instance(fx, client_id)
    await beat(fx, linked, warnings=["cert_expired"])
    await evaluate(fx)
    admin = await fx.console.login("admin@seo.example")

    res = await fx.console.http.get(f"{API}/clients/{client_id}/counts", headers=admin.auth)
    assert res.status_code == 200, res.text
    assert res.json() == {"people": 1, "open_alerts": 1}

    missing = await fx.console.http.get(f"{API}/clients/{uuid4()}/counts", headers=admin.auth)
    assert missing.status_code == 404


async def test_database_blocks_duplicate_live_alerts(fx: Fixture) -> None:
    """La unicidad de alertas vivas la garantiza la base, no solo el motor."""
    from datetime import UTC, datetime

    def row() -> AlertModel:
        return AlertModel(
            id=uuid4(),
            rule_code="instance_offline",
            severity="warning",
            client_id=UUID(int=1),
            instance_id=None,
            status="open",
            dedup_key="instance_offline:x:-",
            details={},
            opened_at=datetime.now(UTC),
        )

    async with fx.console.maker() as s, s.begin():
        s.add(row())
    with pytest.raises(IntegrityError):
        async with fx.console.maker() as s, s.begin():
            s.add(row())


# ------------------------------------------------------------------ acciones masivas


async def two_open_alerts(fx: Fixture) -> list[str]:
    linked = await link_instance(fx, await busy_client(fx))
    await beat(
        fx,
        linked,
        warnings=["cert_expired"],
        sync={"streams": {}, "last_error": "contract_rejected"},
    )
    rows = await _after(fx)
    assert len(rows) == 2
    return [a["id"] for a in rows]


async def test_bulk_acknowledge_changes_open_ones_and_audits_each(fx: Fixture) -> None:
    ids = await two_open_alerts(fx)
    soporte = await fx.console.login("soporte@seo.example")
    res = await fx.console.http.post(
        f"{API}/alerts/bulk/ack",
        json={"ids": [*ids, ids[0], str(uuid4())]},  # un duplicado y uno inexistente
        headers=soporte.auth,
    )
    assert res.status_code == 200, res.text
    assert res.json() == {"changed": 2, "skipped": 1}
    assert {a["status"] for a in await alerts(fx)} == {"acknowledged"}
    actions = await fx.console.audit_actions()
    assert actions.count("alert.acknowledge") == 2

    # Repetir no cambia nada: ya están reconocidas.
    again = await fx.console.http.post(
        f"{API}/alerts/bulk/ack", json={"ids": ids}, headers=soporte.auth
    )
    assert again.json() == {"changed": 0, "skipped": 2}
    assert (await fx.console.audit_actions()).count("alert.acknowledge") == 2


async def test_bulk_resolve_applies_note_and_skips_resolved(fx: Fixture) -> None:
    ids = await two_open_alerts(fx)
    admin = await fx.console.login("admin@seo.example")
    single = await fx.console.http.post(
        f"{API}/alerts/{ids[0]}/resolve", json={"note": ""}, headers=admin.auth
    )
    assert single.status_code == 200

    res = await fx.console.http.post(
        f"{API}/alerts/bulk/resolve",
        json={"ids": ids, "note": "  Revisado en bloque  "},
        headers=admin.auth,
    )
    assert res.json() == {"changed": 1, "skipped": 1}
    resolved = {a["id"]: a for a in await alerts(fx, status="resolved")}
    assert resolved[ids[1]]["resolution_note"] == "Revisado en bloque"
    assert resolved[ids[1]]["resolved_by"] == "admin@seo.example"
    assert resolved[ids[0]]["resolution_note"] is None  # no se pisa la ya resuelta
    assert (await fx.console.audit_actions()).count("alert.resolve") == 2


async def test_bulk_validation_and_permissions(fx: Fixture) -> None:
    ids = await two_open_alerts(fx)
    admin = await fx.console.login("admin@seo.example")
    empty = await fx.console.http.post(
        f"{API}/alerts/bulk/ack", json={"ids": []}, headers=admin.auth
    )
    assert empty.status_code == 422
    too_many = await fx.console.http.post(
        f"{API}/alerts/bulk/ack",
        json={"ids": [str(uuid4()) for _ in range(201)]},
        headers=admin.auth,
    )
    assert too_many.status_code == 422
    long_note = await fx.console.http.post(
        f"{API}/alerts/bulk/resolve", json={"ids": ids, "note": "x" * 501}, headers=admin.auth
    )
    assert long_note.status_code == 422
    assert {a["status"] for a in await alerts(fx)} == {"open"}  # nada cambió

    comercial = await fx.console.login("comercial@seo.example")
    for path in ("ack", "resolve"):
        denied = await fx.console.http.post(
            f"{API}/alerts/bulk/{path}", json={"ids": ids}, headers=comercial.auth
        )
        assert denied.status_code == 403
