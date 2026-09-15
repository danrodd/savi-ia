# Spike — embeddings en la nube (Gemini) vs. locales

> Fecha: 2026-09-15 · Pregunta: ¿conviene ofrecer, además de la opción local,
> embeddings con un proveedor de IA que requiere internet y consume cuota?
> Estado: **medido, sin implementar**. La decisión es del producto.

## Resumen

| Aspecto | Local (`multilingual-e5-small`) | Nube (`gemini-embedding-001`) |
|---|---|---|
| **Calidad: fragmento correcto en 1.er lugar** | 88% (set corto) · 86% (set largo) | **100% · 100%** |
| recall@6 (RNF-08) | 100% | 100% |
| Latencia por pregunta del chat | ~10–15 ms | **~320 ms** (mediana) |
| Importación de un documento grande | ~0,2 s por página densa | Depende de la cuota: rápida con key paga, **más lenta que local con key gratuita** |
| Requiere internet | No | **Sí, al importar y en cada pregunta** |
| Qué sale de la empresa | Solo los fragmentos relevantes, al responder | **Todo el documento**, al importarlo |
| Costo | Ninguno (465 MB en el instalador) | Consumo de la API por token |

**Conclusión:**

- **Calidad:** la opción en la nube es **mejor**. Siempre pone el fragmento correcto primero, incluso en documentos largos donde el modelo local lo deja 2.º o 3.º.
- **Velocidad:** no es "más rápida" en general. Solo lo es para importar documentos grandes con una key de pago. Cada pregunta del chat suma ~0,3 s.
- **Recomendación:** si se ofrece, que sea **opcional** y con la local como default.

## Cómo se midió

- Mismo set y mismo pipeline que el [spike del modelo](spike-modelo.md), con fragmento de 900.
- Set corto: 8 documentos y 30 preguntas. Set largo: MD/TXT con relleno, 19 preguntas.
- Embedder de prueba: `scripts/gemini_embedder.py`.
  - Usa `RETRIEVAL_DOCUMENT` para fragmentos y `RETRIEVAL_QUERY` para preguntas, con 768 dimensiones.
  - Reintenta al recibir 429 respetando la espera que indica la API.
- La key es la del proveedor Gemini ya configurado en SAVI: se descifra en memoria y no se imprime ni se guarda.
- Resultados crudos: [`spike-nube-resultados.md`](spike-nube-resultados.md) y [`spike-nube-largos-resultados.md`](spike-nube-largos-resultados.md).

```powershell
uv run python -m scripts.eval_company_knowledge --models intfloat/multilingual-e5-small gemini/gemini-embedding-001 --chunk-tokens 900 --out spike-nube-resultados.md
uv run python -m scripts.eval_company_knowledge --long --models intfloat/multilingual-e5-small gemini/gemini-embedding-001 --chunk-tokens 900 --out spike-nube-largos-resultados.md
```

## Resultados

### Calidad (modo híbrido)

| Set | Modelo | recall@1 | MRR | MRR solo vector | Preguntas que no quedaron 1.as |
|---|---|---|---|---|---|
| Corto | e5-small | 88% | 0,93 | 0,89 | q01, q13 (vestimenta), q24 |
| Corto | Gemini | **100%** | **1,00** | 0,98 | ninguna |
| Largo | e5-small | 86% | 0,92 | 0,93 | q07, q25 |
| Largo | Gemini | **100%** | **1,00** | 1,00 | ninguna |

En el set largo, Gemini **no sufre el truncamiento** que sí afecta a e5-small
(su límite de entrada es mucho mayor que 512 tokens).

### Preguntas sin respuesta

- Gemini separa algo mejor que e5, pero **los puntajes todavía se solapan**: el peor fragmento correcto saca 0,63 y la mejor pregunta sin respuesta, 0,66.
- En el set largo, un doble umbral (0,63 / 0,67) vació las 5 preguntas sin respuesta sin perder ninguna respuesta. Con solo 5 preguntas eso es sobreajuste probable: se tomaría como indicio, no como regla.
- El umbral depende del modelo: e5 ronda 0,80 y Gemini ~0,6. Cambiar de proveedor obliga a cambiar `COMPANY_DOCS_MIN_SIMILARITY`.

### Velocidad y cuota

| Medición | Valor |
|---|---|
| Lote de 100 textos cortos (prueba directa) | 1,56 s → ~16 ms por texto (local: ~185 ms) |
| Una llamada con un solo texto | ~320 ms de mediana (latencia de red) |
| Set largo: 49 fragmentos + 38 consultas | **2 bloqueos por cuota (429), 74 s de espera** |
| Primera prueba directa: 3 lotes de 100 textos seguidos | Cuota agotada; se recuperó al minuto |

- **Con esta key**, la cuota por minuto se agota con unas decenas de fragmentos de 900 tokens.
- En ese nivel, un PDF de 500 páginas tardaría **bastante más** que en local, porque la importación queda frenada por las esperas.
- Con una key de pago (límites mucho mayores), los lotes de 100 textos harían ese mismo PDF en segundos.
- **Hay que verificar el nivel y los límites** de la key del cliente antes de prometer velocidad.

## Qué implicaría implementarlo

- **Encaja en la arquitectura.** `Embedder` ya es un puerto: sería un adaptador nuevo (`GeminiEmbedder`, y luego `OpenAIEmbedder`) elegido por configuración.
- **Es independiente del proveedor del chat.** Claude no ofrece embeddings, pero una instalación podría chatear con Claude y buscar con Gemini: solo necesita una key de Gemini.
- **Cambiar de modo obliga a reprocesar** todos los documentos, porque los vectores de un modelo no sirven para otro. SAVI ya lo hace solo (`enqueue_stale_embedding_documents`), pero mientras tanto no están disponibles.
- **Sin internet:** la búsqueda tiene que caer a solo BM25 (por palabras) en lugar de fallar, y la interfaz tiene que avisarlo.
- **Cuota:** la importación tiene que respetar los 429 (esperar y seguir) y mostrar "esperando cuota del proveedor".
- **Privacidad:** el aviso de subida cambia. Hoy dice que solo se envían los fragmentos relevantes; en modo nube se envía el documento completo.
- **Costo:** con precios de lista de Google para `gemini-embedding-001` (del orden de USD 0,15 por millón de tokens; verificar al implementar), un PDF de 500 páginas (~450.000 tokens) cuesta unos centavos. Habría que registrarlo en el consumo, igual que el chat.

## Recomendación

1. **Mantener la opción local como default.** Cumple RNF-08, funciona sin internet y no envía documentos completos.
2. **Ofrecer "Búsqueda en la nube" como opción avanzada** en `/admin/conocimiento`, con:
   - el aviso de privacidad;
   - el reprocesamiento explicado;
   - la caída a búsqueda por palabras cuando no hay conexión.
3. **Antes de implementarlo**, validar con los documentos reales de la empresa piloto (P1). Si e5-small ya responde bien sus preguntas, la mejora del primer lugar puede no justificar la complejidad.
