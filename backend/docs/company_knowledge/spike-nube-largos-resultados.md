# Spike — modelo de embeddings, fragmento y umbral

> Generado por `scripts/eval_company_knowledge.py` sobre el set sintético de
> `tests/fixtures/company_knowledge/eval/` (8 documentos MD/TXT/PDF, 30 preguntas:
> 20 parafraseadas, 5 con términos exactos, 5 sin respuesta). Top-k = 6.

## Recuperación por modo

| Modelo | Fragmento | Vectorial recall@6/MRR | BM25 recall@6/MRR | Híbrido recall@6/MRR | Híbrido @1 / @3 | Fragmentos |
|---|---|---|---|---|---|---|
| `intfloat/multilingual-e5-small` | 900 | 100% / 0.929 | 100% / 0.782 | 100% / 0.917 | 86% / 100% | 49 |
| `gemini/gemini-embedding-001` | 900 | 100% / 1.0 | 100% / 0.782 | 100% / 1.0 | 100% / 100% | 49 |

## Separabilidad del coseno

| Modelo | Fragmento | Peor coseno del fragmento correcto | Mejor coseno en preguntas sin respuesta | ¿Separables? |
|---|---|---|---|---|
| `intfloat/multilingual-e5-small` | 900 | 0.8014 | 0.83 | no (se solapan) |
| `gemini/gemini-embedding-001` | 900 | 0.6315 | 0.6635 | no (se solapan) |

## Costo

| Modelo | Fragmento | Indexación ms/página | p95 consulta ms | Memoria índice | Modelo en disco |
|---|---|---|---|---|---|
| `intfloat/multilingual-e5-small` | 900 | 1953.1 | 10.5 | 243 KB | 594 MB |
| `gemini/gemini-embedding-001` | 900 | 15790.6 | 463.9 | 316 KB | 0 MB |

## Filtrado: respuestas conservadas vs. preguntas sin respuesta vaciadas

Mejor combinación por estrategia (prioriza no perder respuestas):

| Modelo | Fragmento | Regla actual (vector ≥ t o BM25 > 0) | Solo vector ≥ t | Doble umbral |
|---|---|---|---|---|
| `intfloat/multilingual-e5-small` | 900 | t=0.83: 100% / 40% | t=0.79: 100% / 20% | bajo=0.0 alto=0.83 bm25>0.0: 100% / 40% |
| `gemini/gemini-embedding-001` | 900 | t=0.57: 100% / 40% | t=0.62: 100% / 80% | bajo=0.63 alto=0.67 bm25>0.0: 100% / 100% |
