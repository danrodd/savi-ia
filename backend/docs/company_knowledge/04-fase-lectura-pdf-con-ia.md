# Fase 4 — Lectura de PDF con IA

> Parte de: [PRD — Conocimiento de la empresa](00-prd.md)
> Estado: **implementada** (backend `45c5ea2`, frontend en el commit siguiente).
> Cambio visible: los PDF escaneados, las fichas técnicas y los planos
> dejan de quedar en "Sin texto". La IA del proveedor configurado los
> transcribe (texto, tablas y descripción de imágenes) y SAVI responde
> con ese contenido, citando la página.
> Skills a leer antes de codear: `enterprise-backend-fastapi`,
> `savi-backend-patterns` (worker en el `lifespan`, proveedores) y, en el
> frontend, `vue-best-practices` y `vue-pinia-best-practices`.

## Resultado esperado

- [ ] Spike cerrado (§3): S1–S3 ✔ en los tres proveedores; segunda ronda con 7 PDF públicos ✔ (`gpt-6-luna` recomendado, dos defectos de Gemini corregidos). **Faltan** el token OAuth de Claude y el documento largo (165 págs.).
- [x] Interruptor global "Leer PDF con IA" visible en la pantalla de Conocimiento, con proveedor, modelo y costo estimado por página.
- [x] Costo estimado del lote en el diálogo de subida, antes de subir.
- [x] Lectura por tramos de páginas con el prompt y el esquema de §6, en paralelo acotado y con reintentos.
- [x] Respaldo con `pypdf` por tramo cuando la IA falla o no está disponible.
- [x] Páginas leídas guardadas: reprocesar no vuelve a pagar y un reinicio retoma donde iba.
- [x] Costo de la lectura registrado y visible en el módulo de uso.
- [x] Métricas de `pypdf` por página guardadas para decidir la Fase 5 (§11).
- [x] Botón "Leer con IA" para documentos existentes.
- [x] Límite de tamaño de archivo ajustado para escaneos de celular.
- [ ] Tests (§12): unitarios e integración ✔ (backend 791, frontend 135); verificado en la interfaz real con `gpt-6-luna`. **Falta** el E2E de Playwright versionado (los actuales activan Claude y gastan su cuota).

---

## 1. Contexto y decisión

### 1.1 Qué pasa hoy

- `PdfTextExtractor` usa `pypdf` y saca solo la capa de texto.
- Si el promedio es menor a 50 caracteres por página
  (`_MIN_CHARS_PER_PDF_PAGE`, `pipeline.py`), el documento queda
  `no_text`. El PRD dejó el OCR fuera de la v1 (`00-prd.md` §3, R6).
- La decisión es **por documento**: un contrato digital con anexos
  escaneados queda `ready` y los anexos se pierden en silencio.
- No existe una opción de lectura con IA. El aviso del diálogo de subida
  (`CompanyDocumentUploadDialog.vue`) habla del envío de fragmentos al
  responder, no de la importación.

### 1.2 Escenario de referencia (no el ideal)

El caso común son **PDF armados con fotos del celular**: cada página es
una imagen JPEG de 1–5 MB, sin capa de texto, a veces girada, a veces con
la marca de agua de la app de escaneo. Le siguen las fichas técnicas
(tablas y diagramas) y los planos. El diseño se valida contra esos
archivos, no contra PDF generados desde Word.

### 1.3 Decisión

**La IA del proveedor activo lee el PDF. `pypdf` queda como respaldo.**

- La IA es mucho mejor con imágenes, tablas y escaneos, y el costo por
  página es bajo (§2).
- En un PDF digital de texto plano, `pypdf` es exacto y la IA puede
  resumir o saltarse partes. Se mitiga con un prompt de **transcripción
  literal** (§6) y se mide durante esta fase para decidir la siguiente
  (§11).
- El pipeline toma la decisión **por página** desde esta fase, aunque en
  la Fase 4 la política siempre responda "IA". Así la Fase 5 (mixto
  automático) solo cambia la política, sin tocar la cola, el prompt, el
  guardado ni las citas.

### 1.4 Alternativas descartadas

| Alternativa | Por qué no |
|---|---|
| Clasificar páginas y mandar a la IA solo las escaneadas, ya en esta fase | Más reglas (umbral de texto, marcas de agua, OCR basura) sin datos reales para calibrarlas. Pasa a la Fase 5, con los datos de esta fase. |
| OCR local (Tesseract) | Binario externo en el instalador, calidad baja en fotos de celular y no entiende tablas ni diagramas. |
| Convertir páginas a imagen y mandar imágenes | Exige un renderizador. PyMuPDF es AGPL (incompatible con el instalador) y `pypdfium2` suma binarios. Los tres proveedores aceptan PDF directo. |
| Casilla "leer con IA" por archivo | El administrador no sabe qué PDF tiene imágenes; la marcaría siempre o nunca. |

## 2. Costos

Supuesto: 100 páginas con imágenes, ~700 tokens de salida por página
(transcripción + tablas + descripción de imágenes). Precios oficiales a
septiembre de 2026, en USD por millón de tokens.

| Proveedor · modelo | Entrada / salida | Entrada por página | Costo por 100 páginas |
|---|---|---|---|
| OpenAI · `gpt-6-luna` | $0,10 / $0,50 | ~2.500 (texto + imagen de la página) | **~US$0,06** |
| Gemini · `gemini-flash-lite-latest` | $0,30 / $2,50 | 258 fijos por página + prompt | **~US$0,18** |
| Claude · `claude-haiku-4-5` | $1 / $5 | 1.500–3.000 de texto + imagen | **~US$0,65** |
| Claude · `claude-sonnet-5` | $2 / $10 | igual | **~US$1,30** |

- La salida es la parte que más pesa.
- Un manual digital de 500 páginas cuesta ~US$0,30 con `gpt-6-luna` y
  ~US$3 con Haiku.
- **Modelo de lectura**: campo propio `document_model` en
  `llm_provider_configs`, que por defecto toma el `chat_model`. En la
  primera ronda del spike, Haiku cambió "4.000" por "4 000" y
  `gpt-6-luna` leyó mal un código de referencia
  ([spike](spike-lectura-ia.md)). Con Claude, el valor por defecto es
  Sonnet. El administrador puede elegir un modelo más barato sabiendo el
  riesgo.
- Costos reales de la primera ronda por 100 páginas: `gpt-6-luna`
  ~US$0,06, Flash-Lite ~US$0,07, Haiku ~US$0,68 y Sonnet 5 ~US$1,02.
- **Hallazgo de configuración:** en la instalación de desarrollo, Claude
  no tiene precios cargados (`pricing = {}`). Sin precios, la lectura se
  registra con costo desconocido, igual que hoy el chat. La pantalla lo
  advierte (§8.1).

## 3. Spike (obligatorio antes de §5)

Script en `backend/scripts/spike_pdf_ai.py`, no versiona documentos de
clientes. Corpus mínimo en una carpeta local ignorada por git:

- 3 PDF de fotos de celular (uno con marca de agua de app, uno con
  páginas giradas, uno de más de 20 MB).
- 3 fichas técnicas con tablas y diagramas.
- 1 plano.
- 2 PDF digitales de texto (para medir omisiones).

Preguntas que el spike responde, por proveedor:

| # | Pregunta | Criterio |
|---|---|---|
| S1 | ¿Acepta el PDF de un tramo directo? | Claude: bloque `document` por el Agent SDK (entrada en streaming). Gemini: `Part` inline `application/pdf`. OpenAI: `input_file` en Responses. |
| S2 | ¿Claude con `local_session` y `oauth_token` acepta el PDF? | Si el Agent SDK no lo permite, se evalúa en este orden: (a) otra vía dentro del Agent SDK; (b) `anthropic` directo **solo** con `api_key`; (c) `pypdf` para esas credenciales, con aviso en la pantalla. Se documenta la decisión. |
| S3 | ¿Devuelve el JSON de §6.2 válido? | 20 de 20 tramos parseables, con salida estructurada nativa o con validación + un reintento. |
| S4 | ¿Transcribe fiel? | En los PDF digitales, ≥ 97 % de las palabras de `pypdf` presentes en la salida de la IA (§11.2). |
| S5 | ¿Cuánto cuesta y tarda de verdad? | Tokens y segundos por página reales, para corregir la tabla de §2 y el estimador (§8.2). |
| S6 | Tramo máximo | Páginas y MB por pedido sin errores ni timeouts. Punto de partida: 5 páginas u 8 MB. |

Resultado en [`spike-lectura-ia.md`](spike-lectura-ia.md).

**Estado tras la primera ronda (documento sintético):**
- S1 y S3 resueltos en los tres proveedores.
- S2 resuelto para la sesión local; falta confirmar el token OAuth.
- S4, S5 y S6 esperan el corpus real.

## 4. Flujo

```
Worker toma el documento (cola actual, uno a la vez)
  │
  ├─ 1. pypdf por página, en el executor: texto + métricas (§5.3)   ← gratis
  ├─ 2. Política decide por página: "texto" o "ia"                   ← Fase 4: todo "ia"
  │                                                                     si la lectura con IA está activa
  ├─ 3. Páginas "ia" ya leídas en esta versión → se reutilizan (§5.2)
  ├─ 4. Resto de páginas "ia" → tramos → proveedor (paralelo acotado)
  │       └─ tramo falla tras reintentos → esas páginas usan el texto de pypdf
  ├─ 5. Guardar cada página leída al terminar su tramo
  └─ 6. ExtractedText(pages=[...]) → chunker → embeddings → índice   ← sin cambios
```

- TXT y Markdown no cambian.
- Si no hay proveedor activo o el interruptor está apagado, la política
  responde "texto" en todas las páginas y el resultado es idéntico al
  actual.
- El documento es `no_text` solo si **todas** las páginas quedan vacías
  después de la IA y del respaldo.

## 5. Backend

### 5.1 Piezas nuevas en `app/modules/company_knowledge/`

| Capa | Pieza | Responsabilidad |
|---|---|---|
| `domain/interfaces` | `PdfPageReader` (puerto) | `async read(tramo: bytes, first_page: int, page_count: int) -> PageReadResult`. Una implementación por proveedor. |
| `domain/interfaces` | `PageRoutingPolicy` (puerto) | `decide(page: PageMetrics) -> Literal["text", "ai"]`. |
| `domain/entities` | `PageMetrics`, `ReadPage`, `PageReadResult` | Métricas de pypdf, página leída (texto, tipo, legible, método) y resultado de un tramo con uso de tokens. |
| `domain/interfaces` | `DocumentPageRepository` | Guardar y leer páginas por `(document_id, version)`. |
| `application/use_cases` | `ReadPdfPagesUseCase` | Orquesta los pasos 1 a 5 de §4. |
| `infrastructure/ai_reading/` | `claude_reader.py`, `gemini_reader.py`, `openai_reader.py`, `prompt.py`, `schema.py`, `splitter.py` | Adaptadores, prompt y esquema (§6), y partición del PDF en tramos con `pypdf` (`PdfWriter`). |
| `infrastructure/ai_reading/` | `AllAiPolicy`, `TextOnlyPolicy` | Políticas de la Fase 4. |
| `infrastructure/persistence` | modelos y repositorio de §5.2 | |

- Los adaptadores reciben el `ActiveProvider` que resuelve el
  `ActiveProviderResolver` actual. Siguen el patrón de los generadores de
  título (`chat/infrastructure/llm/*/title_generator.py`): llamada única,
  sin herramientas, credencial solo en memoria.
- Parámetros por proveedor, según el spike:

  | Proveedor | Envío del tramo | Salida estructurada | Razonamiento |
  |---|---|---|---|
  | Claude | Bloque `document` base64, en modo de entrada en streaming del Agent SDK | `output_format` (`json_schema`); leer `ResultMessage.structured_output` | `thinking={"type": "disabled"}`; `max_turns=3` |
  | OpenAI | `input_file` con `file_data` base64, en Responses | `text.format` `json_schema` strict | `reasoning.effort = low` (`minimal` no existe en GPT-6; si el modelo no acepta el parámetro, se repite sin él) |
  | Gemini | `Part.from_bytes(..., "application/pdf")` | `response_json_schema` | No enviar `thinking_config`: `thinking_budget=0` devuelve 400 |

- `PipelineDocumentProcessor` gana `process_pages(extracted)`, que
  recibe un `ExtractedText` ya armado y hace solo fragmentación y
  embeddings. `process()` sigue igual para TXT y MD.
- `ProcessNextCompanyDocumentUseCase._run_pipeline` llama a
  `ReadPdfPagesUseCase` antes del procesador cuando el documento es PDF.
  La lectura es `async` y corre en el event loop; `pypdf`, la partición
  y los embeddings siguen en el executor.
- **No se agrega ninguna tool MCP.** El contenido entra al índice actual
  y se consulta con `consultar_conocimiento`, como hoy.

### 5.2 Modelo de datos

**`company_document_pages`** (nueva)

| Columna | Tipo | Notas |
|---|---|---|
| `document_id` | FK `ON DELETE CASCADE` | PK compuesta con `version` y `page_number`. |
| `version` | `Integer` | Versión del documento; reemplazar invalida las páginas viejas. |
| `page_number` | `Integer` | Base 1. |
| `method` | `String(8)` | `text` \| `ai`. |
| `page_type` | `String(16)` NULL | `texto` \| `tabla` \| `diagrama` \| `foto` \| `formulario` \| `mixto` (solo `ai`). |
| `legible` | `Boolean` NULL | Solo `ai`. |
| `text` | `Text` | Contenido final de la página. |
| `pypdf_chars` | `Integer` | Caracteres de `pypdf` después de quitar líneas repetidas. |
| `image_count` | `Integer` | Imágenes embebidas en la página. |
| `max_image_pixels` | `Integer` | Píxeles de la imagen más grande (ancho × alto). |
| `ai_error` | `String(48)` NULL | Motivo si el tramo cayó al respaldo. |
| `created_at` | `UtcDateTime` | |

**`company_document_ai_reads`** (nueva, una fila por pedido al proveedor)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `UuidType` PK | |
| `document_id` / `version` | | |
| `page_from` / `page_to` | `Integer` | |
| `provider` / `model` | `String` | |
| `input_tokens` / `output_tokens` | `Integer` | |
| `cost_usd` | `Numeric` NULL | `NULL` si el modelo no tiene precio configurado. |
| `outcome` | `String(16)` | `ok` \| `retried` \| `fallback`. |
| `uploaded_by_login` / `uploaded_by_database_id` | | Para atribuir el gasto en uso. |
| `created_at` | `UtcDateTime` | |

**`company_documents`** (columnas nuevas)

| Columna | Tipo | Notas |
|---|---|---|
| `reading_method` | `String(8)` NULL | `text` \| `ai` \| `mixed`. Se calcula al terminar. |
| `ai_page_count` | `Integer` default 0 | |
| `ai_cost_usd` | `Numeric` NULL | Suma de la versión vigente. |

**`llm_provider_configs`** (columna nueva)

| Columna | Tipo | Notas |
|---|---|---|
| `document_model` | `String` NULL | Modelo de lectura de documentos. `NULL` = usar `chat_model`. Se edita en la pantalla de proveedores, junto a los otros dos modelos. |

**`company_knowledge_settings`** (nueva, una sola fila)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `Integer` PK = 1 | |
| `ai_reading_enabled` | `Boolean` default `true` | Solo tiene efecto con un proveedor activo. |
| `updated_by_login` / `updated_at` | | |

Una migración Alembic en batch mode, con los modelos registrados en
`bootstrap.py` y `alembic/env.py`. Probar en Postgres y SQLite.

**Por qué guardar las páginas:**
- Reprocesar (por ejemplo, al cambiar el modelo de embeddings) reutiliza
  las páginas y **no vuelve a pagar**.
- Si el servidor se reinicia a mitad de un documento, se retoma desde las
  páginas que faltan.
- Son los datos para decidir la Fase 5.

### 5.3 Métricas de `pypdf` por página

Se calculan en el paso 1 para todas las páginas, incluso las que lee la
IA. Cuesta milisegundos por página.

- `pypdf_chars`: con la misma normalización y remoción de líneas
  repetidas de hoy, que también saca las marcas de agua de las apps de
  escaneo.
- `image_count` y `max_image_pixels`: de `page.images`, sin decodificar
  las imágenes.

### 5.4 Tramos y concurrencia

- Un tramo agrupa páginas consecutivas hasta **5 páginas u 8 MB**, lo
  que llegue primero. Una página sola de más de 8 MB va sola. Si supera el
  límite del proveedor, va al respaldo con `ai_error = page_too_large`.
  Los valores finales salen del spike (S6).
- **Los documentos se procesan de a uno**, con la cola actual.
- Dentro de un documento, **hasta 3 tramos en paralelo**
  (`company_docs_ai_concurrency`).
- Error 429, 5xx o timeout (120 s por tramo): reintento con backoff
  exponencial (`company_docs_ai_retry_attempts = 3`). Si sigue fallando,
  esas páginas usan el texto de `pypdf` y se marca `outcome = fallback`.
- **Convivencia con el chat.** No hay forma de reservar cupo en el
  proveedor. La prioridad del chat se protege con la concurrencia baja y
  el backoff: ante un 429, la importación espera y el chat no.
- **JSON inválido**: un reintento del mismo tramo con un recordatorio del
  formato. Si falla de nuevo, se usa el respaldo.
- **Números de página**: se validan contra el tramo. Si faltan páginas en
  la respuesta, esas páginas usan el respaldo.

### 5.5 Configuración (`Settings`)

| Variable | Default | Para qué |
|---|---|---|
| `company_docs_max_file_mb` | 20 → **60** | Escaneos de celular. Verificar el límite de subida del servidor y del proxy. |
| `company_docs_ai_concurrency` | 3 | Tramos en paralelo por documento. |
| `company_docs_ai_pages_per_request` | 5 | Tope de páginas por tramo. |
| `company_docs_ai_max_request_mb` | 8 | Tope de MB por tramo. |
| `company_docs_ai_timeout_s` | 120 | Por tramo. |
| `company_docs_ai_retry_attempts` | 3 | |

### 5.6 API

| Método y ruta | Qué hace |
|---|---|
| `GET /admin/company-documents/ai-reading` | `ai_reading_enabled`, proveedor y modelo de lectura, `available` (hay proveedor usable y el spike lo habilitó para la credencial), `estimated_usd_per_page` (`null` sin precios) y `privacy_notice`. |
| `PUT /admin/company-documents/ai-reading` | Cambia `ai_reading_enabled`. Solo administradores. |
| `POST /admin/company-documents/{id}/read-with-ai` | Encola el documento para leerlo con IA **de nuevo**: descarta las páginas `ai` de la versión vigente. |
| `POST /admin/company-documents/{id}/reprocess` | Sin cambios de contrato. Ahora reutiliza las páginas guardadas. |
| `GET /admin/company-documents/{id}` | Suma `reading_method`, `ai_page_count` y `ai_cost_usd`. |

El avance (`progress.py`) agrega la etapa: `reading` (páginas leídas /
total) y después `embedding` (fragmentos / total).

## 6. Prompt y estructura de la respuesta

Es la pieza que más define la calidad del conocimiento. Vive en
`infrastructure/ai_reading/prompt.py` y `schema.py`, versionado
(`PROMPT_VERSION`), y la versión se guarda con cada página para poder
releer si el prompt mejora.

### 6.1 Prompt (sistema)

```text
Eres un transcriptor de documentos. Recibes un tramo de un PDF de una
empresa (manuales, fichas técnicas, planos, formularios, documentos
escaneados o fotografiados con un celular).

Tu tarea es TRANSCRIBIR, no resumir ni interpretar. Reglas:

1. Transcribe todo el texto visible de cada página, completo y en orden
   de lectura, en el idioma original.
2. Copia números, unidades, códigos, referencias, fechas y nombres
   exactamente como aparecen. No redondees, no conviertas unidades y no
   corrijas nada. Conserva los separadores de miles y decimales tal cual
   (4.000 se escribe 4.000; 3,7 se escribe 3,7).
3. Convierte las tablas a tablas Markdown y conserva los encabezados de
   columna. Si una tabla sigue en la página siguiente, repite los
   encabezados.
4. Marca los títulos y subtítulos con "#" y "##" según su jerarquía.
5. Describe cada imagen, diagrama, plano o gráfico en un bloque
   "[Imagen: ...]": qué muestra, sus etiquetas, medidas, valores y
   relaciones que sirvan para responder preguntas. No describas logos ni
   adornos. Omite las marcas de agua de las aplicaciones de escaneo (por
   ejemplo, "Escaneado con CamScanner").
6. En formularios, escribe "Campo: valor" y marca las casillas como
   [x] o [ ].
7. Si una parte no se lee, escribe [ilegible]. Si la página entera no se
   puede leer, deja el contenido vacío y marca legible = false.
8. No inventes contenido que no está en la página. No agregues
   explicaciones, conclusiones ni comentarios.
9. Si la página está girada, transcríbela en su orientación correcta.
10. Responde SOLO con el JSON del esquema, con una entrada por cada
    página del tramo, en orden.
```

El mensaje de usuario indica el rango (`Páginas 11 a 15 del documento`)
y adjunta el tramo. La numeración de la respuesta es la del documento,
no la del tramo.

### 6.2 Esquema

```json
{
  "type": "object",
  "required": ["paginas"],
  "properties": {
    "paginas": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["numero", "tipo", "contenido", "legible"],
        "properties": {
          "numero":    { "type": "integer" },
          "tipo":      { "enum": ["texto", "tabla", "diagrama", "foto", "formulario", "mixto"] },
          "contenido": { "type": "string" },
          "legible":   { "type": "boolean" }
        }
      }
    }
  }
}
```

- Se usa la salida estructurada nativa de cada proveedor cuando existe
  (OpenAI `json_schema`, Gemini `response_schema`, Claude según el spike)
  y siempre se valida con Pydantic.
- `contenido` es Markdown: el `StructuralChunker` ya corta por
  encabezados y conserva el rango de páginas, así que las citas siguen
  funcionando sin cambios.

## 7. Privacidad

- Hoy solo salen del servidor fragmentos, y solo al responder. **Con la
  lectura activa sale el documento completo al importarlo.**
- Texto del aviso, en la configuración y en el diálogo de subida:
  *"Con la lectura con IA activa, los PDF completos se envían a
  {proveedor} para transcribirlos. Apágala si tus documentos no pueden
  salir del servidor; en ese caso solo se lee el texto digital."*
- Activar la lectura no reprocesa documentos existentes. Solo aplica a
  lo que se suba después o a lo que se envíe con "Leer con IA".

## 8. Frontend

### 8.1 Configuración en la pantalla de Conocimiento

Botón **"Configuración"** en el encabezado de `CompanyKnowledgeView.vue`.
Es el punto que hoy falta: no hay dónde activar la lectura con IA.
Abre un diálogo con:

- Interruptor **"Leer PDF con IA (tablas, imágenes y escaneos)"**.
- Proveedor y modelo que se usarán, en solo lectura, con un enlace a la
  pantalla de proveedores.
- Costo estimado por página, o *"Costo no disponible: el modelo no tiene
  precios configurados"*.
- El aviso de privacidad (§7).
- Si `available = false`: interruptor deshabilitado y el motivo (sin
  proveedor activo o credencial no compatible).
- Con Claude por sesión local o token OAuth: *"La lectura consume el
  límite de tu suscripción de Claude. Una carga grande puede dejar el chat
  sin servicio hasta que el límite se renueve."* El costo se muestra como
  referencia de precio de lista.

### 8.2 Diálogo de subida (`CompanyDocumentUploadDialog.vue`)

- Por cada PDF, al elegirlo, se cuentan las páginas **en el navegador**
  con `pdf-lib` (MIT), cargado con import dinámico solo en este diálogo.
- Cada archivo muestra *"20 páginas · se leerá con IA · ~US$0,01"*.
- Arriba de la lista, el total del lote: *"12 PDF · 430 páginas · ~US$0,25"*.
- Estimación = páginas × `estimated_usd_per_page`. Se muestra como
  aproximada.
- Con la lectura apagada o no disponible: *"se leerá solo el texto
  digital"*, sin costo.
- No hay casilla por archivo.

### 8.3 Tabla y detalle de documentos

- Columna o etiqueta **"Leído con"**: `IA`, `Texto` o `Mixto`.
- Durante el proceso: *"Leyendo con IA: página 7 de 20"* y después
  *"Indexando…"*.
- Acción **"Leer con IA"**:
  - destacada en documentos `no_text`;
  - disponible en el menú de cualquier PDF (releer con IA).
  - Confirma con el costo estimado del documento.
- En el detalle: páginas leídas con IA, páginas que cayeron al respaldo
  y costo.

### 8.4 Módulo de uso

- Nueva fuente **"Lectura de documentos"**, desde
  `company_document_ai_reads`: `document_reading` en el reporte global,
  con páginas, pedidos, tokens y costo por proveedor y modelo. Respeta los
  filtros de período, proveedor, modelo y cliente (por la base de quien
  subió el documento).
- **Implementado aparte del chat**: `totals` y los cortes existentes
  siguen siendo solo del chat, para no mezclar métricas por respuesta. La
  tarjeta del costo total suma los dos y muestra el desglose "Chat ·
  Documentos".
- Se atribuye al administrador que subió el documento.
- No entra en el ranking de conversaciones.

## 9. Casos límite

| Caso | Comportamiento |
|---|---|
| PDF de fotos, sin texto | Todas las páginas a la IA. Hoy quedaba `no_text`. |
| Marca de agua de app de escaneo | La IA la ignora por la regla 5; en las métricas se quita con la remoción de líneas repetidas. |
| Página girada | Regla 9 del prompt. |
| Foto borrosa | Partes `[ilegible]` o `legible = false`. Si todo el documento es ilegible, queda `no_text` con el código `ai_unreadable`. |
| PDF cifrado | Igual que hoy: `pdf_encrypted`, no se envía. |
| Proveedor cae a mitad del documento | Las páginas faltantes usan el respaldo. Queda `mixed` y se puede releer con IA después. |
| Se desactiva el proveedor con documentos en cola | La política responde "texto" en los que falten. |
| Reemplazar el archivo | Versión nueva: páginas nuevas y lectura nueva. |
| 50 PDF de una vez | Cola: uno a la vez, 3 tramos en paralelo por documento. Unas 430 páginas tardan 10–20 minutos, en segundo plano. |
| Documento en inglés | Se transcribe en inglés (regla 1). El modelo de embeddings es multilingüe. |

Nuevos `DocumentStatusCode`: `ai_unreadable`. Los motivos por página
(`page_too_large`, `ai_invalid_json`, `ai_unavailable`) van en
`company_document_pages.ai_error` y no cambian el estado del documento.

## 10. Hoja de ruta

| Fase | Qué decide la política | Qué ve el usuario | Entra cuando |
|---|---|---|---|
| **4 · Todo con IA** (esta) | Interruptor encendido y proveedor usable → todas las páginas a la IA. Si no, todas a `pypdf`. | Interruptor, estimado, "Leído con IA". | Ahora. |
| **5 · Mixto automático** | Páginas con texto suficiente y sin imágenes grandes → `pypdf`; el resto → IA. Umbrales calibrados con §11. | **La pantalla no cambia**: baja el costo y aparece "Mixto: 12 de 40 páginas con IA". | Cuando §11 muestre omisiones de la IA en páginas digitales o cuando el costo lo justifique. |
| **6 · Casos difíciles** | Además detecta OCR basura del escáner (porcentaje de palabras reconocibles). | Opcional: tope de gasto mensual, modo económico por lotes (OpenAI Batch, a mitad de precio), modelo de lectura propio por proveedor. | Según demanda. |

- El interruptor significa lo mismo en todas las fases: *usar IA donde
  sirva*. En la Fase 4 eso es todo el documento; desde la Fase 5, SAVI
  elige.
- La Fase 5 solo implementa una nueva `PageRoutingPolicy`
  (`ThresholdPolicy`) con los umbrales medidos. No cambia el esquema, la
  API ni la interfaz.

**Fuera de esta hoja de ruta** (specs aparte, ya analizados):
- importar conocimiento desde una URL o el sitio web de la empresa, con
  actualización;
- perfiles de redes sociales: cuentas propias por OAuth de Meta primero;
  conectores de terceros como opción del cliente.

## 11. Medición para decidir la Fase 5

### 11.1 Datos

Salen de `company_document_pages`: método, tipo de página, `legible`,
`pypdf_chars`, `image_count` y `max_image_pixels`. El texto de `pypdf` no
se guarda: se vuelve a extraer del blob cuando se analiza, porque es
gratis.

### 11.2 Script `backend/scripts/analyze_page_reading.py`

Sobre las páginas con `method = ai` y `pypdf_chars ≥ 200` (páginas
digitales):

- **Cobertura**: porcentaje de palabras de `pypdf` (normalizadas, sin
  stopwords) presentes en el texto de la IA. Mediana y percentil 10.
- **Aporte**: porcentaje de páginas donde la IA agregó tablas o bloques
  `[Imagen: …]` que `pypdf` no tenía.
- Distribución de `pypdf_chars` y `max_image_pixels` por `page_type`,
  para proponer los umbrales de la `ThresholdPolicy`.
- Costo real por página y por proveedor.

### 11.3 Regla de decisión

| Resultado | Decisión |
|---|---|
| Cobertura mediana ≥ 98 % y P10 ≥ 95 % | La IA es fiel. La Fase 5 se hace solo si el costo lo pide. |
| Cobertura P10 < 95 % | La IA omite texto en páginas digitales. Se prioriza la Fase 5. |
| Aporte alto en páginas digitales | Las páginas digitales con imágenes grandes siguen yendo a la IA en la Fase 5. |

## 12. Tests

**Unitarios**
- Partición en tramos: límite de páginas, límite de MB, página
  individual más grande que el tope.
- Parseo y validación del JSON: páginas faltantes, números fuera del
  tramo, JSON inválido con un reintento.
- Políticas `AllAiPolicy` y `TextOnlyPolicy`.
- `ReadPdfPagesUseCase` con un lector falso:
  - respaldo por tramo;
  - reutiliza páginas guardadas;
  - retoma después de un corte;
  - concurrencia acotada.
- Cálculo de `reading_method` y de `ai_cost_usd`; costo `NULL` sin
  precios.
- Métricas de §5.3 sobre PDF de fixture (digital, escaneado, mixto).

**Integración (Postgres y SQLite)**
- Migración: las tablas y columnas nuevas y el índice.
- Fin a fin con lector falso: subir un PDF escaneado → `ready`,
  `reading_method = ai`, fragmentos con páginas correctas.
- Reprocesar no llama al lector.
- `read-with-ai` descarta las páginas `ai` y las vuelve a leer.
- Uso: las filas de `company_document_ai_reads` aparecen en totales y en
  el corte por proveedor.
- Permisos: configuración y `read-with-ai` solo para administradores.

**Frontend (Vitest)**
- Estimador del diálogo: páginas × precio, total del lote, sin precios y
  con la lectura apagada.
- Diálogo de configuración: interruptor, estado no disponible y aviso.

**E2E (Playwright, `workers: 1`)**
- Subir el PDF escaneado de fixture con la lectura activa → "Leído con
  IA" y la pregunta del chat cita la página.
- Con un proveedor real, **una sola** corrida por proveedor, con el PDF
  más chico, para no gastar de más (Claude al final).

## 13. Verificación final

- `uv run lint`, `uv run typecheck` (Pyright strict) y `uv run pytest`.
- `vue-tsc`, Biome, Vitest y build del frontend.
- Corpus del spike cargado con cada proveedor. Por cada uno se registra:
  - páginas;
  - costo real contra el estimado;
  - tiempo;
  - diez preguntas sobre las fichas técnicas, con respuesta y página
    citada correctas.
- Actualizar `00-prd.md` §3 (el OCR deja de ser un no objetivo) y la
  sección "Estado" del PRD.
