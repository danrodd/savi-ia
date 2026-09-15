# Benchmark de importación — resultados

> Generado por `scripts/bench_company_ingest.py`. Modelo `intfloat/multilingual-e5-small`, 8 núcleos lógicos, ONNX con 4 hilos (como producción).
> Documentos densos de ~3000 caracteres por página.

## Tiempos

| Documento | Fragmento | Tamaño | Fragmentos | Extracción | Fragmentación | Embeddings | **Total (worker)** | Por página | Estado |
|---|---|---|---|---|---|---|---|---|---|
| PDF 10 páginas | 900 | 38 KB | 10 | 0.05 s | 0.00 s | 2.16 s | **2.7 s** | 274 ms | ready |
| PDF 50 páginas | 900 | 193 KB | 50 | 0.40 s | 0.00 s | 11.67 s | **10.9 s** | 219 ms | ready |
| PDF 200 páginas | 900 | 774 KB | 200 | 1.03 s | 0.00 s | 41.76 s | **41.6 s** | 208 ms | ready |
| PDF 500 páginas | 900 | 1943 KB | 500 | 2.53 s | 0.01 s | 100.48 s | **104.0 s** | 208 ms | ready |
| Markdown 1 MB | 900 | 1026 KB | 254 | 0.06 s | 0.01 s | 51.23 s | **51.6 s** | — | ready |
| PDF 10 páginas | 450 | 38 KB | 21 | 0.05 s | 0.00 s | 3.95 s | **4.1 s** | 405 ms | ready |
| PDF 50 páginas | 450 | 193 KB | 101 | 0.26 s | 0.00 s | 20.07 s | **20.2 s** | 404 ms | ready |
| PDF 200 páginas | 450 | 774 KB | 404 | 1.05 s | 0.02 s | 79.20 s | **80.7 s** | 403 ms | ready |
| PDF 500 páginas | 450 | 1943 KB | 1021 | 2.64 s | 0.05 s | 201.41 s | **204.5 s** | 409 ms | ready |
| Markdown 1 MB | 450 | 1026 KB | 540 | 0.07 s | 0.01 s | 108.84 s | **109.2 s** | — | ready |

## Tokens reales por fragmento (límite del modelo: 512)

| Documento | Fragmento | Mediana | Máximo | Fragmentos truncados | Texto que no entra al vector |
|---|---|---|---|---|---|
| PDF 10 páginas | 900 | 852 | 910 | 100% | 39% |
| PDF 50 páginas | 900 | 879 | 949 | 100% | 42% |
| PDF 200 páginas | 900 | 878 | 983 | 100% | 42% |
| PDF 500 páginas | 900 | 878 | 994 | 100% | 42% |
| Markdown 1 MB | 900 | 944 | 1197 | 100% | 46% |
| PDF 10 páginas | 450 | 418 | 480 | 0% | 0% |
| PDF 50 páginas | 450 | 448 | 512 | 0% | 0% |
| PDF 200 páginas | 450 | 448 | 516 | 0% | 0% |
| PDF 500 páginas | 450 | 448 | 539 | 1% | 0% |
| Markdown 1 MB | 450 | 465 | 655 | 26% | 3% |
