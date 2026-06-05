# Operaciones — bootstrap, loader, troubleshooting

Documentación operativa: cómo regenerar contenido desde el v2, diagnosticar fallas de boot, troubleshooting típico.

## El loader — qué hace al arrancar

Cuando el backend arranca (`uv run dev`), se ejecuta `lifespan` en `app/main.py`. Una de las cosas que hace es:

```python
knowledge_root = Path(__file__).resolve().parent / "modules" / "knowledge" / "data"
init_catalog(knowledge_root)
```

Esto dispara `load_static_catalog(root)` en `app/modules/knowledge/infrastructure/static_catalog.py`.

El loader hace, en orden:

1. **Verifica que `<root>` exista**. Si no, levanta `KnowledgeLoadError`.
2. **Recorre `<root>/modules/*/`** y por cada dossier:
   - Lee `overview.json` si existe → `ModuleEntry`.
   - Lee `forms/*.json` → lista de `FormEntry`.
   - Lee `workflows/*.json` → lista de `WorkflowEntry`.
   - Lee `faqs/*.json` → lista de `FaqEntry`.
3. **Lee `<root>/shared/glossary.json`** si existe → lista de `GlossaryEntry`.
4. **Construye índices en memoria**: por nombre de form, por código de módulo, por id de workflow, por término del glosario (case-insensitive + aliases).
5. **Lo guarda como singleton** accesible vía `get_catalog()`.

Si **cualquier paso** falla, el backend NO arranca. La idea es preferir crashear que servir respuestas con knowledge corrupto.

### Performance del loader

- Tiempo: ~50 ms para los 144 archivos actuales.
- Memoria: ~2 MB de Python objects (Pydantic).
- Escalabilidad: O(n) en cantidad de archivos. Hasta unos 5k archivos sigue siendo subsegundo.

## Cómo diagnosticar fallas al boot

Si el backend no arranca después de un cambio en el knowledge, el error te dice qué archivo falló:

### Ejemplo 1: validación Pydantic

```
KnowledgeLoadError: Validación falló para .../forms/frmTest.json (modelo FormEntry):
1 validation error for FormEntry
description
  Field required [type=missing, input_value={'name': 'frmTest', ...}, input_type=dict]
```

→ Falta el campo `description`. Lo agregás en el JSON y reiniciás.

### Ejemplo 2: JSON malformado

```
KnowledgeLoadError: JSON inválido en .../forms/frmTest.json: Expecting ',' delimiter: line 8 column 3 (char 124)
```

→ Probablemente trailing comma o comilla sin cerrar. Validá con un linter de JSON (cualquier editor moderno lo destaca).

### Ejemplo 3: enum inválido

```
KnowledgeLoadError: Validación falló para .../forms/frmTest.json (modelo FormEntry):
1 validation error for FormEntry
module
  Input should be 'CONTABILIDAD', 'NÓMINA', 'INVENTARIO', ... [type=enum, input_value='CONTABILDIAD']
```

→ Typo en `module`. Notá el detalle: `NÓMINA` tiene tilde, no `NOMINA`.

### Ejemplo 4: campo extra no declarado

```
KnowledgeLoadError: Validación falló para .../forms/frmTest.json (modelo FormEntry):
1 validation error for FormEntry
descritpion
  Extra inputs are not permitted [type=extra_forbidden]
```

→ Typo en el nombre del campo. `descritpion` por `description`. Configuramos `extra="forbid"` justamente para atrapar esto.

### Ejemplo 5: directorio requerido falta

```
KnowledgeLoadError: Knowledge root no existe: .../data
```

→ Alguien borró la carpeta `data/` o el path resolution se rompió. Verificá que `app/modules/knowledge/data/` exista.

## El script de bootstrap — cuándo y cómo se usa

Hay un script one-shot en `backend/scripts/bootstrap_knowledge.py` que regenera la estructura de archivos desde el JSON v2 original.

### Cuándo correrlo

- **La primera vez** (ya se corrió al implementar el sistema).
- **Si recibís una versión nueva del v2** desde el equipo SEO y querés re-bootstrappear desde cero (entendiendo que perdés los cambios manuales — ver advertencia).
- **Nunca en CI ni en producción**. Es manual y opcional.

### Cómo correrlo

```bash
cd backend
uv run python -m scripts.bootstrap_knowledge \
  --source "C:/Users/hikig/Documents/SEOGroup/Conocimiento/sisfec_knowledge_base_v2.json" \
  --target app/modules/knowledge/data
```

Salida típica:

```
[skip] Módulo no mapeado: Inicio
[skip] Módulo no mapeado: Seguridad
{
  "modules": 10,
  "forms": 101,
  "workflows": 4,
  "faqs": 29,
  "skipped_modules": 2,
  "skipped_workflows": 0
}
```

### ⚠️ Advertencia importante

El script **PISA** los archivos existentes. Si vos enriqueciste manualmente `frmConciliacionBancaria.json` con `how_to` y `navigation_path`, y después corrés el bootstrap, esos campos se pierden — vuelve a la versión mínima del v2.

**Buena práctica**:
- Antes de re-bootstrappear, hacé `git status` y verificá que todo esté commiteado.
- Después del bootstrap, hacé `git diff` para ver qué se perdió.
- Si se perdió trabajo, hacés `git restore` selectivo de los archivos que enriqueciste y dejás los nuevos del bootstrap.

### Una alternativa más segura

Si vas a recibir versiones nuevas del v2 frecuentemente, vale la pena modificar el script para que sea **incremental**:

- Solo crea archivos que no existen.
- Para archivos existentes, hace `merge` preservando campos que no vienen en el v2 (como `navigation_path`, `how_to`).

Eso es trabajo de futura iteración. Hoy el script es "regenerar desde cero".

## Cómo se mapean los módulos del v2 a `ModuleCode`

El v2 usa nombres mixed-case (`Contabilidad`, `CuentaCobrar`). `ModuleCode` usa UPPER con tildes. La traducción está hardcodeada en el script:

```python
_V2_MODULE_TO_CODE = {
    "Inventario": "INVENTARIO",
    "CuentaCobrar": "CUENTACOBRAR",
    "CuentaPagar": "CUENTAPAGAR",
    "Cartera": "CARTERAFINANCIERA",
    "Contabilidad": "CONTABILIDAD",
    "Nomina": "NÓMINA",
    "Venta": "VENTA",
    "Tercero": "TERCERO",
    "ActivoFijo": "ACTIVOFIJO",
    "Herramientas": "HERRAMIENTA",
    # Inicio y Seguridad NO se mapean.
}
```

Si el v2 trae un módulo nuevo (poco probable), agregás la entrada al diccionario.

## Tests — qué cubren

`tests/unit/modules/knowledge/test_static_catalog.py` cubre:

- Carga de un catálogo mínimo artificial (tmp_path con un par de archivos).
- Búsqueda por intención con scoring.
- Filtrado por módulos autorizados.
- Filtrado transversal del glosario (sin restricción).
- Validación falla loud cuando hay archivos inválidos.
- Filtrado por intersección de módulos en workflows.
- **Smoke test sobre el catálogo real** generado por bootstrap (ejecuta `buscar_por_intencion` y verifica que el top hit es el esperado).

### Cómo corrés los tests

```bash
cd backend
uv run pytest tests/unit/modules/knowledge/ -v
```

Si el smoke test falla, significa que algo en los archivos reales se corrompió. Es buen gate de regresión cada vez que hacés cambios masivos.

## Performance — qué medir si crece el catálogo

Si en el futuro tenemos 5k+ archivos en `data/`, las métricas a vigilar son:

- **Tiempo de boot**: el loader recorre todo serialmente. Si pasa de ~5s, considerá paralelizar la carga.
- **Memoria**: ~2 MB hoy, ~100 MB con 5k forms es esperable.
- **Tiempo per-tool call**: `buscar_por_intencion` es O(n) sobre los forms. Si pasa de 10ms, considerá:
  - Cache LRU de búsquedas recientes.
  - Pre-índice invertido (palabra → forms que la contienen).
  - O directamente saltar a Capa 2 con embeddings.

Hoy nada de esto es necesario.

## Logs útiles

El backend no loguea cada carga del catálogo (sería ruidoso). Pero podés agregar un log estructurado en `init_catalog` si querés verificar qué se cargó en deploy:

```python
log.info(
    "knowledge_loaded",
    modules=len(catalog._modules_by_code),
    forms=len(catalog._forms_by_name),
    workflows=len(catalog._workflows_by_id),
    faqs=len(catalog._faqs),
    glossary=len(catalog._glossary_by_key),
)
```

(No lo tenemos hoy porque es overhead innecesario en local; vale la pena en producción.)

## Troubleshooting flowchart

```
¿El backend no arranca?
  └→ Mirá el último error en stderr.
     ├→ "KnowledgeLoadError" → el problema está en knowledge/data/. Mirá el archivo que indica.
     │  ├→ "JSON inválido" → editor de JSON para encontrar el char roto.
     │  ├→ "Field required" → falta un campo requerido.
     │  ├→ "Extra inputs not permitted" → typo en nombre de campo.
     │  └→ "Input should be..." → enum inválido (module/type).
     └→ Otro error → no es del knowledge.

¿El backend arranca pero el chat no usa el catálogo?
  ├→ Verificá que las tools estén en ALLOWED_TOOLS de server.py.
  ├→ Verificá que el system prompt mencione cuándo usarlas.
  └→ Mirá los eventos SSE en el frontend: ¿el LLM llama tool_use con nombres del knowledge?

¿El LLM filtra mal por módulos?
  ├→ Verificá que la ruta /chat resuelva user.modules correctamente.
  ├→ Verificá que allowed_modules viaje por todo el pipeline (route → use case → runner → server).
  └→ Verificá que cada tool reciba el set correcto (logs de debug).

¿Las búsquedas no traen lo esperado?
  ├→ Verificá synonyms y keywords del form objetivo.
  ├→ Probá la búsqueda en un test unitario con la query exacta.
  └→ Si el form no tiene synonyms enriquecidos, la búsqueda solo matchea por description.
```
