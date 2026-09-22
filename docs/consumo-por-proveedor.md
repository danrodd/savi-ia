# Consumo por proveedor — análisis y diseño

> Rediseño de las vistas de consumo ("Mi consumo" del usuario y "Consumo
> global" del admin) para poder responder: **cuánto gastó cada proveedor, con
> qué modelo, en qué período**.
>
> Estado: **implementado** (Fases 1 a 4, 2026-09-21/22). La Fase 0 (cargar
> tarifas) es una acción manual por instalación, no código — repetirla en
> cada instancia nueva antes de medir consumo real.

---

## 1. Por qué

Con un solo proveedor, un costo total alcanzaba. Con tres, las preguntas que
hay que poder responder son otras:

- ¿Cuánto consumió cada proveedor, y cuánto sobre el total?
- ¿Con qué modelo dentro de cada proveedor?
- ¿Cuánto gastamos **hoy**, o **ayer y hoy**, para cuadrar contra el crédito
  cargado en cada plataforma?
- ¿Qué pasó en ese día que se disparó el costo?

Hoy "Mi consumo" muestra costo total, tokens y una lista de barras por día. No
menciona proveedor ni modelo en ningún lado.

---

## 2. Lo que ya existe (y funciona)

El backend está mucho más cerca de lo necesario de lo que la UI sugiere.

| Pieza | Estado |
|---|---|
| `UsageFilters(provider, model)` | **Ya existe**, y los 8 métodos del repositorio lo aceptan |
| Filtrado en SQL por proveedor y modelo | **Ya implementado** (`MessageModel.provider == …`) |
| `start` / `end` arbitrarios en los 4 endpoints | **Ya soportado** (ISO 8601) |
| Grano del dato | `messages` guarda por turno `provider`, `model`, `cost_usd` y los tokens en `usage` (JSONB) |
| Turnos sin tarifa | `UsageTotals.untariffed_count` ya los cuenta aparte |
| Agrupación diaria en zona local | Ya usa `reporting_timezone` (`America/Bogota`) |
| ECharts | Ya integrado (`UsageChart`: bar, line, pie, tooltip, legend, markLine) |

**Consecuencia importante**: el rango de fechas libre **ya lo acepta la API**.
La limitación a 7/30/90 días es puramente del frontend (`UsageRangeSelector`,
y el store que deriva `start`/`end` de `rangeDays`).

---

## 3. Huecos detectados

1. **No existe ningún agregado por proveedor.** Hay `per_user`,
   `per_conversation` y `daily_*`, pero nada que responda "cuánto gastó cada
   proveedor". Es la única pieza de datos que falta de verdad.
2. **La serie diaria no tiene desglose.** `DailyUsage` es un total por día: sin
   cambiar eso no hay barra apilada por proveedor, que es lo que permite *ver
   qué pasó* en un pico.
3. **`UsageFilters` es de valor único** → no hay selección múltiple.
4. **No hay índice que sirva a estas consultas.** `messages` solo tiene
   `ix_messages_conversation_created` y `ix_messages_superseded_by`, y todo el
   módulo filtra por `role='assistant'` + rango de `created_at`.
5. **Nada expone qué proveedores tuvieron consumo** en el período: por eso
   `AdminUsageView` hardcodea los tres en un `<select>`.
6. **Faltan los presets "Hoy" y "Ayer"**, que son los que se necesitan para
   cuadrar contra el crédito de una corrida de pruebas.

---

## 4. El problema de la conciliación (leer antes de diseñar pantallas)

Objetivo declarado: que cada proveedor sume lo que realmente se gastó de su
crédito, y el total la suma de los tres.

**Hoy eso no puede cuadrar**, porque el costo llega por dos caminos distintos:

| Proveedor | Origen de `cost_usd` | ¿Concilia? |
|---|---|---|
| Claude | `ResultMessage.total_cost_usd` del SDK — la cifra real de Anthropic | Sí |
| Gemini | `compute_cost_usd(usage, pricing.get(modelo))` | Solo si hay tarifa cargada |
| OpenAI | Igual que Gemini | Solo si hay tarifa cargada |

Con la tabla de precios vacía, `pricing.get(modelo)` devuelve `None`,
`compute_cost_usd` devuelve `None`, y **el turno se guarda con `cost_usd` en
NULL**: la pantalla muestra 0 aunque el crédito se haya consumido. El único
rastro es `untariffed_count`.

Dos consecuencias de diseño, no negociables:

- **La tarifa se carga ANTES de gastar crédito.** El costo se calcula al
  escribir el turno, no al leerlo.
- **La pantalla dice de dónde sale cada número.** Se reutiliza el flag
  `reports_cost` del descriptor de proveedores: *"informado por el proveedor"*
  (Claude) contra *"estimado con tu tabla de precios"* (Gemini, OpenAI). Sin esa
  distinción, un tablero que muestre "Gemini $0" al lado de "Claude $12" empuja
  a una decisión de negocio equivocada.
- Incluso con tarifas cargadas, el estimado **no** va a coincidir al centavo con
  la factura del proveedor. La pantalla no puede presentarse como fuente de
  verdad de facturación.

### Recuperar datos ya perdidos

Los tokens se guardan en `usage` (JSONB) **aunque el costo quede en NULL**. Así
que un consumo registrado sin tarifa se puede recalcular después con un script
único sobre las filas con `cost_usd IS NULL`. Es trabajo extra, pero el dato no
está perdido.

---

## 5. Corte del día y zona horaria

Sutil pero decisivo para "Hoy" y "Ayer".

La serie diaria ya se agrupa en `America/Bogota`, pero el frontend manda
`start`/`end` como instantes calculados con `now - N días`. Con eso, "Hoy"
significaría en realidad "últimas 24 horas", mezclando los turnos de la noche
anterior, y los totales no coincidirían con las barras diarias.

**Diseño**: parámetros `from` / `to` de **solo fecha** (`2026-09-21`), que el
backend interpreta en la zona de reporte. Así los totales y la serie diaria usan
el mismo corte de día. Los `start`/`end` actuales se mantienen por
compatibilidad.

---

## 6. Diseño

### Nivel de desglose: proveedor → modelo

Dos niveles. El filtro actúa sobre **proveedor** (tres chips, estables en el
tiempo); el modelo aparece **dentro** de cada fila, expandible. Los modelos
rotan seguido: ponerlos en el filtro lo ensucia en cuanto el proveedor publica
uno nuevo.

### Fase 0 — Cargar tarifas (prerrequisito, no es parte del tablero)

Cargar en el admin el precio por millón de tokens (entrada, salida, lectura de
caché, escritura de caché) de cada modelo que se vaya a usar con Gemini y
OpenAI. Bloquea cualquier corrida paga cuyo consumo se quiera medir.

> Aplica **por instancia**: una app instalada desde el instalador usa su propia
> base, así que sus tarifas se cargan aparte de las de desarrollo.

### Fase 1 — Backend

- `UsageFilters(providers: frozenset[str], models: frozenset[str])`; el query
  param sigue llamándose `provider` pero pasa a repetible
  (`?provider=claude&provider=gemini`). Un valor único sigue siendo válido: no
  rompe clientes actuales.
- VO `ProviderUsage(provider, model, totals)` y
  `per_provider(period, filters, by_model)` → `GROUP BY provider[, model]`.
- `daily_by_provider()` → filas planas `(day, provider, totals)`; el frontend
  pivotea. Se elige esto sobre anidar dentro de `DailyUsage` para no cambiar la
  forma del dato existente.
- ~~`GET /usage/dimensions?from&to`~~ — **no se construyó**, ver sección 8:
  al quedar el filtro solo por proveedor (cerrado, 3 valores), dejó de hacer
  falta.
- Parámetros `from` / `to` por fecha, resueltos en la zona de reporte.
- Migración Alembic con índice compuesto `(role, created_at, provider)`.
  Compuesto simple, **no** parcial: `agent_db` también corre en SQLite para
  escritorio, donde `postgresql_where` se ignora.

### Fase 2 — Barra de filtros compartida

`UsageFilterBar`, que reemplaza a `UsageRangeSelector` y al `<select>`
hardcodeado del admin:

- Presets: **Hoy · Ayer · 7 días · 30 días · 90 días · Personalizado**.
- Con "Personalizado", dos campos de fecha.
- Chips toggleables por proveedor (selección múltiple), estáticos — ver la
  nota sobre `/usage/dimensions` en la sección 8.
- El store pasa de `rangeDays` a `from`/`to` explícitos, y de `provider` a
  `providers: string[]`.

**Todos los filtros aplican a todo**: costo total, tokens totales, serie diaria
y desglose. Es el requisito central.

### Fase 3 — "Mi consumo"

- KPIs que respetan el filtro: Costo total (COP + USD), Tokens, Respuestas y
  **Costo por respuesta** (hoy no existe y es el más comparable entre
  proveedores).
- **Desglose por proveedor**, expandible a modelo: ícono del proveedor
  (reutilizando `ProviderIcon.vue`), costo, barra de porcentaje sobre el total,
  tokens y cantidad de respuestas. Cada fila indica el origen del costo
  (informado / estimado).
- Barra apilada por día con una serie por proveedor, en lugar de la lista de
  barras CSS actual.
- Aviso de `untariffed_count` **nombrando al proveedor**: "12 respuestas de
  Gemini sin tarifa cargada — el costo real es mayor".

### Fase 4 — Admin

- Misma `UsageFilterBar`.
- Tab Global: costo por proveedor en barras horizontales (más legibles que una
  dona para comparar magnitudes) más la apilada diaria.
- Tab KPIs: las tres gráficas actuales recalculadas bajo filtro, más **costo por
  turno comparado entre proveedores** — el número con el que se decide con cuál
  operar.
- ~~Drill-down: click en una barra que fija el filtro a esa fecha~~ — **no se
  construyó**, ver sección 8. Identificar qué pasó en un día se hace hoy
  cambiando a "Personalizado" con ese día como rango.

---

## 7. Referencias de UI

Se aplica el patrón común de los tableros de consumo: presets junto a rango
libre, barra apilada por día segmentada por modelo, tabla con entrada/salida/
caché separados, y totales que responden al filtro activo.

> No se tomó como base la interfaz concreta de ninguna herramienta en
> particular: el layout se derivó del modelo de datos propio.

---

## 8. Orden de trabajo — estado real de la entrega

| Fase | Entrega | Estado |
|---|---|---|
| 0 | Tarifas de Gemini y OpenAI cargadas | Hecho, por instancia (manual, no código) |
| 1 | `UsageFilters` multivalor, `per_provider`/`daily_by_provider`, `from`/`to`, índice compuesto | Hecho |
| 2 | `UsageFilterBar` compartida (presets + chips de proveedor) | Hecho |
| 3 | "Mi consumo": costo por respuesta, desglose expandible, barra apilada | Hecho |
| 4 | Admin: mismo desglose y barra apilada en "Consumo global" | Hecho |

### Dos recortes de alcance deliberados frente al diseño original

- **`GET /usage/dimensions` no se construyó.** El diseño original lo proponía
  para no hardcodear los proveedores del filtro. Pero una vez decidido que el
  filtro actúa solo sobre proveedor (sección 6) — un conjunto cerrado de 3
  valores que ya define `ProviderDescriptor` en el backend —, el endpoint
  dejó de aportar nada: los chips son estáticos
  (`frontend/src/modules/usage/utils/providers.ts`). Si el filtro alguna vez
  necesita ser por modelo (que sí rota), ahí sí hace falta ese endpoint.
- **No hay drill-down** (click en una barra del día para filtrar la tabla de
  conversaciones a esa fecha). Quedó fuera para acotar el alcance de una
  entrega ya grande; es la extensión más directa si se pide después —
  `UsageFilterBar` ya expone `setCustomRange`, así que fijar el rango a un
  día puntual desde un click es agregar el handler, no rediseñar nada.
