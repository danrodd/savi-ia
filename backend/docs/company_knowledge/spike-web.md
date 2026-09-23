# Spike — Importar conocimiento desde la web

> Parte de: [Fase 5](05-fase-importar-desde-web.md) §12.
> Fecha: 2026-09-23. Script: `backend/scripts/spike_web_import.py`.
> Equipo: el de desarrollo (Windows 10, 16 GB de RAM), Playwright 1.63 con
> Chrome Headless Shell 153, `trafilatura` 2.2.

## Resultado

| # | Pregunta | Resultado |
|---|---|---|
| S1 | ¿`trafilatura` extrae bien? | **No sola.** Quita bien menú, pie y cookies, pero en páginas cortas descarta títulos y listas, y en páginas de precios puede descartar las **tarjetas de planes** (bloques cortos). Se decide una extracción **híbrida** (§2). |
| S2 | ¿La muestra detecta los sitios que cargan con JS? | **Sí.** Los 8 sitios públicos (WordPress, Next.js, Nuxt, Astro, SSR de Python) quedaron "sin navegador", correctamente. En el sitio de prueba, el pricing cargado por `fetch` y la SPA quedaron "con navegador". |
| S3 | ¿Cuánto tarda? | Simple: **0,3–1,3 s** por página. Navegador: **1,5–5 s** con la espera tope de 5 s; con espera de 15 s, hasta 16 s en sitios con analítica que nunca deja la red quieta. |
| S4 | ¿Cuánto consume el navegador? | **~160 MB** abierto sin páginas (incluye el driver de Playwright); **280–610 MB** de pico mientras renderiza una página, según el sitio; **0 MB** al cerrarlo. La meta de ≤ 300 MB no se cumple en sitios de marketing pesados. |
| S5 | Guarda de SSRF | Se prueba con tests unitarios al implementar (§13 de la spec); el spike no la cubre. |
| S6 | Licencias | **Todas compatibles**: `trafilatura`, `courlan`, `htmldate`, `jusText` (Apache/BSD), `lxml` (BSD), `markdownify` y `beautifulsoup4` (MIT), `playwright` (Apache 2.0), `defusedxml` (PSF). `tld` es triple (MPL 1.1 / GPL / LGPL): se usa bajo MPL. |

**Hallazgo:** en este equipo **no hay Microsoft Edge instalado**. No se
puede dar por hecho que viene en todo Windows: la opción de usar el
navegador del sistema se descarta y se usa el Chromium de Playwright.
Pesa **115 MB de descarga y 271 MB instalado**, más que lo estimado en la
spec (100–150 MB).

## 1. Detección del modo (S2)

Palabras extraídas con descarga simple y con navegador:

| Tipo | Sitio | Simple | Navegador | Decisión |
|---|---|---|---|---|
| WordPress | wordpress.org/news | 206 | 206 | sin navegador ✔ |
| WordPress | wpbeginner.com (artículo) | 3.941 | 3.941 | sin navegador ✔ |
| Next.js | nextjs.org/docs | 410 | 410 | sin navegador ✔ |
| Next.js | vercel.com/pricing | 1.470 | 1.470 | sin navegador ✔ |
| Nuxt | nuxt.com | 518 | 518 | sin navegador ✔ |
| Astro | astro.build | 481 | 480 | sin navegador ✔ |
| Astro | docs.astro.build | 98 | 98 | sin navegador ✔ |
| SSR (Python) | python.org/about | 197 | 213 | sin navegador ✔ (+16, bajo el umbral) |
| Local | página estática | 56 | 56 | sin navegador ✔ |
| Local | **pricing cargado por `fetch` al abrir** | 16 | 86 | **con navegador ✔** |
| Local | **SPA** (`<div id="app">` vacío) | 6 | 39 | **con navegador ✔** |

- Confirma lo esperado: **Next.js, Nuxt y Astro en SSR o SSG entregan
  todo el contenido con una descarga simple.** El navegador solo aportó
  en los casos que cargan con JavaScript.
- El umbral (+20 palabras y +30 %, o +300 palabras) separó bien los
  casos. Queda como valor inicial; se revisa con sitios reales de
  clientes.

## 2. Extracción (S1)

Problemas de `trafilatura` sola:

- En la página de planes del sitio de prueba, sin navegador, descartó
  el `h1` y la lista de beneficios (16 palabras de 30).
- En vercel.com/pricing, sobre el HTML renderizado, perdió los precios de
  las tarjetas de planes ("Pro · $20 /mo") y conservó la tabla de
  consumo. Es justo el caso de uso del pricing.
- Los modos `favor_precision` y `favor_recall` no lo corrigen.

Alternativa probada: **extracción estructural**. Toma `<main>` (o el
`body`), quita `script`, `style`, `nav`, formularios, banners de cookies
y el `header`, `footer` y `aside` **de la página** (no los que están
dentro de un `<article>` o de `<main>`, porque en WordPress el título de
cada entrada vive en un `<header>` del artículo), y convierte el resto a
Markdown con `markdownify`.

| Sitio | `trafilatura` | Estructural |
|---|---|---|
| Local, planes | 16 | 30 (con `h1` y beneficios) |
| vercel.com/pricing | 1.470 | 2.002 (con las tarjetas de planes) |
| wordpress.org/news | 206 | 110 |
| nuxt.com | 518 | 966 (incluye ejemplos de código) |
| python.org/about | 197 | 342 |

**Decisión: extracción híbrida.** Se corren las dos y se queda la que
extrae más texto. La estructural gana cuando hay tarjetas o listas
cortas; `trafilatura` gana en diseños donde el contenido no está en
`<main>`. El texto repetido en muchas páginas del mismo sitio (restos del
menú o del pie que se hayan filtrado) se quita al rastrear el sitio
completo: una línea que aparece en más de la mitad de las páginas es
plantilla.

## 3. Consumo del navegador (S4)

Una pestaña a la vez, bloqueando imágenes, fuentes, media y hojas de
estilo:

| Configuración (3 páginas pesadas) | Pico | Tiempo |
|---|---|---|
| Por defecto, espera de red quieta 15 s | 498 MB | 32,5 s |
| Flags livianos, espera 15 s | 413 MB | 19,5 s |
| Flags livianos + sin trackers, espera 5 s | 413–507 MB | 15,6 s |

Pico por página (flags livianos, sin trackers, espera de 5 s):

| Página | Pico |
|---|---|
| Navegador abierto, sin páginas | 160 MB |
| Local, planes | 279 MB |
| astro.build | 322 MB |
| wpbeginner.com | 350 MB |
| vercel.com/pricing | 432 MB |
| nuxt.com | 609 MB |
| Después de cerrar | 0 MB |

- Los flags livianos (sin GPU, sin aislamiento por sitio, un solo proceso
  de render) y bloquear trackers bajan el tiempo más que la memoria.
- Lo que más pesa es el DOM y el diseño de cada página, no el JavaScript:
  limitar el heap de JS no cambió el pico.
- **Ajuste de la spec (§7):** el objetivo pasa a ser "≤ ~600 MB mientras
  renderiza y 0 en reposo", más una **guarda de memoria**: si el equipo
  tiene menos de 1 GB disponible, el navegador no se abre, se reintenta
  más tarde y la pantalla lo avisa.
- Espera de red quieta con **tope de 5 s**: alcanzó para el pricing por
  `fetch` y evita esperar 15 s en sitios con analítica permanente.
- El contexto del navegador bloquea los **service workers**, que si no
  pueden hacer pedidos sin pasar por la intercepción (guarda de SSRF).

## 4. Qué cambia en la spec

- §4.4: extracción híbrida (estructural + `trafilatura`) y limpieza de
  líneas de plantilla por sitio.
- §7: Chromium de Playwright (no Edge); consumo medido; guarda de
  memoria; espera de 5 s; service workers bloqueados.
- §11: `markdownify` como dependencia (MIT).
- Queda para decidir: cómo llega el navegador a la instalación del
  cliente (§5 de este documento).

## 5. Pendiente de decisión: cómo se instala el navegador

| Opción | A favor | En contra |
|---|---|---|
| **A. Descarga bajo demanda** desde la pantalla ("Habilitar lectura de sitios con JavaScript", 115 MB) | El instalador no crece; solo lo baja quien lo necesita | Descarga un ejecutable en el servidor del cliente; algunas áreas de TI lo bloquean |
| **B. Componente opcional del instalador** (casilla en Inno Setup) | Sin descargas en tiempo de ejecución; funciona sin salida a los CDN de Playwright | El instalador pasa de su tamaño actual a +115 MB si se marca |
| **C. Siempre incluido** | Más simple | +115 MB para todos, aunque su sitio no lo necesite |

Recomendación: **B**, con la casilla desmarcada por defecto. La mayoría
de los sitios (WordPress, SSR, SSG) no lo necesita, y así no se descargan
ejecutables en el servidor del cliente.
