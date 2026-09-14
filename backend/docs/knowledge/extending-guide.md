# Guía de extensión — agregar campos, entidades nuevas, evolucionar el schema

Esto es para **devs que quieren hacer crecer el schema**. Si solo querés editar contenido existente, andá a [`editing-guide.md`](./editing-guide.md).

## Tres tipos de extensión, en orden de complejidad

```
┌──────────────────────────────────────────────────────────────┐
│ Tipo A — Agregar campo opcional al schema existente          │
│ Trabajo: 1 archivo Python + opcionalmente actualizar tools.  │
│ Tiempo: 30 minutos.                                          │
│ Breaking: NO. Los archivos viejos siguen válidos.            │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Tipo B — Agregar tipo de entidad nuevo                       │
│ Trabajo: nueva entidad + extender loader + nueva tool MCP.   │
│ Tiempo: 2-3 horas.                                           │
│ Breaking: NO. Es composición pura.                           │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Tipo C — Cambio breaking del schema                          │
│ Trabajo: schema nuevo + loader compatible + migración de     │
│         archivos.                                            │
│ Tiempo: 1-2 días.                                            │
│ Breaking: SÍ. Hay que migrar archivos.                       │
└──────────────────────────────────────────────────────────────┘

```

La regla de oro: **80% de las extensiones son tipo A**. Antes de pensar en tipo B o C, evaluá si lo que querés se puede modelar como campo opcional.

---

## Tipo A — Agregar un campo opcional al schema

### Caso de ejemplo

El equipo SEO te pide: *"queremos documentar el tiempo estimado de cada proceso (5 min, 30 min, 1 hora) para que SAVI le diga al usuario cuánto le va a llevar"*.

### Paso a paso

1. **Editás el Pydantic** (`app/modules/knowledge/domain/entities/form_entry.py`):

   ```python
   class FormEntry(BaseModel):
       # ... campos existentes ...

       estimated_duration: str | None = Field(
           default=None,
           description='Duración estimada del proceso. Ej.: "5 min", "30 min", "1 hora".',
       )
   ```

   Notá:
   - **Tipo `| None`** con `default=None` → es opcional.
   - **NO modifiques** campos existentes. Eso es Tipo C.

2. **Opcionalmente, actualizás el serializer** en `app/modules/chat/infrastructure/llm/tools/knowledge.py` para que el LLM lo vea:

   ```python
   def _form_to_payload(form: FormEntry) -> dict[str, Any]:
       return {
           # ... campos existentes ...
           "estimated_duration": form.estimated_duration,
       }
   ```

3. **Actualizás la documentación** de referencia (`backend/docs/knowledge/reference.md`):

   Agregás una fila a la tabla de FormEntry indicando el campo nuevo y su tipo.

4. **Opcional: actualizás el system prompt** del chat si querés que el LLM use el campo de manera particular. Pero si solo es informativo, el LLM lo ve y lo usa solo.

5. **Probás**: corres los tests, levantás el backend, todos los archivos viejos siguen cargando OK. Editás un form para enriquecerlo con el campo nuevo y verificás en el chat.

### Tests

Si el cambio es importante, agregás un test en `tests/unit/modules/knowledge/test_static_catalog.py` que valide que el campo nuevo se carga y se filtra/usa como esperás.

### Reglas no negociables del Tipo A

- **NUNCA** cambies el tipo de un campo existente. `description: str` → `description: dict[...]` ES Tipo C.
- **NUNCA** hagas un campo previamente opcional ahora requerido. Eso rompe archivos viejos.
- **NUNCA** renombres un campo. Es lo mismo que borrar + crear, y rompe archivos viejos.
- Sí podés deprecar un campo (dejarlo opcional, vaciarlo en futuros archivos) y removerlo más adelante con una migración.

---

## Tipo B — Agregar un tipo de entidad nuevo

### Caso de ejemplo

El equipo SEO quiere documentar **roles del ERP**: Contador, Cajero, Vendedor, Almacenista. Cada rol tiene atribuciones, formularios típicos que usa, y reportes que mira.

Eso no encaja como campo de un form (es transversal). Es una entidad nueva.

### Paso a paso

1. **Creás la entidad Pydantic**:

   ```python
   # app/modules/knowledge/domain/entities/role_entry.py
   from pydantic import BaseModel, ConfigDict, Field


   class RoleEntry(BaseModel):
       model_config = ConfigDict(extra="forbid", frozen=True)

       code: str = Field(min_length=1, description='Identificador (p.ej. "contador").')
       name: str = Field(min_length=1, description="Nombre humano del rol.")
       description: str = Field(min_length=1)
       responsibilities: list[str] = Field(default_factory=list)
       main_forms: list[str] = Field(default_factory=list)
       main_workflows: list[str] = Field(default_factory=list)
   ```

2. **Exportala** del barrel `entities/__init__.py`:

   ```python
   from app.modules.knowledge.domain.entities.role_entry import RoleEntry

   __all__ = [..., "RoleEntry"]
   ```

3. **Definís dónde viven los archivos en disco**. Por ejemplo:

   ```
   data/roles/
   ├── contador.json
   ├── cajero.json
   └── vendedor.json
   ```

   Los roles son transversales (no por módulo), así que `data/roles/` directo.

4. **Extendés el puerto** `KnowledgeCatalog`:

   ```python
   class KnowledgeCatalog(ABC):
       # ... métodos existentes ...

       @abstractmethod
       def get_role(self, code: str) -> RoleEntry | None: ...

       @abstractmethod
       def list_roles(self) -> list[RoleEntry]: ...
   ```

5. **Extendés la implementación** `StaticKnowledgeCatalog`:

   ```python
   class StaticKnowledgeCatalog(KnowledgeCatalog):
       def __init__(self, ..., roles: list[RoleEntry]):
           # ... existente ...
           self._roles_by_code: dict[str, RoleEntry] = {r.code: r for r in roles}

       def get_role(self, code: str) -> RoleEntry | None:
           return self._roles_by_code.get(code)

       def list_roles(self) -> list[RoleEntry]:
           return list(self._roles_by_code.values())
   ```

6. **Extendés el loader** `load_static_catalog`:

   ```python
   roles_dir = root / "roles"
   roles = _load_dir(roles_dir, RoleEntry, optional=True)

   return StaticKnowledgeCatalog(..., roles=roles)
   ```

7. **Sumás un `tipo` al dispatcher, NO una tool nueva.** El agente tiene
   un máximo de 4 tools (ver `backend/docs/mcp_deferred_tools_gotcha.md`).
   Editás `app/modules/chat/infrastructure/llm/tools/knowledge.py`:

   ```python
   def build_describir_rol_impl(catalog: KnowledgeCatalog) -> Callable[[dict[str, Any]], Any]:
       async def impl(args: dict[str, Any]) -> dict[str, Any]:
           code = str(args.get("rol", "")).strip().lower()
           if not code:
               return {"role": None, "message": "Falta el código del rol."}
           role = catalog.get_role(code)
           if role is None:
               return {"role": None, "message": f"Rol desconocido: '{code}'."}
           return {"role": _role_to_payload(role)}
       return impl
   ```

   Y en el mismo archivo:
   - agregás `"rol"` a `KNOWLEDGE_TIPOS` (el JSON Schema de la tool lo
     toma de ahí automáticamente);
   - agregás la rama en `build_consultar_conocimiento_impl`:
     `if tipo == "rol": return await rol({"rol": consulta})`.

8. **Documentás el tipo nuevo** en `_CONSULTAR_CONOCIMIENTO_DESCRIPTION`
   (`app/modules/chat/infrastructure/llm/tools/registry.py`), que es lo que
   lee el modelo para saber cuándo usarlo. El registro sirve igual para
   todos los proveedores de IA: no hay nada que registrar por proveedor.

9. **Actualizás el system prompt** para que el LLM sepa que la tool existe.

10. **Agregás tests** del rol nuevo, similar a los existentes para forms.

11. **Documentás en `reference.md`** el schema de `RoleEntry` con sus campos.

### Reglas del Tipo B

- Si la entidad nueva **se filtra por módulo** (como los forms), incluí `allowed_modules` en el método del puerto.
- Si es **transversal** (como el glosario y los roles), no incluyas filtro.
- Si la entidad **referencia otras** (como los workflows referencian forms vía `form`), no valides la referencia en la entidad Pydantic — eso lo podés hacer en un test smoke que recorra el catálogo entero.

---

## Tipo C — Cambio breaking del schema

### Caso de ejemplo

El equipo quiere separar `description` por audiencia: una versión para usuario funcional, otra para técnico. Antes era `description: str`, ahora debería ser un dict.

### Paso a paso (orden importante)

1. **Versionás el schema en el código**. No reemplazás `FormEntry`: creás `FormEntryV2`.

   ```python
   # form_entry.py

   class FormEntryV1(BaseModel):
       """Schema histórico — description plana."""
       description: str
       # ... resto sin cambio ...


   class FormEntryV2(BaseModel):
       """Schema v2 — description por audiencia."""
       description: DescriptionByAudience  # type: ignore
       # ... resto ...


   class DescriptionByAudience(BaseModel):
       funcional: str
       tecnico: str | None = None
   ```

2. **El loader detecta el formato** y elige el schema. Una forma de hacerlo es por la presencia de `schema_version` en el archivo:

   ```python
   # En cada archivo del v2:
   {
     "schema_version": 2,
     "description": { "funcional": "...", "tecnico": "..." },
     ...
   }

   # En el loader:
   def _parse_form(data: dict, path: Path) -> FormEntry:
       version = data.get("schema_version", 1)
       if version == 1:
           return FormEntryV1.model_validate(data).to_canonical()
       elif version == 2:
           return FormEntryV2.model_validate(data).to_canonical()
       else:
           raise KnowledgeLoadError(f"{path}: schema_version desconocida: {version}")
   ```

3. **Definís una representación canónica** que ambas versiones rinden. Esto es lo que usan las tools y el resto del código:

   ```python
   class FormEntry(BaseModel):  # canónico
       description: DescriptionByAudience  # siempre dict, aunque venga de v1

       @classmethod
       def from_v1(cls, v1: FormEntryV1) -> "FormEntry":
           return cls(description=DescriptionByAudience(funcional=v1.description))
   ```

4. **Migrás archivos viejos uno por uno**. No los migrás todos a la vez — eso anula la ventaja del esquema versionado. Migrás cuando alguien va a enriquecer ese form con la versión técnica.

5. **Eventualmente** (meses después) cuando todos los archivos sean v2, removés `FormEntryV1`. Eso ya no es Tipo C, es housekeeping.

### Reglas críticas del Tipo C

- **Siempre** versionar el schema explícitamente (`schema_version` en el JSON).
- **Siempre** mantener compatibilidad con la versión vieja en el loader. La migración es gradual.
- **Siempre** tener un esquema canónico interno (la representación que ven las tools). Eso aísla el cambio.
- **Nunca** hacer un cambio breaking sin discutirlo en una propuesta primero. Es trabajo de varios días.

---

## Cómo elegir entre A, B y C

Cuando dudás qué tipo de extensión hacer, preguntate:

1. **¿Lo que querés agregar es info adicional sobre algo que ya existe en el catálogo?** → Tipo A. Es el 80% de los casos.

2. **¿Es un concepto nuevo, transversal o paralelo, que no encaja como atributo de algo existente?** → Tipo B.

3. **¿Necesitás cambiar el tipo de un campo existente, o convertir un opcional en requerido?** → Tipo C. Pero antes intentá si lo podés modelar como campo opcional NUEVO (Tipo A) que coexista con el viejo. Casi siempre se puede.

---

## Cómo NO extender el sistema

Estos antipatrones aparecen tarde o temprano. Los listo para que los detectes:

### Antipatrón 1 — "Hagamos un v3 que reemplaza todo"

Tentación: "este JSON quedó desactualizado, hagamos uno nuevo desde cero". **Mal**. Perdés el historial, te llena de breaking changes, y vas a tener que repetir el ejercicio en 6 meses.

Mejor: cada archivo se enriquece independientemente con Tipo A.

### Antipatrón 2 — Campos con strings tipo "json adentro de json"

Tentación: `"metadata": "{key1: val1, key2: val2}"`. **Mal**. JSON adentro de JSON es ilegible y no valida.

Mejor: hacé un sub-modelo Pydantic y declarás los campos.

### Antipatrón 3 — Campos "comodín" tipo `dict[str, Any]`

Tentación: agregar `"custom": {...}` con forma libre. **Mal**. Pierde la garantía de Pydantic, te llena de campos no-validados.

Mejor: si necesitás flexibilidad, agregá los campos opcionales que vayas necesitando con Tipo A.

### Antipatrón 4 — Modificar un archivo por bulk-update programático

Tentación: "necesito agregar X a 50 forms — hago un script". **Mal** si el script genera contenido inventado. **Bien** si el script solo agrega placeholders para que el equipo SEO los complete después.

Una buena heurística: si el LLM puede generar el contenido del campo X automáticamente para 50 forms, ese campo probablemente no aporta valor real.

---

## Checklist al hacer extensiones

### Tipo A

- [ ] El campo es opcional (`| None` o `default_factory=list[...]`).
- [ ] Documentado en `reference.md`.
- [ ] Serializado al LLM si aplica (`_form_to_payload` u otro).
- [ ] Tests no rompen.

### Tipo B

- [ ] Entidad Pydantic con `extra="forbid"`.
- [ ] Exportada en el barrel.
- [ ] Layout de disco definido.
- [ ] Puerto `KnowledgeCatalog` extendido.
- [ ] Implementación `StaticKnowledgeCatalog` extendida.
- [ ] Loader extiende su recorrido.
- [ ] Tool MCP creada y registrada.
- [ ] System prompt actualizado.
- [ ] Documentada en `reference.md`.
- [ ] Tests del nuevo tipo.

### Tipo C

- [ ] Schema versionado explícitamente.
- [ ] Loader compatible con versión vieja Y nueva.
- [ ] Representación canónica interna.
- [ ] Plan de migración gradual documentado.
- [ ] Tests de ambas versiones cargando OK.
- [ ] PR explica el porqué del breaking change.
