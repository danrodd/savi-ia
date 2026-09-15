# Validación de la importación de documentos

> Fecha: 2026-09-15 · Equipo: portátil Intel i5-10300H (4 núcleos, 8 hilos), Windows.
> Un servidor con más núcleos debería dar tiempos iguales o mejores.

## Resumen

| Pregunta | Respuesta |
|---|---|
| ¿Funciona la importación de punta a punta? | **Sí.** 10 de 10 documentos (MD, TXT, PDF) quedaron `Listo` por HTTP, Postgres y el worker real. |
| ¿Cumple RNF-03 (PDF de 50 páginas en < 60 s)? | **Sí: 11–12 s.** |
| ¿Es demorado? | Documentos normales: **~1,5 s**. Solo los muy largos se sienten: 200 páginas ≈ 45 s y 500 páginas ≈ 1 min 45 s. |
| ¿Se traba SAVI mientras procesa? (RNF-02) | **No.** La búsqueda pasa de 25 ms a 59 ms de mediana, con un pico de 708 ms. |
| ¿Dónde se va el tiempo? | **97% en los embeddings** (el modelo ONNX). Extraer el PDF y fragmentar es casi instantáneo. |
| ¿Hay que cambiar algo? | En la configuración, no. En la interfaz, sí: falta mostrar el avance de los documentos largos (ver [revisión de la interfaz](revision-interfaz.md)). |

## Qué se midió

| Prueba | Script | Resultado crudo |
|---|---|---|
| Etapas del pipeline con documentos densos de 10 a 500 páginas | `scripts/bench_company_ingest.py` | [`bench-importacion.md`](bench-importacion.md) |
| Importación real por la API con SAVI corriendo | `scripts/bench_http_import.py` | [`bench-http-importacion.md`](bench-http-importacion.md) |
| Calidad con documentos largos (truncamiento) | `scripts/eval_company_knowledge.py --long` | [`spike-modelo-largos-resultados.md`](spike-modelo-largos-resultados.md) |

Los documentos densos tienen ~3.000 caracteres por página, como una hoja carta
llena de texto. Un PDF real con títulos, tablas y espacios suele tener menos,
así que estos tiempos son un techo razonable.

## Tiempos (configuración actual: fragmento de 900)

| Documento | Fragmentos | Tiempo hasta `Listo` |
|---|---|---|
| Documento corto (1–4 páginas) | 1–2 | ~1,5 s |
| PDF 10 páginas | 10 | 2,7 s |
| PDF 50 páginas | 50 | 11 s |
| PDF 200 páginas | 200 | 42 s |
| PDF 500 páginas (máximo permitido) | 500 | 1 min 44 s |
| Markdown 1 MB | 254 | 52 s |

**Regla práctica: ~0,2 s por página densa.** Crece en línea recta con el
tamaño, sin sorpresas. Los documentos se procesan **de a uno**: si se suben
diez PDF de 200 páginas juntos, el último espera en cola a los otros nueve
(~7 minutos).

Un Markdown o TXT de 20 MB (el máximo por archivo) tardaría ~17 minutos. Es
un caso raro (20 MB de texto plano son ~10.000 páginas), pero hoy el sistema
lo acepta.

## Hallazgo: el modelo solo "lee" 512 tokens por fragmento

### Qué pasa

- El modelo `multilingual-e5-small` convierte **como máximo 512 tokens** en su vector; lo que sobra se ignora.
- Los fragmentos de "900 tokens" se estiman como caracteres ÷ 4. En español eso da justo **~900 tokens reales** (medido con el tokenizer del modelo).
- Resultado: en documentos largos, **~42% del texto de cada fragmento no entra al vector**.
- El spike no lo detectó porque sus documentos eran cortos.

### ¿Se pierden respuestas?

Se probó con los documentos del set envueltos en ~40.000 caracteres de
relleno, así las respuestas quedan en cualquier parte del fragmento:

| Configuración | Solo vector (MRR) | **Híbrido (lo que usa SAVI)** | recall@6 | Tiempo relativo |
|---|---|---|---|---|
| Fragmento 900 (actual) | 0,93 | **0,92** | 100% | 1× |
| Fragmento 450 (sin truncar) | 0,96 | 0,86 | 100% | 2× |

- **Solo vector**, 450 es algo mejor: el truncamiento se nota, pero poco.
- **Híbrido**, 900 es mejor. La búsqueda por palabras (BM25) lee el fragmento **completo**, sin límite, y compensa la parte que el vector no ve. Con fragmentos chicos, BM25 pierde contexto.
- Pasar a 450 duplicaría el tiempo de importación y empeoraría la búsqueda real.

**Decisión: se queda 900.** Hay que revisarlo con documentos reales de la
empresa piloto, que tienen más texto parecido entre sí que el relleno de esta
prueba.

## Opción evaluada: el mismo modelo cuantizado (int8)

`Xenova/multilingual-e5-small` es el mismo modelo con los pesos comprimidos a
8 bits. Quedó registrado en el código para poder probarlo, pero **no es el
default**.

| | fp32 (actual) | int8 |
|---|---|---|
| Tamaño en el instalador | 465 MB | **129 MB** |
| Velocidad por fragmento | ~185 ms | **~145 ms** (−22%) |
| Parecido con fp32 (coseno) | — | 0,996 |
| Calidad en el set largo (híbrido) | MRR 0,92 | **MRR 0,92** (mismos rankings) |

- **A favor:** el instalador queda **~336 MB más liviano** y la importación ~20% más rápida, sin pérdida medible.
- **Costo:** cambiar el modelo obliga a **reprocesar todos los documentos** ya cargados en cada instalación. SAVI lo hace solo al arrancar (`enqueue_stale_embedding_documents`), pero durante ese tiempo los documentos no están disponibles para el chat.
- **Recomendación:** adoptarlo **antes** de que haya clientes con documentos cargados, así el reprocesamiento no afecta a nadie. Queda como decisión pendiente.

## Otras mediciones

- **Hilos de CPU:** con 2 hilos va ~20% más lento que con 4, y con 8 hilos no mejora (el portátil tiene 4 núcleos físicos). Producción usa núcleos ÷ 2, que está bien.
- **Tamaño del lote** (8 vs 32 fragmentos): sin diferencia.
- **Subida HTTP:** 20–60 ms incluso para 777 KB. Una sola subida tardó 1,3 s mientras el worker cargaba el modelo por primera vez; no se repitió.

## Reproducir

```powershell
cd backend
uv run python -m scripts.bench_company_ingest --chunk-tokens 900 450
uv run dev   # en otra terminal
uv run python -m scripts.bench_http_import
uv run python -m scripts.eval_company_knowledge --long --models intfloat/multilingual-e5-small Xenova/multilingual-e5-small --chunk-tokens 900 450
```
