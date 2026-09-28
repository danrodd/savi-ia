# Fase 5 — Importar conocimiento desde la web

> Parte de: [PRD — Conocimiento de la empresa](00-prd.md)
> Estado: **implementada con descarga simple (2026-09-28)**. Batería de punta
> a punta **44/44** ([`bateria-web.md`](bateria-web.md)). Lo que cambió
> respecto de esta especificación está en §15. Spike:
> [`spike-web.md`](spike-web.md).
> **Orden acordado (2026-09-23):** primero una prueba con sitios reales de
> clientes usando solo descarga simple y el pipeline actual (subir el
> Markdown extraído y preguntar); si da buenos resultados, se implementa
> la fase **solo con descarga simple**, y la detección "necesita
> navegador" queda como aviso. El navegador (280–610 MB de RAM mientras
> renderiza, +115 MB de instalador) entra después como componente
> opcional, solo si los datos de clientes lo justifican.
> **Prueba con sitios de clientes hecha**
> ([`prueba-sitios-clientes.md`](prueba-sitios-clientes.md)): seo-erp.com,
> surandina.com.co y farmaciasdesimilares.com, **22/24** con descarga
> simple; ninguno necesitó navegador. Sumó a la extracción la limpieza de
> plantilla por repetición, `schema.org`, la elección de secciones del
> sitemap y la corrección de un bug del fragmentador de Markdown.
> Cambio visible: el administrador agrega una página o el sitio web de la
> empresa, SAVI lo lee, lo mantiene actualizado y responde con ese
> contenido citando la página con su link.
> Skills a leer antes de codear: `enterprise-backend-fastapi`,
> `savi-backend-patterns` (worker en el `lifespan`) y, en el frontend,
> `vue-best-practices` y `vue-pinia-best-practices`.
> Numeración: las "Fase 5" y "Fase 6" de la hoja de ruta de
> [`04`](04-fase-lectura-pdf-con-ia.md) §10 son etapas de la lectura de PDF
> (modo mixto y casos difíciles), no fases del módulo.

## Resultado esperado

- [x] Spike (§12): detección ✔ en 11 de 11 páginas; extracción híbrida; consumo medido; licencias ✔.
- [x] Alta de una **página** o de un **sitio completo**, con los mismos permisos que un documento (todos, administradores, por módulo, por base).
- [x] Vista previa antes de importar: páginas encontradas, secciones del sitemap, avisos y texto de muestra.
- [x] Descubrimiento de páginas por sitemap y, si no hay, siguiendo links del mismo dominio, con topes.
- [ ] Lectura en cascada con navegador: **diferida** (§15). Solo descarga simple; el indicio de contenido por JavaScript queda como aviso.
- [x] Extracción del contenido principal a Markdown, sin menú, pie ni banners; el pie se guarda una vez en la información general.
- [x] Cada página entra al pipeline actual como documento: fragmentos, índice, permisos, citas.
- [x] Cita con el título de la página **y su link**.
- [x] Refresco manual y automático; solo reprocesa lo que cambió; da de baja páginas que desaparecen.
- [x] Protección contra SSRF, `robots.txt`, topes de tamaño, tiempo y páginas.
- [x] Consumo acotado en equipos modestos (§7): una fuente a la vez, un hilo de extracción, sin navegador.
- [x] Tests (§13) y batería de punta a punta con un sitio de prueba local.

---

## 1. Contexto y decisión

### 1.1 Qué pasa hoy

- El conocimiento de la empresa entra solo como archivo (PDF, TXT o
  Markdown) subido a mano.
- La información pública de la empresa (servicios, precios, sedes,
  horarios, políticas publicadas) vive en su sitio web y cambia sin
  aviso. Subirla a mano como archivo queda desactualizada.
- El pipeline de documentos (fragmentación, embeddings, índice en
  memoria, permisos por rol y base, versiones, citas) está probado de
  punta a punta ([baterías](bateria-ciclo-vida.md)).

### 1.2 Decisión

**Una página web es un documento más. Lo nuevo es traerla y quedarse con
el texto útil; de ahí en adelante se usa el pipeline actual.**

```
URL → descubrir páginas → leer (simple o con navegador) → extraer texto principal → Markdown
    → documento (origen web) → pipeline actual: fragmentos, índice, permisos, citas
```

- **Con código, no con IA.** El HTML ya es texto estructurado: extraerlo
  es gratis, rápido, exacto y no manda nada a un proveedor. La IA solo
  tendría sentido para texto dentro de imágenes, y queda para una etapa
  posterior (§14).
- **El navegador solo donde hace falta.** La mayoría de los sitios
  (WordPress, SSR, SSG) traen el contenido en el HTML. El navegador se
  usa en los sitios que cargan contenido con JavaScript después de abrir
  (§3), y la decisión se toma **por sitio**, con una muestra, no en cada
  página.
- **Redes sociales: fuera de esta fase.** Bloquean el scraping, piden
  login y sus términos lo prohíben. La vía es su API oficial con permiso
  del dueño de la cuenta (spec aparte).

### 1.3 Alternativas descartadas

| Alternativa | Por qué no |
|---|---|
| Pasar cada página por la IA | Costo por página en cada refresco, lento, puede resumir u omitir (grave en precios y horarios), y manda contenido al proveedor sin necesidad. |
| Navegador para todas las páginas | 10–50 veces más lento y mucha más memoria, para obtener lo mismo en la mayoría de los sitios. |
| Llamar directo a la API interna del sitio (p. ej. la del pricing) | Suele pedir tokens o cabeceras del propio sitio y se rompe cuando el sitio cambia. |
| Decidir el modo en cada página | Duplica el trabajo en cada refresco. La decisión por sitio se toma una vez y el administrador la ve. |
| Convertir el HTML completo a texto (sin extraer el contenido principal) | Cada fragmento vendría con el menú, el pie y los banners repetidos, y la búsqueda empeora. |

## 2. Alcance

**Entra:**
- Modo **página**: una URL.
- Modo **sitio**: una URL raíz; se descubren las páginas del mismo
  dominio (incluidos subdominios `www`).
- HTML de sitios públicos (sin login).
- PDF enlazados desde las páginas del sitio (catálogos, fichas): se
  importan con la lectura de PDF existente, incluida la lectura con IA
  si está aceptada ([Fase 4](04-fase-lectura-pdf-con-ia.md) §7.1).

**No entra:**
- Sitios que piden login o que bloquean bots de forma activa (se avisa).
- Redes sociales.
- Texto dentro de imágenes (§14).
- Seguir links a otros dominios.

## 3. Qué recibe SAVI según cómo está hecho el sitio

SAVI recibe lo mismo que un navegador en el primer instante: el HTML que
manda el servidor. Lo que se carga después en el navegador no llega con
una descarga simple. **Lo que importa no es el framework, sino dónde se
cargan los datos de cada sección.**

| Sitio | Descarga simple | Necesita navegador para |
|---|---|---|
| WordPress | Todo, casi siempre | Plugins que cargan por AJAX |
| Next.js / Nuxt con SSR, SSG o ISR (su propio Node arma el HTML) | Casi todo | Secciones que se cargan en el cliente |
| Astro (SSG o SSR) | Todo | Islas `client:only` |
| React / Vue sin SSR (SPA) | Nada: un `<div id="app">` vacío | Todo |
| Con protección anti-bots (desafío de Cloudflare) | A veces nada | A veces pasa; si no, se avisa |

Detalle de las secciones que **no** vienen en el HTML aunque el sitio
sea SSR (el caso típico: el pricing que llega de una API al abrir):

| Framework | Viene en el HTML | No viene en el HTML |
|---|---|---|
| Next.js | Server Components, `getServerSideProps`, `getStaticProps` | Componentes `"use client"` que piden datos en `useEffect`, SWR o React Query |
| Nuxt | `useFetch` / `useAsyncData` por defecto | `<ClientOnly>`, `server: false`, `ssr: false` |
| Astro | Contenido normal, islas `client:load`, `client:visible`, `client:idle` | Islas `client:only` |

Por eso la regla "salió poco texto" no alcanza: una página con el 95 %
del contenido en el HTML y el pricing cargado aparte parece exitosa.
Se detecta comparando con y sin navegador (§4.3).

## 4. Flujo

```
① Alta → ② Descubrir → ③ Decidir modo (muestra) → ④ Leer y extraer → ⑤ Pipeline actual
                                                                      ⑥ Refresco periódico
```

### 4.1 Alta y vista previa

1. El administrador ingresa la URL y elige **página** o **sitio**,
   permisos (como un documento), refresco (**manual**, **diario** o
   **semanal**) y modo de lectura (**automático**, **sin navegador** o
   **con navegador**).
2. **Vista previa** (`POST /admin/company-web-sources/preview`), sin
   guardar nada:
   - valida la URL (§6.1) y `robots.txt`;
   - cuenta las páginas que encontraría (sitemap o links, hasta el tope);
   - corre la muestra del §4.3 y muestra el modo detectado;
   - muestra el título y los primeros ~500 caracteres extraídos de la
     página principal, para que el administrador vea qué va a aprender
     SAVI.
3. Al confirmar se crea la fuente y se encola el primer rastreo.

### 4.2 Descubrir las páginas (modo sitio)

En orden, lo primero que funcione:

1. **Sitemap**: el que indica `robots.txt` (`Sitemap:`), `/sitemap.xml`,
   `/sitemap_index.xml` o `/wp-sitemap.xml`. Admite índices de sitemaps
   y `.xml.gz`. Da la lista oficial y la fecha de modificación.
2. **Links**: recorrido en anchura desde la URL raíz, mismo dominio,
   hasta la profundidad máxima (3).

En los dos casos:
- Normaliza URLs: sin `#fragmento`, sin parámetros de seguimiento
  (`utm_*`, `gclid`, `fbclid`), con la URL canónica si la página la
  declara.
- Excluye: login, registro, carrito, checkout, cuenta, búsqueda,
  feeds, archivos que no sean HTML o PDF, paginación de etiquetas y
  categorías (`/tag/`, `/category/…/page/N`), y lo que `robots.txt`
  prohíba.
- Respeta el tope de páginas por fuente (200 por defecto). Si hay más,
  prioriza el sitemap por fecha y avisa "se importaron 200 de 540".

### 4.3 Decidir el modo de lectura (por sitio, una vez)

Solo en modo **automático** y solo si el navegador está disponible (§7):

1. Toma una muestra de 3 a 5 páginas: la raíz y las que parezcan de
   precios, planes, productos o servicios (por la URL o el texto del
   link).
2. Lee cada una con descarga simple y con navegador, y extrae el texto
   principal de las dos.
3. Si el navegador aporta **bastante más texto** en alguna página (umbral
   inicial: +30 % de palabras o +300 palabras; se calibra en el spike),
   el sitio queda **con navegador**. Si no, **sin navegador**.
4. Guarda la decisión, la fecha y el motivo ("en /planes el navegador
   encontró 420 palabras más"). La pantalla lo muestra.

La decisión se repite al refrescar solo si el administrador lo pide o si
cambió mucho el texto de la muestra. Con modo forzado, no hay muestra.

En modo **página**, la muestra es esa misma página.

### 4.4 Leer y extraer cada página

Una cola por fuente, página por página:

1. **Descarga** según el modo del sitio:
   - **Simple**: `httpx`, con User-Agent propio (`SAVI-Knowledge/<versión>`),
     redirecciones validadas (§6.1), tope de tamaño y de tiempo.
   - **Navegador**: abre la página, espera a que la red quede quieta
     (máx. 5 s), desplaza hasta el final para cargar lo perezoso y
     toma el HTML resultante. Bloquea imágenes, fuentes, hojas de estilo,
     video, trackers y service workers (§7).
2. **Extracción híbrida** ([spike](spike-web.md) §2): se corren dos
   extractores y se queda el que saca más texto:
   - **estructural**: `<main>` (o el `body`) sin `script`, `style`, `nav`,
     formularios, banners de cookies ni el `header`/`footer`/`aside` de
     la página (sí se conservan los que están dentro de `<article>` o
     `<main>`), convertido a Markdown con `markdownify`. Conserva las
     tarjetas de precios y las listas cortas, que `trafilatura` descarta;
   - **`trafilatura`**: mejor cuando el contenido no está en `<main>`.
   Además: título de la página, idioma y URL canónica. Al rastrear un
   sitio completo, las líneas que aparecen en más de la mitad de sus
   páginas se quitan como plantilla.
3. **Descarte**:
   - texto extraído vacío o casi vacío → la página queda
     `no_text` con un motivo ("la página no tiene texto" o "necesita
     navegador" si el modo es simple y hay indicios de JS);
   - mismo contenido que otra página de la fuente (hash) → no se duplica.
4. **PDF enlazados** del mismo dominio: se descargan con los mismos
   límites y entran como documentos PDF de la fuente.

### 4.5 Pipeline actual

Cada página es un `CompanyDocument` con:
- `media_type = text/markdown` y el Markdown extraído como blob, más un
  encabezado con el título y la URL;
- los permisos de la fuente (visibilidad, módulos, bases);
- el vínculo a su fuente y su URL (§5.2).

De ahí en adelante no cambia nada: fragmentos, embeddings, índice,
filtro de permisos antes de rankear, citas. **No se agrega ninguna tool
MCP**: se consulta con `consultar_conocimiento` y `tipo: "documentos"`.

### 4.6 Refresco

- **Automático** según la frecuencia de la fuente, en una **ventana
  nocturna** configurable (por defecto 01:00–05:00, hora del servidor),
  para no competir con el chat en horario de uso.
- **Manual** con un botón, en cualquier momento.
- Por página:
  1. pedido condicional con `If-None-Match` / `If-Modified-Since`; `304`
     → sin cambios;
  2. si descargó, compara el hash del texto extraído: igual → sin
     cambios (solo actualiza la fecha);
  3. distinto → versión nueva, igual que "reemplazar" (el índice la
     publica al procesarla).
- **Páginas nuevas** en el sitemap o en los links: se agregan.
- **Páginas que desaparecen** (404/410, o que ya no están en el sitemap):
  se marcan; a la **segunda** vez seguida se dan de baja (el documento se
  borra y sale del índice). Un error pasajero (5xx, timeout) no cuenta.
- Si el sitio entero falla (DNS, 5xx en la raíz), la fuente queda con
  error y **se conserva lo último bueno**: SAVI sigue respondiendo con
  la versión anterior.

## 5. Backend

### 5.1 Piezas nuevas en `app/modules/company_knowledge/`

| Capa | Pieza | Responsabilidad |
|---|---|---|
| `domain/entities` | `WebSource`, `WebPage` | Fuente (URL, modo, permisos, refresco, modo de lectura detectado) y página (URL, documento, validadores HTTP, hash, bajas). |
| `domain/interfaces` | `WebFetcher` (puerto) | `fetch(url, conditional) -> FetchResult` (HTML o PDF, estado, validadores). Implementaciones: simple y con navegador. |
| `domain/interfaces` | `ContentExtractor` (puerto) | `extract(html, url) -> ExtractedPage` (Markdown, título, canónica, idioma). |
| `domain/interfaces` | `PageDiscoverer` (puerto) | Sitemap y links, con normalización y exclusiones. |
| `domain/interfaces` | `WebSourceRepository` | Fuentes y páginas. |
| `domain/services` | `RenderModeDecision` | Regla del §4.3 sobre los textos de la muestra. Pura, testeable. |
| `application/use_cases` | `PreviewWebSource`, `CreateWebSource`, `UpdateWebSource`, `DeleteWebSource`, `RefreshWebSource`, `CrawlWebSource` | Alta, vista previa, edición (propaga permisos a sus documentos), baja (borra sus documentos), refresco manual y el rastreo (§4.2–4.6). |
| `infrastructure/web/` | `safe_http.py` | Cliente `httpx` con la validación de destino del §6.1 en cada conexión y redirección. |
| `infrastructure/web/` | `static_fetcher.py`, `browser_fetcher.py` | Descarga simple y con Playwright (§7). |
| `infrastructure/web/` | `trafilatura_extractor.py`, `discovery.py`, `robots.py` | Extracción, sitemap/links, `robots.txt`. |
| `infrastructure/` | worker de rastreo | Tarea en el `lifespan`, como el worker de documentos: toma fuentes pendientes o vencidas, una a la vez. |

- El rastreo **crea o actualiza documentos** y los deja `pending`; el
  worker de documentos existente los procesa. No se duplica el pipeline.
- Los documentos de una fuente web **no pasan por el control de
  duplicados por `sha256`** de la subida manual: se deduplican dentro de
  la fuente (§4.4).
- Editar los permisos de la fuente los propaga a sus documentos con
  `update_access_metadata` + `index.update_metadata`, igual que editar
  un documento. Aplica en la siguiente pregunta.

### 5.2 Modelo de datos

**`company_web_sources`** (nueva)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID | PK |
| `url` | `String(2048)` | URL ingresada, normalizada. |
| `mode` | `String(8)` | `page` \| `site` |
| `title` | `String(200)` | Del sitio o puesto por el administrador. |
| `render_mode` | `String(8)` | `auto` \| `static` \| `browser` (elegido) |
| `detected_render` | `String(8)` null | `static` \| `browser` (resultado de la muestra) |
| `detection_reason` | `String(300)` null | Texto para la pantalla. |
| `refresh` | `String(8)` | `manual` \| `daily` \| `weekly` |
| `max_pages` | `Integer` | Por defecto 200. |
| `visibility`, `modules`, `all_databases` | como `company_documents` | Plantilla de permisos. |
| `status` | `String(16)` | `pending` \| `crawling` \| `ready` \| `failed` |
| `status_code`, `status_message` | null | Motivo estable y texto. |
| `page_count`, `skipped_count` | `Integer` | Importadas y descartadas en el último rastreo. |
| `last_crawl_started_at`, `last_crawl_finished_at`, `next_refresh_at` | `UtcDateTime` null | |
| `created_by_login`, `created_by_database_id` | | Como los documentos. |
| `created_at`, `updated_at`, `deleted_at` | | Baja lógica. |

**`company_web_source_databases`** (nueva): bases de la fuente cuando
`all_databases = false`, como `company_document_databases`.

**`company_web_pages`** (nueva)

| Columna | Tipo | Notas |
|---|---|---|
| `document_id` | FK `ON DELETE CASCADE` | PK. El documento que la representa. |
| `source_id` | FK | Índice. |
| `url` | `String(2048)` | Única por fuente. |
| `canonical_url` | `String(2048)` null | |
| `fetch_method` | `String(8)` | `static` \| `browser` |
| `etag`, `last_modified` | null | Validadores HTTP. |
| `content_hash` | `String(64)` | Hash del Markdown extraído. |
| `missing_count` | `Integer` | Veces seguidas que no se encontró. |
| `last_fetched_at`, `last_changed_at` | `UtcDateTime` | |

**`company_documents`**: nueva columna `source_kind` (`upload` \| `web`,
por defecto `upload`). La tabla de documentos de la pantalla muestra solo
`upload`; las páginas web se ven dentro de su fuente.

### 5.3 Configuración (`Settings`)

| Variable | Defecto | |
|---|---|---|
| `COMPANY_WEB_MAX_SOURCES` | 20 | Fuentes por instalación. |
| `COMPANY_WEB_MAX_PAGES_PER_SOURCE` | 200 | Tope por fuente (el administrador puede bajarlo). |
| `COMPANY_WEB_MAX_DEPTH` | 3 | Profundidad al seguir links. |
| `COMPANY_WEB_MAX_PAGE_MB` | 5 | HTML; los PDF usan el tope de documentos. |
| `COMPANY_WEB_FETCH_TIMEOUT_S` | 20 | Descarga simple. |
| `COMPANY_WEB_RENDER_TIMEOUT_S` | 5 | Espera de red quieta en el navegador (spike: 5 s alcanza y evita esperar a la analítica). |
| `COMPANY_WEB_BROWSER_MIN_FREE_MB` | 1024 | Memoria disponible mínima para abrir el navegador. |
| `COMPANY_WEB_REQUEST_DELAY_S` | 1.0 | Pausa entre pedidos al mismo sitio. |
| `COMPANY_WEB_REFRESH_WINDOW` | `01:00-05:00` | Ventana del refresco automático. |
| `COMPANY_WEB_BROWSER` | `auto` | `auto` \| `off` (§7) |

### 5.4 API

| Endpoint | |
|---|---|
| `POST /admin/company-web-sources/preview` | Vista previa (§4.1). No guarda nada. |
| `POST /admin/company-web-sources` | Alta; encola el primer rastreo. |
| `GET /admin/company-web-sources` | Lista con estado, páginas, último refresco y modo. |
| `GET /admin/company-web-sources/{id}` | Detalle con sus páginas (URL, estado, fecha, método). |
| `PATCH /admin/company-web-sources/{id}` | Título, permisos, refresco, modo de lectura, tope. |
| `POST /admin/company-web-sources/{id}/refresh` | Refresco manual (409 si ya está rastreando). |
| `DELETE /admin/company-web-sources/{id}` | Baja: borra sus documentos y los retira del índice en el acto. |

Todos exigen administrador, como los de documentos. Aplican los límites
de subida por usuario existentes al alta y al refresco manual.

### 5.5 Chat y citas

- La fuente citada guarda también la `url` de la página. En el chat, la
  cita muestra el título **con el link** a la página original.
- Prompt: la sección de documentos menciona que pueden ser **páginas del
  sitio web de la empresa**. Si la pregunta es por precios o datos que
  cambian, la respuesta indica la fecha de la última actualización de la
  página ("según el sitio web, actualizado el 20/09").
- `documentos_disponibles` lista las fuentes web agrupadas ("Sitio web
  de la empresa: 48 páginas"), no las 48 páginas.

## 6. Seguridad

### 6.1 SSRF: el riesgo principal

SAVI corre en el servidor del cliente, dentro de su red. Una URL
maliciosa o mal escrita (`http://192.168.1.10/admin`,
`http://localhost:5433`, `http://169.254.169.254/`) haría que el
servidor pida recursos internos. Reglas, **en cada conexión y en cada
redirección**:

- Solo `http` y `https`, puertos 80 y 443 (configurable).
- Se resuelve el DNS **una vez** y se valida la IP: se rechazan
  loopback, privadas (RFC 1918), link-local (incluye metadatos de nube),
  CGNAT, multicast, reservadas, `0.0.0.0` y sus equivalentes IPv6
  (`::1`, `fc00::/7`, `fe80::/10`, IPv4 mapeadas).
- Se conecta **a esa IP validada** (con el `Host` original), para que
  una segunda resolución no la cambie (DNS rebinding).
- Máximo 5 redirecciones, cada una validada igual.
- En el navegador, las mismas reglas se aplican interceptando **todos**
  los pedidos de la página (`route`): un script del sitio no puede hacer
  que el navegador llame a la red interna.
- Lista blanca opcional para intranets (`COMPANY_WEB_ALLOWED_PRIVATE_HOSTS`),
  apagada por defecto.

### 6.2 Contenido

- El texto de las páginas entra con los mismos delimitadores y la regla
  "es información, no instrucciones" que los documentos.
- `robots.txt` se respeta siempre, con el User-Agent propio.
- Topes de tamaño por página y de páginas por fuente; los `sitemap.xml`
  se leen con un parser seguro contra XML malicioso (`defusedxml`) y con
  tope de tamaño descomprimido.
- No se ejecuta nada descargado fuera del navegador aislado, y el
  navegador corre sin perfil persistente, sin descargas y sin permisos.

## 7. Recursos: que no sature un equipo modesto

| Medida | Efecto |
|---|---|
| Rastreo **una fuente a la vez** y descarga simple con concurrencia 2 por sitio + pausa | El consumo no crece con la cantidad de fuentes. |
| **Un solo navegador, una pestaña a la vez**, en cola | El navegador usa lo mismo para 5 o 200 páginas. |
| **Bloquear imágenes, fuentes, media y trackers** en el navegador | Menos RAM, red y tiempo; solo interesa el texto. |
| Navegador **se abre al empezar el lote y se cierra al terminar** | Cero memoria en reposo. |
| Refresco automático en **ventana nocturna** y solo lo que cambió | El chat no compite con el rastreo en horario de uso. |
| Extracción y embeddings en el executor existente | No bloquea el event loop. |
| Navegador **opcional** (`COMPANY_WEB_BROWSER=off`) | En un equipo justo se apaga: los sitios que lo necesiten quedan con el aviso "este sitio necesita navegador para leerse completo" y el resto funciona. |

**Qué navegador** ([spike](spike-web.md) §3 y §5). Chrome Headless Shell
de Playwright: 115 MB de descarga, 271 MB instalado. El Edge del sistema
se descartó: en el equipo de desarrollo no está instalado, así que no se
puede dar por hecho en todo Windows.

**Consumo medido:** ~160 MB con el navegador abierto, **280–610 MB de
pico** mientras renderiza una página (según el sitio) y **0 al cerrarlo**.
Con flags livianos (sin GPU, sin aislamiento por sitio, un proceso de
render). **Guarda de memoria:** si hay menos de
`COMPANY_WEB_BROWSER_MIN_FREE_MB` disponible, el navegador no se abre, la
página se reintenta más tarde y la pantalla lo avisa.

**Cómo llega a la instalación:** pendiente de decisión (spike §5).
Recomendación: componente opcional del instalador, desmarcado por
defecto.

## 8. Frontend

### 8.1 Pantalla de Conocimiento

- Nueva pestaña **"Sitios web"** junto a "Documentos".
- Lista de fuentes: título, URL, tipo (página o sitio), páginas
  importadas, estado, último refresco, próximo refresco y una etiqueta
  **"Con navegador"** cuando corresponda (con el motivo en un tooltip).
- Acciones: refrescar ahora, editar, eliminar (con confirmación que dice
  cuántas páginas se borran).

### 8.2 Diálogo "Agregar sitio o página"

1. URL y tipo (página o sitio completo).
2. Botón **"Revisar"** → vista previa: páginas encontradas (y si se
   aplicará el tope), modo detectado con su motivo, título y texto de
   muestra, advertencias (robots, sitio que pide login, anti-bots).
3. Permisos (mismo componente que la subida), refresco y, en opciones
   avanzadas, modo de lectura y tope de páginas.
4. **"Importar"**.

### 8.3 Detalle de una fuente

Tabla de páginas: URL (link), título, estado, método (simple o
navegador), última actualización y motivo si se descartó. Filtro por
estado.

### 8.4 Chat

Las fuentes web se muestran con un ícono de link y abren la página en
una pestaña nueva.

## 9. Casos límite

| Caso | Comportamiento |
|---|---|
| WordPress con sitemap de Yoast | Sitemap; descarga simple; sin navegador. |
| Next.js con pricing cargado en el cliente | La muestra detecta más texto con navegador → sitio "con navegador". |
| SPA de React sin SSR | Descarga simple vacía → la muestra decide navegador. Sin navegador disponible: aviso. |
| Astro | Descarga simple; sin navegador (salvo islas `client:only`). |
| Desafío de Cloudflare / anti-bots | Se detecta por el estado (403/503) y el contenido; la fuente queda con aviso, no se reintenta en bucle. |
| Sitio que pide login | Se detecta la redirección o el formulario de login; aviso. |
| URL interna o IP privada | Rechazada en la vista previa y en cada redirección. |
| `robots.txt` prohíbe el sitio | Aviso; no se importa. |
| Sitio con 5.000 páginas | Tope de 200 (configurable), priorizando el sitemap por fecha; aviso. |
| Página que cambia solo la fecha o un contador | El hash del texto cambia → versión nueva. Si se vuelve ruido, el spike evaluará quitar números volátiles del hash. |
| Página que desaparece | Baja a la segunda vez seguida. |
| Sitio caído al refrescar | La fuente queda con error y se conserva lo último bueno. |
| Mismo contenido en varias URLs | Se deduplica por hash dentro de la fuente. |
| PDF enlazado de 60 MB | Tope de documentos; se descarta con aviso. |
| Página en inglés | Se importa tal cual; el modelo de embeddings es multilingüe. |
| La fuente se elimina con un rastreo en curso | El rastreo se cancela; los documentos se borran. |

## 10. Costos

- **Cero por página**: la descarga, la extracción y los embeddings son
  locales. El chat cuesta lo mismo que con cualquier documento.
- Los PDF enlazados, si la lectura con IA está aceptada, cuestan lo mismo
  que subirlos a mano, con el estimado previo.
- Ancho de banda: una página de texto pesa decenas de KB; con el
  navegador sin imágenes, pocos cientos de KB.

## 11. Dependencias nuevas

| Paquete | Uso | A confirmar en el spike |
|---|---|---|
| `trafilatura` | Extracción del contenido principal | ✔ Apache 2.0 (y dependencias Apache/BSD/MIT). |
| `markdownify` | Extracción estructural a Markdown | ✔ MIT (con `beautifulsoup4`, MIT). |
| `playwright` | Navegador | ✔ Apache 2.0. Pendiente: empaquetado con PyInstaller y forma de instalar el navegador. |
| `defusedxml` | Sitemaps seguros | — |

`httpx` ya está en el proyecto. `robots.txt` se lee con
`urllib.robotparser` de la biblioteca estándar.

## 12. Spike (obligatorio antes de §5)

Script `backend/scripts/spike_web_import.py`, sin tocar el módulo:

| # | Pregunta | Cómo | Criterio |
|---|---|---|---|
| S1 | ¿`trafilatura` extrae bien el contenido principal? | 8–10 sitios públicos: WordPress, Next SSR/SSG, Nuxt, Astro, una SPA. Revisar a mano el Markdown. | Sin menú ni pie repetidos; títulos y tablas legibles. |
| S2 | ¿La muestra detecta los sitios que cargan con JS? | Sitio de prueba local con: página estática, pricing cargado por `fetch` al abrir, SPA pura, isla `client:only`. Más los sitios públicos. | Detecta los casos con JS y no marca navegador en los estáticos. Calibra el umbral del §4.3. |
| S3 | ¿Cuánto tarda? | Descarga simple vs. navegador por página. | Referencia para los tiempos y el tope. |
| S4 | ¿Cuánto consume el navegador? | Edge del sistema y Chromium de Playwright, con recursos bloqueados, midiendo RAM máxima y en reposo. | ≤ 300 MB renderizando; 0 al cerrar. |
| S5 | ¿La guarda de SSRF se sostiene? | IPs privadas, `localhost`, redirección a IP interna, DNS que resuelve a interna, pedidos del navegador a la red interna. | Todos rechazados. |
| S6 | Licencias | `trafilatura` y sus dependencias. | Compatibles con distribuir el instalador. |

El resultado se documenta en `spike-web.md`, como los spikes anteriores.

## 13. Tests

**Unitarios**
- Normalización de URLs y exclusiones de descubrimiento.
- Lectura de sitemaps (índices, `.gz`, XML malicioso, tope).
- `robots.txt`.
- `RenderModeDecision` con textos de muestra.
- Guarda de SSRF: cada rango rechazado, redirecciones, IPv6, IP
  mapeada, rebinding (DNS falso).
- Refresco: 304, hash igual, hash distinto (versión nueva), 404 dos veces
  (baja), 5xx (no cuenta), sitio caído (conserva lo último).
- Propagación de permisos de la fuente a sus documentos.

**Integración**
- Servidor HTTP local de prueba con las páginas del S2 y un sitemap: alta,
  rastreo, documentos listos, búsqueda y citas con URL.
- Borrar la fuente retira todo del índice en el acto.

**Batería de punta a punta** (`scripts/bateria_web_ciclo_vida.py`,
resultado en [`bateria-web.md`](bateria-web.md)): sitio de prueba local con datos inventados (precios, horarios,
sedes), incluido un pricing cargado por JS; preguntas naturales; cambio de
un precio y refresco; página borrada; intento de SSRF; permisos por módulo
y por base; usuarios no administradores.

## 14. Hoja de ruta

| Etapa | Qué incluye |
|---|---|
| **5 · Web (esta)** | Página y sitio, sitemap y links, cascada simple → navegador, extracción, refresco, SSRF, PDF enlazados. |
| 5.1 · Texto en imágenes | Banners e infografías leídos con la IA del proveedor, con el mismo consentimiento por proveedor que los PDF. Según demanda. |
| 5.2 · Sitios con login | Credenciales por fuente o cookies. Solo si un cliente lo pide; implica guardar secretos. |
| Aparte · Redes sociales | APIs oficiales con permiso del dueño de la cuenta (Meta primero). |

## 15. Notas de implementación

Lo que cambió respecto de lo especificado arriba, y por qué.

**Alcance**
- **Sin navegador.** La prueba con sitios de clientes resolvió 22/24 con
  descarga simple y ninguno lo necesitó. §4.3 y la etiqueta "Con
  navegador" (§8.1, §8.3) no se implementaron; el indicio de contenido
  por JavaScript aparece como aviso en la vista previa y en la página.
- **Sin fecha de actualización en la respuesta** (§5.5). SAVI dice
  "según el sitio web de la empresa", pero la búsqueda no le pasa la fecha
  de la página. Pendiente si los clientes lo piden.

**Refresco (§4.6)**
- **En modo sitio no se usan pedidos condicionales.** La plantilla se
  calcula comparando todas las páginas; si algunas volvían `304` quedaban
  fuera de la comparación, el texto limpio de las demás cambiaba y se
  creaban versiones falsas. En modo sitio se descarga todo y el hash
  decide. El modo página sí usa `If-None-Match` / `If-Modified-Since`.
- **Dos hashes por página.** El del texto detecta páginas repetidas con
  otra URL; el del contenido completo (título incluido) decide la versión.
  Con uno solo, un título nuevo o desambiguado nunca llegaba a las citas.
- **La primera vez que una página falta queda como error**, con el motivo;
  a la segunda se da de baja. Un 5xx o un error de red no cuenta y conserva
  lo último bueno.
- **Las páginas omitidas no se guardan**: la tabla de páginas va atada a un
  documento. La fuente muestra cuántas se omitieron y por qué.

**Extracción (§4.4)**
- **El pie de la página se conserva.** El extractor descarta
  `<header>`/`<footer>`, pero guarda el texto del pie (sin su menú) y el
  rastreo lo suma a la comparación de plantilla: queda una vez en
  "Información general del sitio", con un mínimo propio de 6 palabras (un
  pie con dirección y teléfono ronda las 15). Su cita lleva a la portada:
  el fragmento `#informacion-general` no existe en el sitio real.
- **Títulos repetidos se desambiguan** con la ruta ("Contáctenos ·
  contrato1"): en sitios reales varias páginas comparten título.

**Descarga**
- **Doble descompresión de gzip.** Al leer la respuesta por partes para
  cortarla en el tope de tamaño, `httpx` ya la descomprime; hay que quitar
  `content-encoding` antes de armar la respuesta final. Sin eso fallaban
  casi todos los sitios reales. Solo lo mostró la prueba en vivo.

**Frontend (§8)**
- La vista previa no se repite al excluir secciones: el número de páginas
  se recalcula en el cliente como aproximado ("unas N").
- Cambiar el máximo de páginas o las secciones de una fuente pide una
  lectura nueva al guardar; los permisos aplican en la siguiente pregunta.
- Las fuentes web del chat se abren con su link público, también en una
  conversación compartida; solo se enlazan URLs `http(s)`.
