# Gotcha: el modo "deferred tools" del Claude Agent SDK

> **TL;DR**: el Claude Agent SDK cambia de comportamiento cuando hay **muchas tools** registradas en el MCP server. A partir de ~5-6 tools, las pone en modo **diferido**: el LLM tiene que descubrirlas vía `ToolSearch` antes de poder usarlas. Ese cambio de paradigma confunde al modelo y produce respuestas raras: alucinaciones de "la herramienta no responde", llamadas redundantes, pills repetidas, costo en tokens disparado. **La cura es mantener pocas tools** — y si necesitás muchas funcionalidades, **consolidá en una sola tool con un campo `tipo` discriminador** que despache internamente.

---

## El síntoma

Lo vimos cuando pasamos de 3 tools (`info_empresa`, `consultar_datos`, `consultar_libre`) a 10 tools (las 3 anteriores + 7 del knowledge). En lugar de mejorar el comportamiento del LLM, lo empeoró brutalmente:

- El LLM llamaba a `ToolSearch` antes de usar cualquier tool del knowledge.
- A pesar de que las tools devolvían matches válidos (logueamos el payload exacto enviado al LLM), el LLM respondía: *"Las herramientas del catálogo no me están respondiendo en este momento"*.
- El LLM inventaba pasos genéricos de su entrenamiento (*"buscá en Tesorería o Contabilidad"*) en lugar de usar el dato real del catálogo (*"está en Contabilidad"*).
- Las pills del frontend mostraban *"Procesando información ×3"* + *"Buscando en el catálogo ×2"* + *"Revisando el flujo del proceso ×1"* en una sola interacción — el LLM dando vueltas.
- El costo del turno se disparó: **264k tokens cacheados** en un turno (vs ~100k antes), porque cada `ToolSearch` agrega schema discovery al contexto.

## La causa: el modo "deferred tools"

El Claude Agent SDK, cuando detecta que el set de tools supera cierto umbral (alrededor de 5-7), las **no expone todas directamente al LLM**. En su lugar:

1. Mantiene las tools en un catálogo interno.
2. Le dice al LLM: *"hay tools disponibles, pero no las podés ver directamente. Usá `ToolSearch` para descubrirlas."*
3. El LLM tiene que llamar a `ToolSearch` con keywords, recibir el schema de la(s) tool(s) que matcheen, y recién entonces puede llamarlas.

Esto agrega un round trip extra (`ToolSearch` → schema → llamada real) y, lo más grave, **cambia el modelo mental del LLM**. En lugar de tratar tools como "extensiones de mis capacidades disponibles ahora", el LLM las trata como "recursos remotos que pueden o no estar disponibles" — y se vuelve más conservador hasta el punto de **dudar de los resultados** y alucinar fallas.

Es un patrón documentado por el equipo de Anthropic: el modelo es **más confiable cuando tiene menos tools visibles directamente**. Cada tool agregada después del umbral es un trade-off contra la calidad del razonamiento del modelo.

## Cómo detectarlo

### En los logs del backend

Si el LLM está usando `ToolSearch`, vas a verlo en `tool_invocations` de los mensajes asistente persistidos en BD:

```json
[
  {"id": "toolu_...", "name": "ToolSearch", "input": {"query": "select:mcp__savi__buscar_por_intencion", ...}},
  {"id": "toolu_...", "name": "mcp__savi__buscar_por_intencion", ...}
]
```

`ToolSearch` siempre antes de las tools custom = SDK en modo diferido.

### En las pills del frontend

`ToolSearch` no tiene mapeo en `toolLabels.ts`, así que se renderiza como **"Procesando información"**. Si ves esa pill apareciendo cuando deberías ver una pill específica de tu tool, sospechá del modo diferido.

### En los costos

El cache balloon a >150k tokens cacheados por turno cuando antes estaba en <100k. Cada turno paga ese overhead.

### En el comportamiento del LLM

Las señales más claras son:
- Respuestas tipo *"no encontré"*, *"la herramienta no responde"*, *"el catálogo no está disponible"* **aunque la tool sí devolvió matches válidos** (verificarlo logueando el payload retornado).
- El LLM pide aclaraciones que no debería pedir (*"¿en qué módulo del ERP trabajás?"*) en vez de usar el dato del catálogo.
- Múltiples llamadas a tools distintas para la misma pregunta, como tanteando.

## El fix: consolidación con dispatcher

En vez de N tools separadas, se registra **una sola tool** con un campo discriminador `tipo` que despacha internamente a las N implementaciones.

### Antes (N tools = modo deferred)

```python
# server.py — 7 tools del knowledge separadas, total 10 con las otras 3
@tool("buscar_por_intencion", "...", {"consulta": str})
async def _buscar(args): ...

@tool("describir_modulo", "...", {"modulo": str})
async def _describir(args): ...

@tool("obtener_workflow", "...", {"workflow_id": str})
async def _wf(args): ...

# ... + 4 más
```

### Después (1 tool consolidada = modo directo)

```python
# tools/knowledge.py
def build_consultar_conocimiento_impl(catalog, allowed_modules):
    """Dispatcher: enrutamiento interno por `tipo`."""
    intencion = build_buscar_por_intencion_impl(catalog, allowed_modules)
    modulo    = build_describir_modulo_impl(catalog, allowed_modules)
    workflow  = build_obtener_workflow_impl(catalog, allowed_modules)
    # ... etc

    async def impl(args):
        tipo = str(args.get("tipo", "intencion")).strip().lower()
        consulta = str(args.get("consulta", "")).strip()
        if tipo == "intencion":
            return await intencion({"consulta": consulta})
        if tipo == "modulo":
            return await modulo({"modulo": consulta})
        if tipo == "workflow":
            return await workflow({"workflow_id": consulta})
        # ...
        return {"error": f"tipo '{tipo}' no reconocido"}

    return impl


# server.py — una sola tool
@tool(
    "consultar_conocimiento",
    DESCRIPCION_QUE_EXPLICA_LOS_TIPOS,
    {"tipo": str, "consulta": str},
)
async def _consultar(args):
    impl = build_consultar_conocimiento_impl(cat, allowed_modules)
    return await impl(args)
```

Puntos clave del patrón:

1. **Cada `tipo` mapea a una implementación existente** (no es código nuevo, es plumbing). Las funciones individuales (`build_buscar_por_intencion_impl`, etc.) siguen siendo testeables aisladamente.
2. **El system prompt explica los `tipo` válidos** y cuándo usar cada uno, con ejemplos.
3. **El response del LLM no cambia** — recibe el mismo payload que recibiría llamando la tool granular. Solo cambia la fachada de invocación.
4. **Frontend: una única etiqueta** en `toolLabels.ts` para la tool consolidada. Cero pills "Procesando información" parásitas.

## Regla práctica del proyecto

> **Máximo 4 tools registradas en el MCP server.**

Si necesitás más funcionalidades, consolidalas. Si en algún momento necesitás cruzar ese umbral, **medí antes/después**: corré el chat con queries reales, mirá los `tool_invocations` y el costo en tokens. Si aparece `ToolSearch` o el costo escala feo, **revertí y consolidá**.

## Checklist al agregar una tool MCP nueva

Antes de mergear cualquier PR que agregue una tool al MCP server, validá:

- [ ] **¿Cuántas tools quedan después de este cambio?** Si quedan ≥5, evaluar consolidación.
- [ ] **¿La funcionalidad nueva es realmente disjunta de las existentes?** Si comparte 80% del comportamiento con otra (mismo catálogo, misma fuente de datos), considerá un parámetro extra en lugar de tool separada.
- [ ] **¿Tiene sentido como `tipo` de una tool existente?** Si la respuesta es sí, agregalo como `tipo` y NO crees tool nueva.
- [ ] **Después del merge: probá una pregunta real** y verificá los logs:
  - No debe aparecer `ToolSearch` en `tool_invocations` para queries simples.
  - `cache_read_input_tokens` no debe explotar (>150k es señal de alarma).
- [ ] **Si el LLM dice "la herramienta no responde"** o frases similares cuando la tool sí está respondiendo (verificalo con logging del payload), volvé al patrón dispatcher.

## Cómo verificar rápido si tu set actual está en modo deferred

Hacé una query típica del agente y mirá el campo `tool_invocations` del mensaje asistente persistido en `messages`. Si ves:

```json
{"name": "ToolSearch", ...}
```

ANTES de cualquier tool tuya, estás en modo diferido. Si no aparece, estás en modo directo.

## Antecedente histórico

Este patrón nos costó **una tarde de debugging** mientras el LLM repetidamente alucinaba *"el catálogo no responde"* aunque los logs mostraban payloads válidos con matches. La consolidación de 7 → 1 tool resolvió el problema sin tocar ni una línea del catálogo subyacente, ni del prompt, ni de la lógica de filtrado por módulos. El issue era 100% el modo deferred del SDK.

Resuelto en: PR de la Fase 1 del knowledge (junio 2026).

## Referencias

- Sección 5.2 de `CLAUDE.md` (raíz) — política de tools MCP en SAVI.
- `app/modules/chat/infrastructure/llm/tools/registry.py` — registro neutral de las tools (`claude/mcp_adapter.py` lo expone como MCP).
- `app/modules/chat/infrastructure/llm/tools/knowledge.py` — patrón dispatcher implementado.
