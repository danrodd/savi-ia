# Spike — modelo de embeddings, fragmento y umbral

> Generado por `scripts/eval_company_knowledge.py` sobre el set sintético de
> `tests/fixtures/company_knowledge/eval/` (8 documentos MD/TXT/PDF, 30 preguntas:
> 20 parafraseadas, 5 con términos exactos, 5 sin respuesta). Top-k = 6.

## Recuperación por modo

| Modelo | Fragmento | Vectorial recall@6/MRR | BM25 recall@6/MRR | Híbrido recall@6/MRR | Híbrido @1 / @3 | Fragmentos |
|---|---|---|---|---|---|---|
| `intfloat/multilingual-e5-small` | 900 | 100% / 0.929 | 100% / 0.782 | 100% / 0.917 | 86% / 100% | 49 |
| `intfloat/multilingual-e5-small` | 450 | 100% / 0.964 | 93% / 0.78 | 100% / 0.857 | 79% / 100% | 98 |
| `Xenova/multilingual-e5-small` | 900 | 100% / 0.917 | 100% / 0.782 | 100% / 0.917 | 86% / 100% | 49 |
| `Xenova/multilingual-e5-small` | 450 | 100% / 0.929 | 93% / 0.78 | 100% / 0.851 | 79% / 93% | 98 |

## Separabilidad del coseno

| Modelo | Fragmento | Peor coseno del fragmento correcto | Mejor coseno en preguntas sin respuesta | ¿Separables? |
|---|---|---|---|---|
| `intfloat/multilingual-e5-small` | 900 | 0.8014 | 0.83 | no (se solapan) |
| `intfloat/multilingual-e5-small` | 450 | 0.8176 | 0.8287 | no (se solapan) |
| `Xenova/multilingual-e5-small` | 900 | 0.8008 | 0.8259 | no (se solapan) |
| `Xenova/multilingual-e5-small` | 450 | 0.8152 | 0.8249 | no (se solapan) |

## Costo

| Modelo | Fragmento | Indexación ms/página | p95 consulta ms | Memoria índice | Modelo en disco |
|---|---|---|---|---|---|
| `intfloat/multilingual-e5-small` | 900 | 2065.3 | 13.6 | 243 KB | 594 MB |
| `intfloat/multilingual-e5-small` | 450 | 3004.5 | 12.3 | 317 KB | 594 MB |
| `Xenova/multilingual-e5-small` | 900 | 1714.6 | 9.9 | 243 KB | 594 MB |
| `Xenova/multilingual-e5-small` | 450 | 2462.7 | 9.0 | 317 KB | 594 MB |

## Filtrado: respuestas conservadas vs. preguntas sin respuesta vaciadas

Mejor combinación por estrategia (prioriza no perder respuestas):

| Modelo | Fragmento | Regla actual (vector ≥ t o BM25 > 0) | Solo vector ≥ t | Doble umbral |
|---|---|---|---|---|
| `intfloat/multilingual-e5-small` | 900 | t=0.83: 100% / 40% | t=0.79: 100% / 20% | bajo=0.0 alto=0.83 bm25>0.0: 100% / 40% |
| `intfloat/multilingual-e5-small` | 450 | t=0.83: 100% / 40% | t=0.8: 100% / 20% | bajo=0.0 alto=0.83 bm25>0.0: 100% / 40% |
| `Xenova/multilingual-e5-small` | 900 | t=0.83: 100% / 40% | t=0.79: 100% / 20% | bajo=0.0 alto=0.83 bm25>0.0: 100% / 40% |
| `Xenova/multilingual-e5-small` | 450 | t=0.83: 100% / 40% | t=0.8: 100% / 20% | bajo=0.0 alto=0.83 bm25>0.0: 100% / 40% |
