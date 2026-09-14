# Fase 1 — Ingesta y procesamiento de documentos

> Parte de: [PRD — Conocimiento de la empresa](00-prd.md)
> Estado: **propuesta**.
> Cambio visible: documentos administrables por API, procesados e
> indexables. SAVI todavía **no** los usa en el chat (Fase 2).
> Skills a leer antes de codear: `enterprise-backend-fastapi`
> (módulo nuevo) y `savi-backend-patterns` (tarea de fondo en el
> `lifespan`).

## Resultado esperado

- [ ] Spike cerrado: modelo de embeddings elegido con datos (§2).
- [ ] Módulo `company_knowledge` con tablas, migración y registro en `bootstrap.py` / `alembic/env.py`.
- [ ] API de administración: subir, listar, ver, editar, reemplazar, reprocesar, eliminar, uso.
- [ ] Extracción de PDF, TXT y MD, con detección de PDF sin texto y cifrado.
- [ ] Fragmentación con rango de páginas y encabezado.
- [ ] Embeddings locales en un hilo dedicado, sin frenar el event loop.
- [ ] Worker de ingesta en el `lifespan`, con recuperación tras reinicio.
- [ ] Modelo empaquetado en el instalador y cargado offline.
- [ ] Tests unitarios y de integración en SQLite y Postgres.

---

## 1. Dependencias nuevas

| Paquete | Para qué | Licencia | Notas |
|---|---|---|---|
| `fastembed` | Embeddings ONNX locales | Apache-2.0 | Trae `onnxruntime`, `numpy`, `tokenizers` y `huggingface-hub`. Fijar versión exacta, como `openai==3.13.0`. |
| `pypdf` | Extracción de texto de PDF | BSD-3 | Python puro, sin binarios. **No** usar PyMuPDF (AGPL). |
| `python-multipart` | Subida `multipart/form-data` en FastAPI | Apache-2.0 | Hoy entra solo como dependencia transitiva (`uv.lock:1297`); se declara explícito porque el módulo depende de él. |

Agregar a `installer/savi.spec` los `hiddenimports` y *data files* que
requieran `fastembed`/`onnxruntime` (se descubren en el build del
spike, igual que se hizo con `openai`).

## 2. Spike: elección del modelo (obligatorio antes de §4)

### 2.1 Candidatos

| Modelo | Dim | Soporte en `fastembed` | Notas |
|---|---|---|---|
| `intfloat/multilingual-e5-small` | 384 | Modelo **custom** (`add_custom_model`, pooling mean, normalizado) | Liviano. Requiere prefijos `query: ` / `passage: `. |
| `intfloat/multilingual-e5-large` | 1024 | Nativo | Mejor calidad esperada, mucho más pesado. Mismos prefijos. |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 384 | Nativo | Referencia liviana sin prefijos. |

Los tamaños en disco y la memoria **se miden en el spike**, no se
asumen.

### 2.2 Set de evaluación (P1 del PRD)

`backend/tests/fixtures/company_knowledge/eval/`, **no versionado si
los documentos son reales del cliente** (queda en `.gitignore` con
una excepción solo para `questions.example.json`):

- 5 a 10 documentos (PDF y MD) de una empresa piloto.
- `questions.json`: 30 preguntas con `expected: [{document, pages}]`.
  Incluir 5 preguntas con términos exactos (códigos, números de acta,
  montos) y 5 que **no** tienen respuesta en los documentos.

### 2.3 Medición

Script `scripts/eval_company_knowledge.py`:

1. Procesa los documentos con el pipeline real (§5 y §6).
2. Para cada modelo, en tres modos (solo vectores, solo BM25 e híbrido
   RRF):
   - `recall@6`: el fragmento esperado está entre los 6 primeros;
   - `MRR`;
   - tiempo de indexación por página;
   - p95 de consulta;
   - memoria del índice;
   - tamaño en disco del modelo.
3. Informe en `backend/docs/company_knowledge/spike-modelo.md`.

**Criterio de elección:** el modelo más liviano cuyo modo híbrido cumpla
`recall@6 ≥ 0,85` (RNF-08). Si ninguno cumple, se revisan tamaño de
fragmento y solapamiento antes de pasar a uno más pesado.

## 3. Modelo de datos (BD del agente)

Todo con los tipos portables existentes (`UuidType`, `UtcDateTime`,
`JsonType`) y `LargeBinary` para bytes (`BYTEA` en Postgres, `BLOB` en
SQLite).

### 3.1 `company_documents`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `UuidType` PK | |
| `title` | `String(200)` NOT NULL | Por defecto, el nombre de archivo sin extensión. |
| `original_filename` | `String(255)` NOT NULL | Sanitizado: sin rutas. |
| `media_type` | `String(64)` NOT NULL | `application/pdf`, `text/plain` o `text/markdown`. Detectado por contenido (§5.1). |
| `size_bytes` | `Integer` NOT NULL | |
| `sha256` | `String(64)` NOT NULL | Del archivo original. |
| `version` | `Integer` NOT NULL default 1 | Se incrementa al reemplazar. |
| `status` | `String(16)` NOT NULL | `pending` \| `processing` \| `ready` \| `no_text` \| `failed` |
| `status_code` | `String(48)` NULL | Motivo con código estable: `pdf_encrypted`, `pdf_unreadable`, `encoding_unsupported`, `too_many_pages`, `too_many_chunks`, `index_limit_reached`, `internal_error`. |
| `page_count` | `Integer` NULL | PDF; `NULL` en texto. |
| `chunk_count` | `Integer` NOT NULL default 0 | |
| `char_count` | `Integer` NOT NULL default 0 | |
| `embedding_model` | `String(120)` NULL | Modelo con el que se generaron los vectores. |
| `visibility` | `String(16)` NOT NULL | `all` \| `modules` \| `admins` |
| `modules` | `JsonType` NOT NULL default `[]` | Valores de `ModuleCode`. Obligatorio no vacío si `visibility = modules`. |
| `all_databases` | `Boolean` NOT NULL default `true` | |
| `uploaded_by_login` | `String(50)` NOT NULL | |
| `uploaded_by_database_id` | `UuidType` NOT NULL | Identidad calificada (multi-BD §3.2). |
| `uploaded_by_user_id` | `Integer` NOT NULL | |
| `processed_at` | `UtcDateTime` NULL | |
| `deleted_at` | `UtcDateTime` NULL | Baja: ver §7.6. |
| `created_at` / `updated_at` | `UtcDateTime` NOT NULL | |

Índices:
- `uq_company_documents_sha256`: único parcial sobre `sha256 WHERE deleted_at IS NULL`.
- `ix_company_documents_status`: `(status, created_at)`, para el worker.

### 3.2 `company_document_databases`

`document_id` FK + `erp_database_id` FK → `erp_databases.id`, PK
compuesta. Solo tiene filas cuando `all_databases = false`.

### 3.3 `company_document_blobs`

`document_id` PK/FK, `content LargeBinary NOT NULL`.

**Por qué en la BD y no en disco:** un solo respaldo (`pg_dump`, o la copia
de `savi.db`) cubre todo, que es lo que documenta la Fase 1 de
plataforma. Además no hay permisos de carpetas ni rutas por modo de
despliegue, y con 20 MB por archivo el costo es aceptable. Va en tabla
aparte para que listar documentos nunca cargue bytes.

### 3.4 `company_document_chunks`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `UuidType` PK | |
| `document_id` | FK, `ON DELETE CASCADE` | |
| `ordinal` | `Integer` NOT NULL | Orden dentro del documento. |
| `page_from` / `page_to` | `Integer` NULL | Rango de páginas (PDF). |
| `heading` | `String(300)` NULL | Encabezado Markdown vigente o primera línea en mayúsculas del bloque. |
| `text` | `Text` NOT NULL | |
| `embedding` | `LargeBinary` NOT NULL | `float32` little-endian, normalizado, `dim × 4` bytes. |
| `created_at` | `UtcDateTime` NOT NULL | |

Índice: `(document_id, ordinal)`.

**Por qué bytes y no un tipo vector:** es portable entre Postgres 10+ y
SQLite sin extensiones (PRD §8.1). `numpy.frombuffer` lo reconstruye sin
copias al cargar el índice.

### 3.5 Migración

- Una revisión Alembic con las cuatro tablas, en batch mode.
- `down_revision`: head al momento de implementar (`uv run alembic heads`).
- Registrar los cuatro modelos en `_REGISTERED_MODELS` de `bootstrap.py`
  (en orden de FK) y en `alembic/env.py`.
- Verificar el índice único parcial en los dos caminos de creación de
  esquema (lección de multi-BD §6.1).

## 4. Módulo `app/modules/company_knowledge/`

```
company_knowledge/
├── domain/
│   ├── entities/company_document.py        # + DocumentChunk
│   ├── value_objects/visibility.py         # Visibility, DocumentStatus, StatusCode
│   ├── interfaces/document_repository.py
│   ├── interfaces/text_extractor.py        # extract(bytes, media_type) -> ExtractedText
│   ├── interfaces/chunker.py
│   ├── interfaces/embedder.py              # embed_passages / embed_query
│   ├── interfaces/document_index.py        # Fase 2
│   └── exceptions.py
├── application/
│   ├── requests/, responses/, dtos/
│   └── use_cases/
│       ├── upload_document.py
│       ├── update_document.py
│       ├── replace_document.py
│       ├── reprocess_document.py
│       ├── delete_document.py
│       ├── list_documents.py
│       ├── get_usage.py
│       └── process_next_document.py        # lo invoca el worker
└── infrastructure/
    ├── http/routes.py, dependencies.py
    ├── persistence/models.py, sqlalchemy_document_repository.py
    ├── extraction/pdf_extractor.py, text_extractor.py, media_type_sniffer.py
    ├── chunking/structural_chunker.py
    ├── embeddings/fastembed_embedder.py
    └── worker.py
```

## 5. Extracción

### 5.1 Detección de tipo por contenido

La extensión y el `Content-Type` del cliente **no** se confían:

| Detección | Tipo |
|---|---|
| Empieza con `%PDF-` | `application/pdf` |
| Decodifica como UTF-8 (con o sin BOM) y extensión `.md`/`.markdown` | `text/markdown` |
| Decodifica como UTF-8 | `text/plain` |
| No es UTF-8 pero decodifica como `cp1252` sin caracteres de control | `text/plain` (archivos típicos de Windows) |
| Otro | `415 unsupported_media_type` |

### 5.2 PDF (`pypdf`)

- Documento cifrado → intentar abrir con contraseña vacía. Si no se
  puede, `failed / pdf_encrypted`.
- Error de lectura → `failed / pdf_unreadable`.
- Más de `COMPANY_DOCS_MAX_PAGES` (500) → `failed / too_many_pages`.
- Texto por página con `page.extract_text()`. Se normalizan saltos de
  línea, se unen palabras cortadas por guion al final de línea y se
  eliminan encabezados y pies repetidos (líneas idénticas en más del 60%
  de las páginas).
- **Sin texto:** si el promedio es menor a 50 caracteres por página →
  `no_text` (PDF escaneado, R6 del PRD).

### 5.3 TXT y Markdown

- Normalización a `\n` y eliminación del BOM.
- Markdown: se conservan los encabezados `#` para la fragmentación. No se
  renderiza HTML.

## 6. Fragmentación (`StructuralChunker`)

| Parámetro | Default | Configurable |
|---|---|---|
| Tamaño objetivo | 900 tokens estimados (caracteres ÷ 4) | `COMPANY_DOCS_CHUNK_TOKENS` |
| Solapamiento | 120 tokens estimados | `COMPANY_DOCS_CHUNK_OVERLAP` |
| Máximo por documento | 2.000 fragmentos | `COMPANY_DOCS_MAX_CHUNKS_PER_DOC` |

Algoritmo:

1. Dividir en **bloques estructurales**: por encabezado en Markdown, por
   párrafo (línea en blanco) en TXT y por página y párrafo en PDF.
2. Acumular bloques hasta el tamaño objetivo **sin partir un bloque**,
   salvo que el bloque solo supere el tamaño. En ese caso se parte por
   oraciones.
3. Solapar el final del fragmento anterior al comienzo del siguiente.
4. Cada fragmento guarda `page_from`/`page_to` y el `heading` vigente.
5. El texto que se vectoriza es `heading + "\n" + text`, para que el
   encabezado aporte contexto. El `text` guardado queda sin el heading.

Los parámetros finales los fija el spike (§2).

## 7. Casos de uso y API de administración

Prefijo `/admin/company-documents`, todos con `SaviAdminDep`. `"admin"`
ya está en `_API_PREFIXES`.

### 7.1 `POST /admin/company-documents`: subir

`multipart/form-data`:

| Campo | Tipo | Validación |
|---|---|---|
| `file` | archivo | ≤ `COMPANY_DOCS_MAX_FILE_MB` (20). Tipo según §5.1. |
| `title` | string, opcional | 1–200 caracteres. |
| `visibility` | `all` \| `modules` \| `admins` | Obligatorio. |
| `modules` | repetido | Valores válidos de `ModuleCode`; obligatorio si `visibility = modules`, prohibido en los otros casos. |
| `all_databases` | bool | Default `true`. |
| `database_ids` | repetido | Obligatorio no vacío si `all_databases = false`; bases existentes y no eliminadas. |

Respuesta `201` con `CompanyDocumentResponse` en estado `pending`.

| Error | Status | `errorCode` |
|---|---|---|
| Archivo demasiado grande | `413` | `file_too_large` |
| Tipo no soportado | `415` | `unsupported_media_type` |
| Archivo idéntico existente | `409` | `duplicate_document`, con `existing_document_id` y `existing_title` |
| Límite de fragmentos de la instalación ya alcanzado | `422` | `index_limit_reached` |
| Validación de campos | `422` | (formato estándar) |

- El tamaño se controla **mientras se lee** el stream, no después: un
  archivo de 2 GB no puede cargarse entero en memoria para rechazarlo.
- En el `201` el worker se despierta de inmediato (§8).

### 7.2 Otros endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `""` | Lista sin bytes ni texto. Filtros: `status`, `visibility`, `module`, `database_id`, `q` (título). Orden por `created_at` desc, paginado. |
| `GET` | `/{id}` | Detalle + bases del alcance. |
| `PATCH` | `/{id}` | `{title?, visibility?, modules?, all_databases?, database_ids?}`. **No reprocesa.** Publica la actualización de metadatos al índice (Fase 2) en el acto. |
| `POST` | `/{id}/replace` | `multipart` con `file`. Nuevo `sha256` (`409` si coincide con **otro** documento), `version + 1`, reemplaza blob, borra fragmentos, `pending`. Conserva `id`, título y permisos. |
| `POST` | `/{id}/reprocess` | Borra fragmentos y vuelve a `pending`. `409` si está `processing`. |
| `DELETE` | `/{id}` | Baja (§7.6). Idempotente, `204`. |
| `GET` | `/usage` | `{documents: {total, by_status}, chunks, chunk_limit, bytes_stored, estimated_index_memory_bytes, embedding_model}` |

`CompanyDocumentResponse`: todos los campos de §3.1 excepto `sha256`,
más `database_ids` y `status_message` (texto en español derivado de
`status_code`). **Nunca** incluye contenido.

### 7.3 Cambio de modelo de embeddings

Si `embedding_model` de un documento no coincide con el modelo
configurado (actualización de SAVI con un modelo nuevo), el documento
**no** se usa en búsquedas. Al arrancar, el worker lo encola para
reprocesar automáticamente. `/usage` informa cuántos documentos quedan
pendientes por ese motivo.

### 7.4 Validación de módulos

`modules` acepta cualquier `ModuleCode`, incluidos los CORE y
`HERRAMIENTA`. La interfaz (Fase 3) muestra nombres legibles; el backend
valida contra el enum.

### 7.5 Límites de la instalación

`COMPANY_DOCS_MAX_TOTAL_CHUNKS` (50.000). El worker verifica antes de
guardar fragmentos. Si el documento haría superar el límite →
`failed / index_limit_reached`, sin guardar fragmentos parciales.

### 7.6 Baja

En **una** transacción: `deleted_at = now()`, borrar blob y fragmentos, y
quitar filas de `company_document_databases`. La fila del documento
queda, con título, fechas y visibilidad, para que las fuentes históricas
digan "documento eliminado" (P4 del PRD). El índice lo retira en el acto
(Fase 2). Un documento eliminado no se puede editar, reemplazar ni
reprocesar (`404`).

## 8. Worker de ingesta

`infrastructure/worker.py`:

- Se inicia en el `lifespan` (`main.py`) **después** de `init_catalog`.
  Se cancela y espera en el `finally`.
- Al arrancar: `UPDATE … SET status = 'pending' WHERE status = 'processing'`,
  porque un reinicio a mitad deja documentos colgados.
- Bucle: toma el documento `pending` más antiguo (en Postgres con
  `SELECT … FOR UPDATE SKIP LOCKED`), lo marca `processing` y ejecuta
  `ProcessNextDocumentUseCase`. Si no hay trabajo, espera un
  `asyncio.Event` que despierta la subida, con timeout de 60 s.
- **Todo lo que usa CPU** (extracción, fragmentación y embeddings) corre
  en un `ThreadPoolExecutor(max_workers=1)` **dedicado**, con
  `loop.run_in_executor`. Nunca en el executor por defecto, que comparten
  otras tareas.
- `onnxruntime`: `intra_op_num_threads = max(1, os.cpu_count() // 2)`.
  Así queda CPU para el chat (RNF-02).
- Embeddings en lotes de 32 fragmentos.
- Escritura de fragmentos en una transacción por documento. Si falla a
  mitad, no quedan fragmentos parciales: se hace rollback y queda
  `failed / internal_error` con log (sin contenido).
- Una excepción no controlada **nunca** detiene el worker ni la
  aplicación.
- `COMPANY_DOCS_WORKER_ENABLED=false` lo apaga (tests).

## 9. Embedder y empaquetado del modelo

`FastembedEmbedder`:

- Carga diferida en el primer uso, una vez por proceso.
- `embed_passages(texts)` antepone `passage: ` y `embed_query(text)`
  antepone `query: ` si el modelo elegido es e5.
- Vectores normalizados (L2) a `float32`.

Ubicación del modelo:

| Entorno | Fuente |
|---|---|
| Instalado | `<app>/models/<modelo>/`, cargado con `specific_model_path` y `HF_HUB_OFFLINE=1`. **Sin descargas en runtime** (RNF-06). |
| Desarrollo | `uv run download-embedding-model` (script nuevo en `[project.scripts]`) descarga a `backend/.models/`, que queda en `.gitignore`. |

`installer/build.ps1`: paso nuevo que ejecuta la descarga en staging y
copia `models/` al bundle. Si falta, el build **aborta**, igual que con el
catálogo de conocimiento. `--check-config` informa si el modelo carga.

Si el modelo no carga en runtime: la subida sigue aceptando documentos
(quedan `pending`), `/usage` informa `embedding_model_unavailable` y la
Fase 2 omite la búsqueda de documentos sin afectar el resto del chat.

## 10. Configuración (`Settings`)

| Variable | Default |
|---|---|
| `COMPANY_DOCS_MAX_FILE_MB` | `20` |
| `COMPANY_DOCS_MAX_PAGES` | `500` |
| `COMPANY_DOCS_MAX_CHUNKS_PER_DOC` | `2000` |
| `COMPANY_DOCS_MAX_TOTAL_CHUNKS` | `50000` |
| `COMPANY_DOCS_CHUNK_TOKENS` | `900` (lo ajusta el spike) |
| `COMPANY_DOCS_CHUNK_OVERLAP` | `120` |
| `COMPANY_DOCS_EMBEDDING_MODEL` | el elegido por el spike |
| `COMPANY_DOCS_MODEL_DIR` | vacío = ubicación por entorno (§9) |
| `COMPANY_DOCS_WORKER_ENABLED` | `true` |

## 11. Tests

| Test | Verifica |
|---|---|
| Detección de tipo | PDF renombrado `.txt` se trata como PDF; binario con extensión `.md` → `415`; TXT `cp1252` aceptado. |
| Límite de tamaño en stream | Un stream mayor al límite se corta sin leerse entero (cliente fake que cuenta bytes leídos). |
| Duplicado | Mismo `sha256` → `409` con el id existente; tras eliminar, se puede volver a subir. |
| Validación de permisos al subir | `modules` vacío con `visibility = modules` → `422`; `modules` con `visibility = all` → `422`; base inexistente → `422`. |
| PDF | Con texto → páginas correctas; cifrado → `pdf_encrypted`; escaneado (fixture de imagen) → `no_text`; más de 500 páginas → `too_many_pages`. Encabezados repetidos eliminados. |
| Fragmentación | No parte bloques salvo excedentes; solapamiento correcto; rango de páginas por fragmento; heading vigente en Markdown. |
| Embeddings | Dimensión y normalización; prefijos e5; bytes ↔ `numpy` sin pérdida. |
| Worker | Recupera `processing` al arrancar; transacción por documento sin parciales ante fallo; una excepción no detiene el bucle; `SKIP LOCKED` en Postgres. |
| No bloquea el event loop | Durante el procesamiento de un documento grande, una corrutina de control mide su *lag* de agenda por debajo de 50 ms (embedder fake que duerme con `time.sleep`). |
| Reemplazo | Conserva `id` y permisos, incrementa `version`, borra fragmentos viejos. |
| Baja | Borra blob y fragmentos, conserva la fila; operaciones posteriores → `404`. |
| Límite total | Documento que excede → `index_limit_reached` sin fragmentos. |
| Modelo cambiado | Documentos con otro `embedding_model` se reencolan al arrancar. |
| Portabilidad | Suite del módulo en SQLite y en Postgres (`savi_agente` de prueba). |
| Sin contenido en logs | Procesar un documento con una frase centinela no la deja en los logs capturados. |
| Permisos de API | Todos los endpoints → `403` sin admin. |

Gates: `uv run lint`, `uv run typecheck`, `uv run pytest`. Verificación
real: subir un PDF de 50 páginas en la instalación de desarrollo, medir
RNF-03 y registrar el tiempo en el informe del spike.
