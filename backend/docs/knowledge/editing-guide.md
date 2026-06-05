# Guía de edición — cómo agregar y modificar conocimiento

Esta es **la guía principal del equipo SEO** (y de cualquiera que quiera enriquecer SAVI). Te dice cómo hacer los cambios más frecuentes paso a paso, con ejemplos copy-paste.

> Si todavía no leíste [`README.md`](./README.md), empezá por ahí. Si querés la referencia exacta de cada campo, andá a [`reference.md`](./reference.md).

## Antes de tocar nada

Tres cosas que tenés que saber:

1. **Todos los archivos viven en `backend/app/modules/knowledge/data/`**. Nunca toques nada fuera de esa carpeta.
2. **Cada cambio se valida con Pydantic al arrancar el backend**. Si rompiste algo, el backend NO arranca y te dice qué archivo está mal.
3. **No hay reload en caliente**. Para ver los cambios tenés que reiniciar el backend (en local: `uv run dev`, parar y volver a correr).

## Caso 1 — Enriquecer un formulario existente (lo más común)

Querés agregarle pasos, ruta de menú, o cálculos a un formulario que ya tiene una entrada en el catálogo.

### Paso a paso

1. Encontrá el archivo:
   ```
   backend/app/modules/knowledge/data/modules/<modulo>/forms/<nombreForm>.json
   ```
   Por ejemplo, `data/modules/contabilidad/forms/frmConciliacionBancaria.json`.

2. Abrilo en tu editor. Vas a ver algo así:
   ```json
   {
     "name": "frmConciliacionBancaria",
     "module": "CONTABILIDAD",
     "type": "PROCESO",
     "description": "Conciliación de extractos bancarios con la contabilidad.",
     "keywords": ["conciliacion bancaria", "extracto bancario"],
     "source": "sisfec_knowledge_base v2"
   }
   ```

3. Agregale los campos que querés. Por ejemplo, ruta del menú y pasos:
   ```json
   {
     "name": "frmConciliacionBancaria",
     "module": "CONTABILIDAD",
     "type": "PROCESO",
     "user_label": "Conciliación bancaria",
     "description": "Cruza el extracto bancario con la contabilidad del período.",
     "keywords": ["conciliacion bancaria", "extracto bancario"],
     "synonyms": ["conciliar banco", "cuadrar extracto"],
     "navigation_path": ["Contabilidad", "Procesos", "Conciliación bancaria"],
     "prerequisites": [
       "Cuenta bancaria creada en el plan contable",
       "Movimientos del período mayorizados"
     ],
     "how_to": [
       { "step": 1, "action": "Seleccionar cuenta bancaria a conciliar" },
       { "step": 2, "action": "Importar extracto", "detail": "Formatos: OFX, CSV o Excel" },
       { "step": 3, "action": "Revisar cruces automáticos" },
       { "step": 4, "action": "Marcar partidas conciliatorias manuales" },
       { "step": 5, "action": "Generar documento de conciliación" }
     ],
     "source": "Manual oficial SEO ERP v2.5",
     "updated": "2026-06-03"
   }
   ```

4. Guardá. Reiniciá el backend.

5. Probá en el chat: *"¿cómo concilio el extracto del banco?"*. SAVI ahora te tiene que dar la ruta del menú, los prerrequisitos y los pasos.

### Reglas importantes para no cagarla

- **NO cambies** los 4 campos requeridos sin entender bien (`name`, `module`, `type`, `description`). El `name` está referenciado desde otros formularios (`related_forms`) — si lo cambiás, esas referencias se rompen.
- **JSON estricto**: comilla doble siempre, sin trailing commas, sin comentarios.
- **`module` con tilde donde corresponda**: `"NÓMINA"`, no `"NOMINA"`. La validación atrapa el typo pero te ahorrás el viaje.
- **Listas vacías** se ponen `[]` o se omiten directamente. No pongas `null` ni `""`.

## Caso 2 — Agregar un formulario nuevo

El formulario existe en el ERP pero no está en el catálogo. Lo agregás creando un archivo nuevo.

### Paso a paso

1. Identificá a qué módulo pertenece. Por ejemplo, `frmCertificadoIngresos` va en `nomina/`.

2. Creá el archivo:
   ```
   backend/app/modules/knowledge/data/modules/nomina/forms/frmCertificadoIngresos.json
   ```

3. El **mínimo viable**:
   ```json
   {
     "name": "frmCertificadoIngresos",
     "module": "NÓMINA",
     "type": "INFORME",
     "description": "Genera el certificado anual de ingresos y retenciones del empleado para la declaración de renta."
   }
   ```

4. Reiniciá. El loader lo descubre automáticamente — **no tenés que registrarlo en ningún lado**.

5. Si querés enriquecerlo desde el día 1, agregale los demás campos (ver [`reference.md`](./reference.md) para todos los disponibles).

## Caso 3 — Crear un workflow nuevo

Un workflow describe un proceso end-to-end que cruza formularios.

### Paso a paso

1. Decidí en qué módulo "principal" vive. Por ejemplo, `wf_facturacion_electronica` va en `cuentacobrar/`.

2. Creá el archivo:
   ```
   data/modules/cuentacobrar/workflows/wf_facturacion_electronica.json
   ```

3. Contenido:
   ```json
   {
     "id": "wf_facturacion_electronica",
     "name": "Facturación electrónica DIAN",
     "description": "Emisión y envío de facturas electrónicas a la DIAN según resolución vigente.",
     "modules": ["CUENTACOBRAR"],
     "synonyms": ["facturar electrónico", "enviar FE", "emisión electrónica"],
     "steps": [
       { "step": 1, "form": "frmFactura", "action": "Crear factura con cliente y productos" },
       { "step": 2, "form": "frmFactura", "action": "Validar resolución DIAN vigente" },
       { "step": 3, "form": "frmEnvioFacturaElectronica", "action": "Enviar al validador HKA" },
       { "step": 4, "form": "frmEnvioFacturaElectronica", "action": "Confirmar acuse de recibo de la DIAN" }
     ]
   }
   ```

## Caso 4 — Agregar una FAQ

Una FAQ es una pregunta natural pre-mapeada con respuesta canónica.

### Paso a paso

1. Si es de un módulo específico:
   ```
   data/modules/contabilidad/faqs/faq_consulta_balance.json
   ```
   Si es transversal:
   ```
   data/shared/faqs/faq_que_es_savi.json
   ```

2. Contenido:
   ```json
   {
     "id": "faq_consulta_balance",
     "question": "¿Cómo veo el balance general del mes?",
     "synonyms": ["balance del mes", "estado financiero mensual"],
     "module": "CONTABILIDAD",
     "answer_summary": "Andá a Contabilidad → Informes → Balance General. Filtrás año y mes. Podés exportar a Excel o generar el gráfico de distribución.",
     "related_forms": ["frmInformeBalanceGeneral"]
   }
   ```

## Caso 5 — Agregar términos al glosario

El glosario es un archivo único con una lista. Para agregar un término, editás esa lista.

### Paso a paso

1. Abrí `data/shared/glossary.json`. Es una lista:
   ```json
   [
     { "term": "DIAN", "definition": "...", "aliases": ["dian"] }
   ]
   ```

2. Agregá tu entrada al final de la lista:
   ```json
   [
     { "term": "DIAN", "definition": "...", "aliases": ["dian"] },
     {
       "term": "PILA",
       "definition": "Planilla Integrada de Liquidación de Aportes — formato oficial colombiano para pagar aportes a seguridad social.",
       "aliases": ["pila", "planilla pila"]
     }
   ]
   ```

## Caso 6 — Eliminar un formulario obsoleto

Si un formulario fue retirado del ERP, simplemente borrás el archivo. El loader no se entera (no hay registro central).

**Pero**: revisá si otros formularios lo referencian en `related_forms`. Si sí, esas referencias quedan apuntando a un nombre que ya no existe — el LLM puede mencionarlo y confundir al usuario. Limpiá esas referencias en el mismo PR.

```bash
# Buscar referencias antes de borrar
grep -r "frmObsoleto" backend/app/modules/knowledge/data/
```

## Errores típicos al editar (y cómo se ven)

### "Field required"

```
Validación falló para .../frmTest.json (modelo FormEntry):
1 validation error for FormEntry
description
  Field required
```

→ Te faltó un campo requerido. Mirá la referencia.

### "Extra inputs are not permitted"

```
Validación falló para .../frmTest.json (modelo FormEntry):
1 validation error for FormEntry
descritpion
  Extra inputs are not permitted
```

→ Typo en el nombre de un campo. `descritpion` por `description`. El `extra="forbid"` lo atrapa.

### "Input should be 'CRUD', 'CONSULTA', 'INFORME', 'PROCESO' or 'TRANSACCION'"

→ El `type` que pusiste no es uno de los 5 válidos. Los enums son cerrados.

### "Input should be a valid enumeration member" (en module)

→ El `module` no matchea un `ModuleCode`. Recordá tildes (`NÓMINA`) y mayúsculas exactas.

### "JSON inválido"

→ Tu archivo no es JSON parseable. Probablemente trailing comma, comilla sin cerrar, o un comentario `//` (JSON no admite comentarios).

## Cuándo NO usar el catálogo y NSESITÁS otra cosa

- **Si la info es narrativa larga** (manual de 20 páginas) → la metés en Capa 2 (RAG, futuro). No la copies en un `business_rules` ni en `description`.
- **Si la info es del cliente** (políticas internas, lista de proveedores específica) → Capa 3 (multi-tenant, futuro).
- **Si la info son DATOS** (saldo, factura, stock) → eso lo consulta `data_query`, no el catálogo.

## Checklist antes de un PR

- [ ] El archivo es JSON válido.
- [ ] `module` está en mayúsculas con tilde donde corresponde.
- [ ] `type` es uno de los 5 válidos.
- [ ] Los campos opcionales que agregaste tienen el formato correcto (listas como `[]`, fechas como `"YYYY-MM-DD"`).
- [ ] `related_forms` apuntan a `name`s que existen en el catálogo.
- [ ] `synonyms` están en castellano natural, como diría el usuario.
- [ ] Corriste el backend localmente y verificaste que arranca sin errores.
- [ ] Probaste una pregunta en el chat que active el formulario que tocaste.
