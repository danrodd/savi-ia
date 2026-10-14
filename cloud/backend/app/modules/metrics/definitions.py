"""Definiciones únicas de las métricas (§4.1 de la Fase 3).

Es **la** fuente de verdad: las consultas las implementan, los tests las verifican con
valores escritos a mano y la consola muestra estos textos en el tooltip de cada métrica.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    label: str
    definition: str
    source: str


METRICS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        "turns",
        "Turnos",
        "Cantidad de respuestas del asistente, incluidas las reemplazadas al editar o regenerar.",
        "ev_turns",
    ),
    MetricDefinition(
        "conversations",
        "Conversaciones",
        "Conversaciones creadas en el período.",
        "ev_conversations",
    ),
    MetricDefinition(
        "active_users",
        "Usuarios activos",
        "Usuarios distintos con al menos un turno en el período. Se cuentan por seudónimo: "
        "Cloud no sabe quiénes son.",
        "ev_turns",
    ),
    MetricDefinition(
        "dau",
        "Usuarios activos por día",
        "Usuarios activos en un día calendario (zona America/Bogota).",
        "ev_turns",
    ),
    MetricDefinition(
        "mau",
        "Usuarios activos del mes",
        "Usuarios activos en los últimos 30 días móviles.",
        "ev_turns",
    ),
    MetricDefinition(
        "entering_users",
        "Usuarios que entran",
        "Usuarios distintos con al menos un inicio de sesión en el período, tengan o no turnos.",
        "ev_sessions",
    ),
    MetricDefinition(
        "adoption",
        "Adopción",
        "Usuarios activos dividido por usuarios que entran.",
        "derivada",
    ),
    MetricDefinition(
        "tokens",
        "Tokens",
        "Suma de entrada, salida, caché leída y caché creada.",
        "ev_turns",
    ),
    MetricDefinition(
        "cost_usd",
        "Costo (USD)",
        "Suma del costo informado por cada turno. Los turnos sin precio no se estiman: "
        "se cuentan aparte como «sin precio».",
        "ev_turns",
    ),
    MetricDefinition(
        "cost_per_active_user",
        "Costo por usuario activo",
        "Costo dividido por usuarios activos.",
        "derivada",
    ),
    MetricDefinition(
        "turns_with_error",
        "Turnos con error",
        "Turnos que terminaron en error. «Interrumpido» (lo cortó la persona) y «truncado» "
        "(alcanzó el tope de caracteres) se muestran aparte y no son errores del sistema.",
        "ev_turns",
    ),
    MetricDefinition(
        "error_rate",
        "Tasa de error",
        "Turnos con error dividido por turnos.",
        "derivada",
    ),
    MetricDefinition(
        "latency",
        "Latencia p50 / p90",
        "Percentiles del tiempo de respuesta, sin contar turnos sin dato.",
        "ev_turns",
    ),
    MetricDefinition(
        "tools",
        "Uso de herramientas",
        "Cantidad de usos por herramienta y, en conocimiento, por tipo; con la tasa de error.",
        "ev_turns",
    ),
    MetricDefinition(
        "free_queries_failed",
        "Consultas libres fallidas",
        "Consultas libres con resultado distinto de éxito dividido por el total.",
        "ev_free_queries",
    ),
    MetricDefinition(
        "online",
        "Instancia en línea",
        "Habló con Cloud hace menos de 15 minutos.",
        "instances",
    ),
    MetricDefinition(
        "outdated",
        "Instancia desactualizada",
        "Su versión es menor que la última publicada.",
        "instances",
    ),
    MetricDefinition(
        "freshness",
        "Frescura de datos",
        "Lo más atrasado entre el último contacto de la instancia y la marca más vieja de sus "
        "envíos. Una instancia sin conexión hace parecer que el uso cayó: no es pérdida del "
        "cliente.",
        "last_heartbeat.sync",
    ),
)

ERROR_FINISH_REASON = "error"
INTERRUPTED_FINISH_REASON = "interrupted"
TRUNCATED_FINISH_REASON = "truncated"
FREE_QUERY_SUCCESS = "ok"
