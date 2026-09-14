# Tools MCP e integración con el LLM

Cómo el catálogo se expone al agente. Para devs que quieren entender el pipeline o agregar/modificar tools.

## El pipeline completo

```
Usuario en el chat
       │
       ▼
POST /chat con Bearer token
       │
       ▼
Route resuelve el usuario actual (CurrentUserDep)
       │
       ▼
Route llama ResolveUserModulesUseCase → frozenset[ModuleCode]
       │
       ▼
ChatTurnUseCase.execute(..., allowed_modules=modules_filter)
       │
       ▼
LLMRunner.stream_turn(..., allowed_modules=modules_filter)
       │
       ▼
build_savi_mcp_server(allowed_modules=modules_filter)
       │
       ▼
_build_knowledge_tools(allowed_modules)
       │
       ▼  (clausura por turno)
7 tools del knowledge instanciadas con allowed_modules + catalog singleton
       │
       ▼
Claude las ve y las llama cuando le sirve
       │
       ▼
Cada tool consulta el catálogo y filtra ANTES de devolver al LLM
       │
       ▼
LLM recibe info ya filtrada, compone respuesta en castellano natural
```

El punto importante: **`allowed_modules` viaja por todo el pipeline pero solo se aplica al final, dentro de cada tool**. No es un guard que detiene la ejecución, es un filtro de visibilidad.

## Las 7 tools

| Tool | Args | Cuándo la usa el LLM | Filtra por módulos |
|---|---|---|---|
| `buscar_por_intencion` | `consulta: str` | Por defecto en cualquier *"cómo X"*, *"dónde Y"*, *"qué necesito para Z"*. | ✅ |
| `describir_modulo` | `modulo: str` | *"qué hace Contabilidad"* | ✅ |
| `obtener_formulario` | `nombre: str` | Lookup directo cuando ya identificó el form (uso interno del LLM). | ✅ |
| `obtener_workflow` | `workflow_id: str` | Procesos end-to-end. | ✅ (intersección) |
| `responder_faq` | `pregunta: str` | Preguntas muy típicas pre-mapeadas. | ✅ |
| `traducir_termino` | `termino: str` | Siglas, glosario (DIAN, PILA, NIT, PUC). | ❌ (transversal) |
| `listar_modulos_accesibles` | sin args | *"qué puedo hacer en SAVI"* | ✅ |

### Por qué el glosario NO se filtra

Las siglas son del dominio público (DIAN, PILA, NIT). No hay razón para esconder qué significan según el módulo del usuario.

## Cómo se filtra exactamente

Cada tool recibe `allowed_modules: frozenset[ModuleCode] | None` por clausura cuando se construye el server. La construcción se hace **una vez por turno** — el server es nuevo cada vez que entra una request al `/chat`.

```python
# server.py
def build_savi_mcp_server(conversation_id=None, allowed_modules=None):
    return create_sdk_mcp_server(
        ...,
        tools=[
            ...,
            *_build_knowledge_tools(allowed_modules),
        ],
    )
```

Dentro de `_build_knowledge_tools`, cada tool clausura el set:

```python
@tool("buscar_por_intencion", ...)
async def _buscar(args):
    impl = build_buscar_por_intencion_impl(cat, allowed_modules)  # ← acá clausura
    return await impl(args)
```

Y la implementación filtra:

```python
def build_buscar_por_intencion_impl(catalog, allowed_modules):
    async def impl(args):
        hits = catalog.search_by_intent(
            args["consulta"],
            allowed_modules=allowed_modules,  # ← acá filtra
            limit=3,
        )
        return {"matches": [...]}
    return impl
```

### Caso admin

Si el usuario es admin (`is_admin=True`), la ruta `/chat` setea `allowed_modules=None`. En el catálogo:

```python
def search_by_intent(self, query, *, allowed_modules, limit=3):
    for form in self._forms_by_name.values():
        if not self._module_allowed(form.module, allowed_modules):
            continue
        # ...

@staticmethod
def _module_allowed(module, allowed):
    if allowed is None:
        return True  # ← admin pasa por acá
    return module in allowed
```

## Lo que ve el LLM

Cada tool retorna un dict con la info estructurada. Para `buscar_por_intencion`:

```json
{
  "matches": [
    {
      "score": 18,
      "form": {
        "internal_name": "frmConciliacionBancaria",
        "user_label": "Conciliación bancaria",
        "module": "CONTABILIDAD",
        "type": "PROCESO",
        "description": "...",
        "navigation_path": ["Contabilidad", "Procesos", "Conciliación bancaria"],
        "prerequisites": [...],
        "how_to": [...],
        "actions": [...],
        "business_rules": [...],
        "calculations": [...],
        "outputs": [...],
        "common_issues": [...],
        "related_forms": [...],
        "related_workflows": [...]
      }
    }
  ]
}
```

Si no hay matches:

```json
{
  "matches": [],
  "message": "No encontré un formulario o concepto del ERP que matchee esa consulta dentro de los módulos disponibles para el usuario."
}
```

El LLM ve ese `message` y se lo traduce al usuario.

## Las reglas que el system prompt le dice al LLM

En `system_prompt.py` hay una sección dedicada al uso del catálogo. Las reglas clave:

- **Usar `buscar_por_intencion` por defecto** para cualquier pregunta de "cómo X", "dónde Y".
- **Nunca mencionar `internal_name` al usuario** — usar `user_label`.
- **Incluir la `navigation_path`** en la respuesta cuando esté disponible.
- **Usar `prerequisites`, `how_to`, `calculations`, `common_issues`** para componer una respuesta completa.
- **Si la tool devuelve vacío con `message`**, traducir ese motivo al usuario amablemente.
- **Las preguntas conceptuales** se responden con el catálogo, NO con SQL.

## Cómo agregar una tool nueva

(Para Tipo B de [`extending-guide.md`](./extending-guide.md), pero específico para tools.)

> El agente tiene un máximo de **4 tools** (ver
> `backend/docs/mcp_deferred_tools_gotcha.md`). Una capacidad nueva del
> catálogo se agrega como un **`tipo` más** de `consultar_conocimiento`,
> no como tool aparte.

1. **Implementación** en `app/modules/chat/infrastructure/llm/tools/knowledge.py`:

   ```python
   def build_describir_rol_impl(catalog, allowed_modules=None):
       async def impl(args):
           rol = str(args.get("rol", "")).strip().lower()
           if not rol:
               return {"role": None, "message": "Falta el código del rol."}
           entry = catalog.get_role(rol)  # nuevo método del catálogo
           if entry is None:
               return {"role": None, "message": f"Rol '{rol}' no documentado."}
           return {"role": {...}}
       return impl
   ```

2. **Dispatcher**, en el mismo archivo: agregar `"rol"` a `KNOWLEDGE_TIPOS`
   (el JSON Schema de la tool lo toma de ahí) y la rama en
   `build_consultar_conocimiento_impl`:

   ```python
   if tipo == "rol":
       return await rol({"rol": consulta})
   ```

3. **Descripción** en `_CONSULTAR_CONOCIMIENTO_DESCRIPTION`
   (`app/modules/chat/infrastructure/llm/tools/registry.py`): agregar el
   tipo nuevo y cuándo usarlo. El registro es común a todos los
   proveedores de IA.

4. **Mencionar en el system prompt** cuándo usarla.

## Cómo modificar una tool existente

Si querés que `buscar_por_intencion` devuelva 5 matches en vez de 3, cambiás el `limit=3` en `build_buscar_por_intencion_impl`. Pero pensá:

- ¿Más matches = más tokens al LLM = más caro y lento?
- ¿O es porque el ranking actual es flojo?

Si es lo segundo, mejor afinar el scoring de `matches_query` en `FormEntry` que disparar más matches.

## Debugging — cómo saber qué tool está llamando el LLM

El runner emite eventos SSE tipo `tool_use`. El frontend los muestra como pills en la UI ("Pensando…", "Consultando datos…", etc.). En el backend, los logs estructurados incluyen el nombre de la tool y los args.

Para debug local, mirá los logs de uvicorn — cada tool call deja rastro.

## ⚠️ Regla crítica del MCP: máximo 4 tools

La tool del knowledge es **UNA sola** (`consultar_conocimiento`) con un
campo `tipo` que despacha a 7 implementaciones internas. NO son 7 tools
separadas en el MCP server.

Por qué: el Claude Agent SDK pasa a modo "deferred tools" cuando hay
muchas tools. Eso confunde al LLM y le hace alucinar que las tools no
responden. Detalle completo + checklist al agregar tools en
[`backend/docs/mcp_deferred_tools_gotcha.md`](../mcp_deferred_tools_gotcha.md).

**Si en el futuro alguien quiere "separar" la tool del knowledge en
varias tools porque le parece más limpio**: leer ese doc primero. Tiene
el antecedente de la tarde de debugging que esto nos costó.

## Caveats que aprendí construyendo esto

- **Las tools se construyen por turno, no por proceso**. Importante para `allowed_modules`: si el usuario cambia de módulos entre dos turnos (por upgrade de plan), el siguiente turno ya tiene el set actualizado.
- **El catálogo se carga una vez al boot, no por turno**. Cambios en los JSON requieren reinicio. Esto es a propósito — el catálogo es inmutable en runtime.
- **El LLM puede llamar tools varias veces por turno**. `buscar_por_intencion` puede devolver 3 hits y el LLM puede llamar `obtener_formulario` después de elegir uno para más detalle. Es por diseño.
