# Spike — modelo de embeddings, fragmento y umbral

> Generado por `scripts/eval_company_knowledge.py` sobre el set sintético de
> `tests/fixtures/company_knowledge/eval/` (8 documentos MD/TXT/PDF, 30 preguntas:
> 20 parafraseadas, 5 con términos exactos, 5 sin respuesta). Top-k = 6.

## Recuperación por modo

| Modelo | Fragmento | Vectorial recall@6/MRR | BM25 recall@6/MRR | Híbrido recall@6/MRR | Híbrido @1 / @3 | Fragmentos |
|---|---|---|---|---|---|---|
| `intfloat/multilingual-e5-small` | 900 | 100% / 0.893 | 96% / 0.873 | 100% / 0.933 | 88% / 100% | 8 |
| `intfloat/multilingual-e5-small` | 300 | 100% / 0.91 | 96% / 0.88 | 100% / 0.93 | 88% / 96% | 14 |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 900 | 100% / 0.818 | 96% / 0.873 | 100% / 0.913 | 84% / 100% | 8 |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 300 | 92% / 0.76 | 96% / 0.88 | 100% / 0.89 | 84% / 92% | 14 |
| `jinaai/jina-embeddings-v2-base-es` | 900 | 100% / 0.973 | 96% / 0.873 | 100% / 0.953 | 92% / 100% | 8 |
| `jinaai/jina-embeddings-v2-base-es` | 300 | 100% / 0.901 | 96% / 0.88 | 100% / 0.968 | 96% / 96% | 14 |
| `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | 900 | 100% / 0.718 | 96% / 0.873 | 100% / 0.89 | 80% / 96% | 8 |
| `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | 300 | 100% / 0.79 | 96% / 0.88 | 100% / 0.953 | 92% / 100% | 14 |

## Separabilidad del coseno

| Modelo | Fragmento | Peor coseno del fragmento correcto | Mejor coseno en preguntas sin respuesta | ¿Separables? |
|---|---|---|---|---|
| `intfloat/multilingual-e5-small` | 900 | 0.812 | 0.8298 | no (se solapan) |
| `intfloat/multilingual-e5-small` | 300 | 0.8105 | 0.8298 | no (se solapan) |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 900 | 0.2131 | 0.481 | no (se solapan) |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 300 | 0.1363 | 0.481 | no (se solapan) |
| `jinaai/jina-embeddings-v2-base-es` | 900 | 0.2483 | 0.4136 | no (se solapan) |
| `jinaai/jina-embeddings-v2-base-es` | 300 | 0.2178 | 0.4259 | no (se solapan) |
| `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | 900 | 0.1965 | 0.4984 | no (se solapan) |
| `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | 300 | 0.295 | 0.4988 | no (se solapan) |

## Costo

| Modelo | Fragmento | Indexación ms/página | p95 consulta ms | Memoria índice | Modelo en disco |
|---|---|---|---|---|---|
| `intfloat/multilingual-e5-small` | 900 | 92.6 | 14.5 | 24 KB | 465 MB |
| `intfloat/multilingual-e5-small` | 300 | 96.3 | 12.9 | 34 KB | 465 MB |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 900 | 33.6 | 11.0 | 24 KB | 240 MB |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 300 | 50.0 | 11.2 | 34 KB | 240 MB |
| `jinaai/jina-embeddings-v2-base-es` | 900 | 306.2 | 40.8 | 36 KB | 614 MB |
| `jinaai/jina-embeddings-v2-base-es` | 300 | 368.5 | 43.5 | 55 KB | 614 MB |
| `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | 900 | 231.9 | 35.7 | 36 KB | 1075 MB |
| `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | 300 | 290.8 | 33.9 | 55 KB | 1075 MB |

## Filtrado: respuestas conservadas vs. preguntas sin respuesta vaciadas

Mejor combinación por estrategia (prioriza no perder respuestas):

| Modelo | Fragmento | Regla actual (vector ≥ t o BM25 > 0) | Solo vector ≥ t | Doble umbral |
|---|---|---|---|---|
| `intfloat/multilingual-e5-small` | 900 | t=0.0: 100% / 0% | t=0.8: 100% / 20% | bajo=0.0 alto=0.8 bm25>3.0: 100% / 20% |
| `intfloat/multilingual-e5-small` | 300 | t=0.82: 100% / 40% | t=0.0: 100% / 0% | bajo=0.0 alto=0.82 bm25>3.0: 100% / 60% |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 900 | t=0.23: 100% / 40% | t=0.09: 100% / 20% | bajo=0.0 alto=0.23 bm25>0.0: 100% / 40% |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 300 | t=0.23: 100% / 40% | t=0.13: 100% / 20% | bajo=0.0 alto=0.23 bm25>0.0: 100% / 40% |
| `jinaai/jina-embeddings-v2-base-es` | 900 | t=0.19: 100% / 40% | t=0.19: 100% / 40% | bajo=0.0 alto=0.19 bm25>0.0: 100% / 40% |
| `jinaai/jina-embeddings-v2-base-es` | 300 | t=0.05: 100% / 20% | t=0.05: 100% / 20% | bajo=0.0 alto=0.05 bm25>0.0: 100% / 20% |
| `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | 900 | t=0.29: 100% / 40% | t=0.0: 100% / 0% | bajo=0.0 alto=0.29 bm25>0.0: 100% / 40% |
| `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | 300 | t=0.28: 100% / 40% | t=0.28: 100% / 40% | bajo=0.0 alto=0.28 bm25>0.0: 100% / 40% |
