# Importación de punta a punta — resultados

> Generado por `scripts/bench_http_import.py` contra SAVI corriendo (HTTP, Postgres, worker real).
> Los documentos se procesan de a uno: la espera incluye la cola.

| Documento | Tamaño | Páginas | Subida | Espera hasta listo | Estado |
|---|---|---|---|---|---|
| acta-comite-045.md | 1 KB | — | 30 ms | 1.6 s | ready |
| manual-caja.md | 2 KB | — | 1329 ms | 0.8 s | ready |
| politica-credito-clientes.txt | 1 KB | — | 22 ms | 0.8 s | ready |
| politica-devoluciones.txt | 1 KB | — | 23 ms | 0.7 s | ready |
| procedimiento-inventario.pdf | 3 KB | 3 | 25 ms | 1.5 s | ready |
| protocolo-controlados.pdf | 2 KB | 2 | 26 ms | 1.5 s | ready |
| reglamento-trabajo.pdf | 4 KB | 4 | 32 ms | 1.4 s | ready |
| seguridad-informacion.md | 1 KB | — | 23 ms | 1.4 s | ready |
| bench-denso-50-paginas.pdf | 194 KB | 50 | 34 ms | 12.2 s | ready |
| bench-denso-200-paginas.pdf | 777 KB | 200 | 56 ms | 57.5 s | ready |

Total del lote: **59.9 s**.

## Búsqueda mientras se procesa (RNF-02)

| Situación | Muestras | Mediana | Máximo |
|---|---|---|---|
| Sin procesamiento | 10 | 25 ms | 49 ms |
| Procesando bench-denso-200-paginas.pdf | 77 | 59 ms | 708 ms |
