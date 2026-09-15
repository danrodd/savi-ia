# Fase 4 — Deuda técnica, costos visibles y UX

> Objetivo: cerrar lo que no es urgente pero desgasta: costos que no se ven,
> código duplicado, interfaz incompleta y detalles de seguridad menores.
> Esfuerzo estimado: **4-5 días**, troceable. Ninguna tarea bloquea a otra.

## Alcance

| # | Hallazgo | Severidad |
|---|---|---|
| M6 | Costo invisible cuando falta la tarifa | Media |
| M8 | Interfaz de documentos incompleta | Media |
| M9 | Tres runners con el mismo bucle agéntico | Media |
| O5 | Ingesta en serie, sin avance visible | Media |
| O7 | El reuso de un refresh token no invalida la cadena | Baja |
| B1–B7 | Bajas varias | Baja |

---

## M6 — Que el costo sin tarifa se note

**Qué está mal.** `compute_cost_usd` devuelve `None` si el modelo no tiene
tarifa cargada, se guarda `NULL` y la pantalla de consumo lo suma como 0.
Medido: las 11 respuestas con Gemini registran USD 0,00.

**Cambios**

- Backend: los reportes de consumo devuelven, además del total, `respuestas_sin_tarifa` por proveedor y modelo.
- Frontend (`AdminUsageView`): si hay respuestas sin tarifa, mostrar un aviso —"12 respuestas de `gemini-2.5-flash` sin tarifa cargada: el costo real es mayor"— con enlace a la pantalla de proveedores.
- Al activar un proveedor cuyo modelo de chat no tiene precio, avisar en el momento.

**Criterios de aceptación**

- [ ] El consumo distingue "sin tarifa" de "costo cero".
- [ ] Activar un proveedor sin tarifa muestra el aviso.
- [ ] Con todas las tarifas cargadas, la pantalla se ve igual que hoy.

**Tests:** `test_usage_reports_untariffed_responses`, más un test de la vista.

---

## M8 — Interfaz de documentos

Ya está priorizada en
[`revision-interfaz.md`](../../backend/docs/company_knowledge/revision-interfaz.md),
con 12 hallazgos. El orden acordado:

| Prioridad | Qué | Nota |
|---|---|---|
| 1 | Avance del procesamiento y posición en cola | Necesita que el backend guarde el avance; se hace junto con O5 |
| 2 | Acciones visibles en móvil (tarjetas o menú "⋯") | |
| 3 | Soltar un archivo fuera de la zona no debe abrirlo en el navegador | Bug real |
| 4 | Buscador y filtro por estado | |
| 5 | Menú por fila en lugar de tres botones | |
| 6 | Mostrar el pasaje que coincidió, no el inicio del fragmento | |
| 7 | Páginas precisas en documentos de páginas cortas | Toca el fragmentador |
| 8-12 | Pulido | |

**Criterio de aceptación de la fase:** cerrados 1 a 5, con Vitest y E2E en verde.

---

## M9 — Un solo bucle agéntico

**Qué está mal.** `openai/runner.py` (366 líneas) y `gemini/runner.py` (313)
reimplementan el mismo ciclo: pedir al modelo, ejecutar herramientas, devolver
resultados, repetir hasta `max_agent_turns`, con truncado y cálculo de costo
duplicados. Cada cambio de comportamiento se hace tres veces y se olvida una.

**Cambios**

Extraer a `chat/infrastructure/llm/agent_loop.py` un bucle que reciba un
adaptador por proveedor:

```python
class ProviderAdapter(Protocol):
    async def request(self, messages, tools) -> ProviderResponse: ...
    def to_tool_calls(self, response) -> list[ToolCall]: ...
    def to_events(self, response) -> Iterable[ChatEvent]: ...
    def usage_of(self, response) -> TokenUsage: ...
```

El bucle queda con el control de turnos, el truncado, el costo y los eventos.
Cada runner se reduce a traducir formatos.

**Claude queda afuera**: su bucle lo maneja el Agent SDK, no SAVI.

**Criterios de aceptación**

- [ ] `openai/runner.py` y `gemini/runner.py` bajan a menos de la mitad.
- [ ] Todos los tests existentes de ambos siguen en verde **sin cambios** (es refactor, no cambio de comportamiento).
- [ ] Un turno real con cada proveedor produce los mismos eventos que antes.

---

## O5 — Ingesta: avance y cola

**Qué está mal.** Un solo worker en serie: un PDF de 500 páginas (~1 min 45 s)
bloquea la cola de todos. La interfaz solo muestra "Procesando…".

**Cambios**

1. **Avance persistido**: `company_documents` guarda `chunks_procesados` y `chunks_totales`; el pipeline los actualiza por lote de 32. Migración Alembic.
2. **Posición en cola**: el listado devuelve cuántos documentos hay por delante.
3. **Frontend**: barra de avance y "En cola (2 antes)". Es el punto 1 de M8.
4. **Más de un worker**: solo si SAVI Servidor lo necesita. En escritorio, un worker está bien y dos compiten por la misma CPU que usa el chat.

**Criterios de aceptación**

- [ ] Durante el procesamiento de un PDF grande, la interfaz muestra un porcentaje que avanza.
- [ ] Un documento en cola muestra cuántos tiene delante.
- [ ] El avance no agrega más de un `UPDATE` por lote de 32 fragmentos.

**Tests:** `test_pipeline_reports_progress`, más el componente en Vitest.

---

## O7 — Reuso de refresh token

**Qué está mal.** La rotación funciona (se revoca el `jti` viejo y se emite
uno nuevo). Pero si llega un refresh **ya revocado** —el caso típico de token
robado y reusado— simplemente falla, sin invalidar la cadena ni dejar rastro.

**Cambios**

En `RefreshTokensUseCase`, cuando el registro existe y está revocado:

```python
if record.is_revoked:
    # Un refresh revocado que vuelve es la firma de un token robado: el
    # legítimo ya rotó. Se corta toda la cadena del usuario y que vuelva
    # a iniciar sesión, en lugar de dejar al atacante reintentando.
    await self._refresh_tokens.revoke_all_for_user(record.user_id, record.erp_database_id, when=now)
    log.warning("refresh_token_reuse_detected user_id=%s", record.user_id)
    raise InvalidTokenError(...)
```

`revoke_all_for_user` ya existe en el repositorio.

**Criterios de aceptación**

- [ ] Reusar un refresh revocado invalida todos los refresh vivos de ese usuario en esa base.
- [ ] Queda un warning en el log.
- [ ] Un refresh normal no se ve afectado.

**Test:** `test_refresh_reuse_revokes_all_user_tokens`.

---

## Bajas

| # | Qué | Cambio |
|---|---|---|
| B1 | Refresh token en `localStorage` | Evaluar cookie `HttpOnly` + `SameSite=Strict` para el refresh, dejando solo el access en memoria. Cambia el flujo del frontend: medir el costo antes de decidir. |
| B2 | `xlsx 0.18.5` con CVE sin parche | Hoy no explotable (solo se escribe). Migrar a la distribución oficial de SheetJS o a `exceljs` si alguna vez se leen archivos. |
| B3 | Sin Content-Security-Policy | Middleware con CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` y `Referrer-Policy`. Ajustar la CSP para el `blob:` que usan las descargas. |
| B4 | El historial carga todos los mensajes por turno | `list_messages` con `limit` y orden descendente, invertido en memoria. Se usan los últimos 20. |
| B5 | `launcher.py` con 1.145 líneas | Partir por responsabilidad: bandeja, splash, arranque del servidor, chequeos. |
| B6 | `sql_validator.py` en `# pyright: basic` | Ya se corrige en la Fase 1. |
| B7 | UX: sin buscador de conversaciones, "Nueva conversación" vacías acumuladas, consumo por `#id` | Buscador en la barra lateral; no crear la conversación hasta el primer mensaje; mostrar el nombre del usuario en consumo. |

---

## Resultado de la fase

- El costo que se muestra es el costo real, o dice que no lo sabe.
- La interfaz de documentos deja de sentirse a medio terminar.
- Un cambio en el bucle del agente se hace una vez, no tres.
- Un token robado deja de servir apenas se intenta reusar.
