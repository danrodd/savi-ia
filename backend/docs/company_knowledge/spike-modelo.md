# Spike — modelo de embeddings, fragmento y umbral

> Fecha: 2026-09-15 · Estado: **decidido con set sintético**; se repite con
> documentos de la empresa piloto (P1) cuando estén.

## Decisión

| Parámetro | Valor | Cambio |
|---|---|---|
| Modelo | `intfloat/multilingual-e5-small` | Sin cambio |
| Fragmento | 900 tokens estimados, solapamiento 120 | Sin cambio |
| `COMPANY_DOCS_MIN_SIMILARITY` | **0,80** | Antes 0,82 |
| Estrategia de umbral | La actual: se descarta si coseno < umbral **y** no hay coincidencia BM25 | Sin doble umbral |

RNF-08 (recall@6 ≥ 85%) **se cumple**: 100% en modo híbrido.

Lo más importante que salió del spike: **ningún umbral absoluto separa las
preguntas sin respuesta**, con ninguno de los cuatro modelos. El umbral solo
recorta ruido. Decir "no encontré información" le corresponde al modelo de
lenguaje, que ya lo hace (verificado en Fase 2).

## En palabras simples

### Glosario

| Término | Qué es |
|---|---|
| **Embedding / modelo de embeddings** | Programa que convierte un texto en una lista de números (un vector) que representa su significado. Dos textos que dicen lo mismo con otras palabras quedan con vectores parecidos. SAVI lo corre local, sin internet. |
| **e5-small** | `intfloat/multilingual-e5-small`, el modelo de embeddings que usa SAVI. Multilingüe, 465 MB, viaja en el instalador. |
| **Fragmento** | Pedazo de un documento (unos 900 tokens ≈ 3.600 caracteres). SAVI no le pasa documentos enteros a Claude, sino los fragmentos más relevantes. |
| **Coseno (similitud)** | Puntaje de parecido entre el vector de la pregunta y el de un fragmento. Más alto = más parecido. Cada modelo tiene su propia escala: en e5 casi todo cae entre 0,78 y 0,87. |
| **BM25** | Búsqueda por palabras: puntúa los fragmentos que comparten términos con la pregunta (códigos como `POL-DEV-07`, montos). |
| **Híbrido** | Combina la búsqueda por significado (coseno) y por palabras (BM25). Es lo que usa SAVI. |
| **Umbral (`COMPANY_DOCS_MIN_SIMILARITY`)** | Un fragmento se descarta si su coseno queda **por debajo del umbral y además** no comparte ninguna palabra con la pregunta. |
| **recall@6** | De las preguntas que sí tienen respuesta, en qué porcentaje el fragmento correcto aparece entre los 6 primeros resultados (SAVI le entrega 6 a Claude). El PRD exige ≥ 85% (RNF-08). |
| **recall@1 / MRR** | Qué tan arriba queda el fragmento correcto: recall@1 = sale primero; MRR promedia 1/posición (1 = siempre primero, 0,5 = siempre segundo). |

### Qué se probó y por qué importa

La búsqueda de documentos tiene tres perillas: el **modelo**, el **tamaño de
fragmento** y el **umbral**. Antes del spike el umbral (0,82) se había puesto
a ojo, mirando un par de búsquedas en la interfaz. El spike las ajusta con
datos: una empresa ficticia con 8 documentos y 30 preguntas cuya respuesta
correcta se conoce de antemano, medidas por el mismo camino que usa producción.

### El caso que lo justifica: q13

Pregunta: *"¿Cómo debo ir vestido a trabajar en la farmacia?"*. La respuesta
está en el reglamento: *"bata blanca institucional con el carné visible…
calzado cerrado y antideslizante"*. No comparte **ni una palabra** con la
pregunta, así que BM25 no ayuda y todo depende del coseno.

Ese fragmento sacó **0,816**. Con el umbral en 0,82 SAVI lo descartaba y Claude
no habría tenido con qué responder: habría dicho "no encontré información"
teniendo el documento cargado. Es exactamente el tipo de pregunta (con otras
palabras) que un usuario real hace. Sin el set de evaluación no se detectaba.

### Por qué no se pueden filtrar las preguntas sin respuesta

Lo ideal sería que el umbral también dejara vacías las preguntas que los
documentos no responden ("dame una receta de arepas", "¿a cuánto está el
dólar?"). No se puede: con **los cuatro modelos** probados, algunas preguntas
sin respuesta sacan cosenos más altos (hasta 0,83 en e5) que algunas
respuestas correctas (0,81). Subir el umbral para rechazarlas tira respuestas
válidas. Por eso el umbral se usa solo para recortar ruido, y quien decide
"no encontré información" es Claude al leer los fragmentos, algo que ya hace
bien (verificado en Fase 2).

## Cómo se midió

- **Set:** `tests/fixtures/company_knowledge/eval/`, de una empresa ficticia
  (Droguería Andina S.A.S.):
  - 8 documentos: 3 MD, 2 TXT y 3 PDF de varias páginas con encabezado repetido.
  - 30 preguntas: 20 parafraseadas, 5 con términos exactos (códigos, montos) y 5 sin respuesta.
  - Las preguntas de PDF exigen la página correcta.
- **Pipeline real:**
  - SQLite temporal, worker de procesamiento e índice híbrido en memoria.
  - Se mide el mismo camino que usa producción, sin atajos.
- **Reproducir:**

  ```powershell
  uv run python -m scripts.build_eval_pdfs          # regenera los PDF
  uv run python -m scripts.eval_company_knowledge --download
  ```

- **Salida:** tablas completas en [`spike-modelo-resultados.md`](spike-modelo-resultados.md)
  y datos por pregunta en `spike-modelo-resultados.json`.

## Resultados

### Calidad (modo híbrido)

| Modelo | Fragmento | recall@6 | recall@1 | MRR | MRR solo vector |
|---|---|---|---|---|---|
| e5-small | 900 | 100% | 88% | 0,93 | 0,89 |
| e5-small | 300 | 100% | 88% | 0,93 | 0,91 |
| MiniLM-L12 | 900 | 100% | 84% | 0,91 | 0,82 |
| MiniLM-L12 | 300 | 100% | 84% | 0,89 | 0,76 |
| jina-v2-base-es | 900 | 100% | 92% | 0,95 | 0,97 |
| jina-v2-base-es | 300 | 100% | 96% | 0,97 | 0,90 |
| mpnet-base | 900 | 100% | 80% | 0,89 | 0,72 |
| mpnet-base | 300 | 100% | 92% | 0,95 | 0,79 |

### Costo

| Modelo | En disco | Indexación ms/página | p95 consulta |
|---|---|---|---|
| e5-small | 465 MB | ~90 | ~12 ms |
| MiniLM-L12 | 240 MB | ~35–50 | ~12 ms |
| jina-v2-base-es | 614 MB | ~300–350 | ~40 ms |
| mpnet-base | 1.075 MB | ~220–280 | ~35 ms |

### Umbral (e5-small, fragmento 900, regla actual)

| Umbral | Respuestas conservadas | Preguntas sin respuesta vaciadas |
|---|---|---|
| 0,78–0,81 | 100% | 0% |
| **0,82 (anterior)** | **96%** | 20% |
| 0,83 | 96% | 40% |

Con 0,82 se perdía la q13 ("¿Cómo debo ir vestido a trabajar?"). El fragmento
correcto tenía coseno 0,816 y ninguna palabra en común con la pregunta, que es
justo el caso de paráfrasis que la búsqueda vectorial tiene que resolver.

## Por qué esta decisión

- **Modelo: se queda e5-small.**
  - Todos los candidatos cumplen RNF-08, así que la elección se decide por costo y por la calidad vectorial.
  - MiniLM es más liviano, pero su calidad vectorial cae mucho con fragmentos chicos (MRR 0,76). En este set el BM25 lo tapa porque las preguntas comparten vocabulario con los documentos, y con usuarios reales eso no está garantizado.
  - jina-v2-base-es es el mejor en calidad (recall@1 96%), pero indexa 3,5 veces más lento, consulta 3 veces más lento y obliga a reindexar. Queda como **camino de mejora** si con documentos reales fallan las paráfrasis.
  - mpnet no aporta nada sobre jina y pesa el doble.
- **Fragmento: se queda 900.**
  - En este set los documentos son cortos (8 documentos dan 8 fragmentos con 900 y 14 con 300), así que la medición no distingue bien entre tamaños.
  - Con 300 no hubo mejora de recall para e5.
  - 900 entrega más contexto por cita al modelo de lenguaje.
  - Hay que volver a medirlo con documentos largos reales.
- **Umbral: 0,80, sin doble umbral.**
  - Ningún modelo separa las preguntas sin respuesta. El mejor coseno de una pregunta sin respuesta (0,83 en e5) supera al peor coseno de un fragmento correcto (0,81).
  - El doble umbral (más exigente sin coincidencia léxica) vació hasta 60% de las preguntas sin respuesta con fragmento 300. Pero son 5 preguntas: está sobreajustado y suma complejidad sin evidencia suficiente.
  - Palabras comunes ("empresa", "política", "empleados") dan coincidencias BM25, así que la regla léxica tampoco las rechaza.
- **"Receta de arepas"** (q27) sigue trayendo fragmentos (coseno ~0,82, sin BM25). No se corrige con el umbral sin perder respuestas reales. Es aceptable: SAVI se niega a temas fuera de la empresa y, con fragmentos irrelevantes, responde que no encontró información.

## Límites del spike

- **Set sintético y chico:** con 8 documentos, recall@6 discrimina poco. Por eso se reportan también recall@1 y MRR.
- **Páginas cortas** (~1.200 caracteres): la indexación por página subestima un PDF real. Para RNF-03, 50 páginas × ~90 ms ≈ 5 s, muy lejos de 60 s, aunque no es una medición con PDF real.
- **Sin e5-large ni jina-v3** (más de 2 GB cada uno): quedaron fuera por tamaño de instalador (R4).

## Próximo paso

Cuando lleguen los documentos de la empresa piloto (P1):

1. Agregarlos a un set propio con sus 30 preguntas.
2. Correr el mismo script.
3. Revisar sobre todo recall@1 de las paráfrasis y el tamaño de fragmento con documentos largos.
