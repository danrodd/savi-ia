# Spike — modelo de embeddings, fragmento y umbral

> Generado por `scripts/eval_company_knowledge.py` sobre el set sintético de
> `tests/fixtures/company_knowledge/eval/` (8 documentos MD/TXT/PDF, 30 preguntas:
> 20 parafraseadas, 5 con términos exactos, 5 sin respuesta). Top-k = 6.

## Recuperación por modo

| Modelo | Fragmento | Vectorial recall@6/MRR | BM25 recall@6/MRR | Híbrido recall@6/MRR | Híbrido @1 / @3 | Fragmentos |
|---|---|---|---|---|---|---|
| `intfloat/multilingual-e5-small` | 900 | 100% / 0.893 | 96% / 0.873 | 100% / 0.933 | 88% / 100% | 8 |
| `gemini/gemini-embedding-001` | 900 | 100% / 0.98 | 96% / 0.873 | 100% / 1.0 | 100% / 100% | 8 |

## Separabilidad del coseno

| Modelo | Fragmento | Peor coseno del fragmento correcto | Mejor coseno en preguntas sin respuesta | ¿Separables? |
|---|---|---|---|---|
| `intfloat/multilingual-e5-small` | 900 | 0.812 | 0.8298 | no (se solapan) |
| `gemini/gemini-embedding-001` | 900 | 0.6194 | 0.6455 | no (se solapan) |

## Costo

| Modelo | Fragmento | Indexación ms/página | p95 consulta ms | Memoria índice | Modelo en disco |
|---|---|---|---|---|---|
| `intfloat/multilingual-e5-small` | 900 | 112.0 | 15.3 | 24 KB | 594 MB |
| `gemini/gemini-embedding-001` | 900 | 226.5 | 453.7 | 36 KB | 0 MB |

## Filtrado: respuestas conservadas vs. preguntas sin respuesta vaciadas

Mejor combinación por estrategia (prioriza no perder respuestas):

| Modelo | Fragmento | Regla actual (vector ≥ t o BM25 > 0) | Solo vector ≥ t | Doble umbral |
|---|---|---|---|---|
| `intfloat/multilingual-e5-small` | 900 | t=0.0: 100% / 0% | t=0.8: 100% / 20% | bajo=0.0 alto=0.8 bm25>3.0: 100% / 20% |
| `gemini/gemini-embedding-001` | 900 | t=0.59: 100% / 40% | t=0.59: 100% / 40% | bajo=0.6 alto=0.64 bm25>0.0: 100% / 60% |
