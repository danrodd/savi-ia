# Spike — Lectura de PDF con IA (primera ronda)

> Parte de: [Fase 4 — Lectura de PDF con IA](04-fase-lectura-pdf-con-ia.md) §3
> Fecha: 2026-09-23. Estado: **primera ronda con un documento sintético**.
> Falta la ronda con el corpus real (S4, S5 y S6).

## Documento de prueba

PDF generado para imitar el caso común, un escaneo de celular:

- 2 páginas que son solo imágenes JPEG, sin capa de texto (`pypdf`
  extrae 0 caracteres).
- Leve desenfoque e inclinación.
- La segunda página girada 90°.
- Marca de agua "Escaneado con CamScanner" en las dos páginas.
- Página 1: ficha técnica con un código de referencia, una tabla de 5
  filas y un diagrama eléctrico (L1, L2 y L3 hacia un motor "M").
- Página 2: texto con "4.000 horas", "18 meses" y un teléfono.

Mismo prompt (§6.1, con las reglas agregadas abajo) y mismo esquema en
los tres proveedores. Se pidió salida estructurada nativa.

## Resultados

| Proveedor · modelo | Credencial | Acepta el PDF | JSON válido | Tiempo | Costo de 2 páginas |
|---|---|---|---|---|---|
| Claude · `claude-haiku-4-5` | sesión local | Sí (bloque `document` por el Agent SDK) | Sí (`output_format`) | 7,6 s | US$0,0135 |
| Claude · `claude-sonnet-5` | sesión local | Sí | Sí | 6,2 s | US$0,0203 |
| OpenAI · `gpt-6-luna` | clave de API | Sí (`input_file` en Responses) | Sí (`json_schema` strict) | 14,9 s | US$0,0011 |
| Gemini · `gemini-flash-lite-latest` | clave de API | Sí (`Part` `application/pdf`) | Sí (`response_json_schema`) | 3,4 s | US$0,0014 |

Fidelidad:

| Dato | Haiku 4.5 | Sonnet 5 | gpt-6-luna | Flash-Lite |
|---|---|---|---|---|
| Código `SEO-BC450-22` | ✔ | ✔ | ✘ `SEQ-BC450-22` | ✔ |
| Tabla completa y como tabla | ✔ | ✔ | ✔ | ✔ |
| Diagrama descrito (L1, L2, L3, M, 3,7 kW) | ✔ | ✔ | ✔ | ✔ |
| Página girada | ✔ | ✔ | ✔ | ✔ |
| `4.000 horas` | ✘ `4 000` (dos corridas) | ✔ | ✔ | ✔ |
| Marca de agua omitida | ✔ (con la regla nueva) | ✔ | ✔ | ✔ |
| Títulos con `#` | ✔ | ✔ | ✔ | Uno sin marcar |

**Una muestra no es estadística.** Los errores de Haiku y de
`gpt-6-luna` son del tipo que más importa en una ficha técnica (números
y códigos), pero el modelo se elige con el corpus real (S4).

## Hallazgos

1. **S1 y S3 resueltos**: los tres proveedores aceptan el PDF directo y
   devuelven el esquema con salida estructurada nativa.
2. **S2 resuelto para la sesión local**: el Agent SDK instalado (0.2.87)
   acepta el bloque `document` en modo de entrada en streaming, con el
   mismo aislamiento del generador de títulos (sin herramientas). No hace
   falta usar `anthropic` directo. **El token OAuth no se probó** (no hay
   uno configurado). Usa el mismo tipo de autenticación de suscripción, así
   que lo esperable es que funcione igual; se confirma antes de liberar.
3. **Razonamiento**:
   - Claude: `thinking={"type": "disabled"}` baja el tiempo y el costo
     (Haiku pasó de 10,4 s y US$0,016 a 7,6 s y US$0,0135) sin perder
     calidad.
   - Gemini: `thinking_budget=0` devuelve **400** en
     `gemini-flash-lite-latest`. Sin configurar, ya usó 0 tokens de
     razonamiento. No se envía `thinking_config`.
   - OpenAI: usó 332 tokens de razonamiento. Probar el esfuerzo mínimo
     que acepte el modelo.
4. **Caché de Claude**: el Agent SDK escribe el pedido en la caché de
   1 hora, que cuesta el doble de la entrada. En la primera corrida de
   Haiku fue ~75 % del costo. Para documentos que se leen una vez es gasto
   perdido. `DISABLE_PROMPT_CACHING=1` en el `env` del CLI **no tuvo
   efecto**. Queda abierto.
5. **Llamada extra de Claude**: cada pedido con Sonnet sumó una llamada
   corta a Haiku que hace el CLI (~US$0,001). Es un costo fijo por tramo;
   con tramos de 5 páginas pesa poco.
6. **Suscripción**: con sesión local o token OAuth no se paga por token.
   El costo que informa el SDK es el precio de lista, y lo que se consume
   es el límite de la suscripción. Una carga grande puede agotarlo y dejar
   el chat sin servicio.

## Costo por 100 páginas con estos datos

| Modelo | Por página | Por 100 páginas |
|---|---|---|
| `gpt-6-luna` | US$0,00057 | ~US$0,06 |
| `gemini-flash-lite-latest` | US$0,00068 | ~US$0,07 |
| `claude-haiku-4-5` | US$0,0068 | ~US$0,68 |
| `claude-sonnet-5` | US$0,0102 | ~US$1,02 |

Coinciden con la estimación de §2, salvo Gemini, que salió más barato
(258 tokens por página y salida más corta).

## Cambios que esto produce en la especificación

- Dos reglas nuevas en el prompt: conservar los separadores de miles y
  decimales, y omitir las marcas de agua de apps de escaneo.
- El modelo de lectura deja de ser el `title_model`: pasa a un campo
  propio `document_model`, que por defecto toma el `chat_model`.
- Parámetros por proveedor (razonamiento) documentados en §5.1.
- Advertencia de suscripción en la configuración (§8.1).

## Pendiente para la segunda ronda

- Corpus real (S4, S5 y S6): fotos de celular reales, fichas técnicas,
  planos y PDF digitales para medir omisiones.
- Token OAuth de Claude.
- ~~Esfuerzo de razonamiento mínimo en OpenAI~~: probado con `gpt-6-luna`.
  `minimal` devuelve 400 (acepta `none`, `low`, `medium`, `high`, `xhigh`,
  `max`). Con `none` y con `low` siguió leyendo mal el código de referencia
  (con `none` coló una letra cirílica: "SE-BС450"); `low` cuesta ~15 % más.
  Se usa `low`. El error es del modelo, no del razonamiento: para fichas
  técnicas conviene otro `document_model`.
- Desactivar la caché de 1 hora en el Agent SDK.
