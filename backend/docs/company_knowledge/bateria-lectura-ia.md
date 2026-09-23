# Batería — Lectura de PDF con IA, de punta a punta

> Parte de: [Fase 4 — Lectura de PDF con IA](04-fase-lectura-pdf-con-ia.md)
> Fecha: 2026-09-23. Script: `backend/scripts/bateria_lectura_ia.py`.
> Proveedor: OpenAI, `gpt-6-luna` (chat y lectura).

## Resultado

**22/22 en tres corridas seguidas**, después de corregir los defectos que
encontró la batería (§5). La primera corrida dio 19/22.

- Los 7 PDF quedaron `Listo · Leído con IA`, todas sus páginas (47/47).
- Las 20 preguntas con dato respondieron **el valor correcto y citaron el
  documento correcto**.
- En las 2 preguntas sin respuesta en los documentos, SAVI dijo que no lo
  encontró. **No inventó.**
- Ninguna respuesta dijo "no tengo acceso" ni un equivalente.

Costo de una corrida completa: **US$0,031** de lectura (una sola vez por
documento) + **~US$0,01–0,015** de preguntas.

## 1. Qué se probó

La cadena completa, igual que la usa un administrador:

1. Subir el PDF por la API de Conocimiento, con la lectura con IA activa.
2. El worker lo lee con IA por tramos, lo fragmenta y lo indexa.
3. Un usuario pregunta por el chat, cada pregunta en una conversación nueva.
4. Verificación automática de cada respuesta:
   - contiene el **dato esperado**;
   - cita el **documento correcto** (fuentes guardadas en el mensaje);
   - no **deduce** el dato ("parecería…", "por la nomenclatura…");
   - no dice **"no tengo acceso"** ni equivalentes.

Los valores esperados salen del texto de `pypdf` (documentos digitales) o de
mirar la imagen (escaneos), **nunca de la transcripción de la IA**. Así la
batería no valida la IA contra sí misma.

## 2. Corpus

PDF públicos (descargados de sus URLs; no se versionan). Los datos
personales del formulario de Querétaro ya vienen tachados de origen: es la
versión pública de un portal de transparencia.

| Documento | Fuente | Tipo | Págs. | Tamaño | Qué tiene |
|---|---|---|---|---|---|
| Ficha técnica Potabon K | [PDF](https://croper-production.s3.amazonaws.com/product_provider_files/files/000/015/127/original/ficha_tecnica_Potabon_K_20200304090357.pdf.pdf) | **Escaneo** (CamScanner) | 2 | 973 KB | Tabla de porcentajes, NIT, presentaciones; marca de agua "Scanned with CamScanner". `pypdf` saca 0 caracteres útiles. |
| Solicitud de licencia de construcción, Querétaro | [PDF](https://municipiodequeretaro.gob.mx/municipio/repositorios/transparencia/a67/1T22/sds/84S.pdf) | **Foto de formulario** | 1 | 1,1 MB | Casillas marcadas, valores escritos a mano, tabla de superficies, clave catastral. |
| Guía de instalación de repisas Rubbermaid | [PDF](https://images.thdstatic.com/catalog/pdfImages/51/51960b5c-3c93-4bf5-8499-87edb6b831b2.pdf) | **Diagrama escaneado** | 1 | 195 KB | Pasos ilustrados con medidas (16" / 40,6 cm; 50 lb / 22,7 kg), en tres idiomas. |
| Ficha técnica bombas Rotoplas TCP | [PDF](https://rotoplas.vteximg.com.br/arquivos/FT-320003.pdf?v=638201110020170000) | Digital + gráfico | 2 | 143 KB | Tabla de especificaciones de dos modelos y curva de desempeño. |
| Catálogo bombas Cisealco STB | [PDF](https://cisealco.com/catalogos/cat_bomb_sixteam.pdf) | Digital + tablas | 12 | 870 KB | Tablas de rendimiento, dimensiones y pesos; curvas. |
| Instalación eléctrica de vivienda | [PDF](https://www3.gobiernodecanarias.org/medusa/ecoblog/mmormarf/files/2015/04/instalacion-electrica-vivienda-2.pdf) | Digital + planos | 16 | 1,5 MB | Esquemas unifilares, multifilares y de montaje (65 imágenes). |
| Ficha técnica Simdax (AEMPS) | [PDF](https://cima.aemps.es/cima/pdfs/es/ft/64154/FichaTecnica_64154.html.pdf) | Digital, texto denso | 13 | 229 KB | Control: mide si la IA se salta texto. |

### Cómo quedó cada documento

| Documento | Estado | Leído con | Págs. con IA | Fragmentos | Costo de lectura |
|---|---|---|---|---|---|
| Ficha técnica Potabon K | Listo | IA | 2/2 | 1 | US$0,0012 |
| Solicitud de licencia Querétaro | Listo | IA | 1/1 | 2 | US$0,0012 |
| Guía Rubbermaid | Listo | IA | 1/1 | 1 | US$0,0005 |
| Ficha Rotoplas TCP | Listo | IA | 2/2 | 1 | US$0,0011 |
| Catálogo Cisealco STB | Listo | IA | 12/12 | 6 | US$0,0080 |
| Instalación eléctrica de vivienda | Listo | IA | 16/16 | 8 | US$0,0090 |
| Ficha Simdax | Listo | IA | 13/13 | 12 | US$0,0102 |
| **Total** | | | **47/47** | **31** | **US$0,0311** |

Sin la lectura con IA, los tres escaneos habrían quedado en "Sin texto".

## 3. Preguntas y resultados (corrida final)

| # | Documento | Pregunta | Esperado | Respuesta de SAVI | Cita | ✔ |
|---|---|---|---|---|---|---|
| P01 | Potabon K (escaneo) | ¿Qué porcentaje de citronela contiene el Potabon K? | 3,0 % | "contiene 3,0 % de citronela como repelente vegetal" | Potabon K p. 1–2 | ✔ |
| P02 | Potabon K (escaneo) | ¿En qué presentaciones se vende el Potabon K? | 1, 4, 10 y 20 litros | "1, 4, 10 y 20 litros" | Potabon K p. 1–2 | ✔ |
| P03 | Potabon K (escaneo) | ¿Cuál es el pH de la solución al 5%? | Entre 6 y 7 | "pH entre 6 y 7" | Potabon K p. 1–2 | ✔ |
| P04 | Querétaro (formulario) | ¿Cuál es la superficie del predio? | 220.17 m² | "220,17 m²" | Querétaro p. 1 | ✔ |
| P05 | Querétaro (formulario) | ¿Cuál es el total de m² de construcción? | 247.34 m² | "247,34 m²" | Querétaro p. 1 | ✔ |
| P06 | Rubbermaid (diagrama) | ¿Cada cuánto se atornilla el montante a los parantes? | 16 pulgadas | "cada 16 pulgadas (40,6 cm)" | Rubbermaid p. 1 | ✔ |
| P07 | Rubbermaid (diagrama) | ¿Cuánto peso soporta la repisa? | 50 lb / 22,7 kg | "50 lb (22,7 kg)" | Rubbermaid p. 1 | ✔ |
| P08 | Rotoplas | ¿Caudal máximo de la TCP158 de 1 HP? | 6 m³/h | "6 m³/h, equivalente a 100 litros por minuto" | Rotoplas p. 1–2 | ✔ |
| P09 | Rotoplas | ¿Corriente máxima de la TCP130? | 2,7 A | "2,7 A" | Rotoplas p. 1–2 | ✔ |
| P10 | Rotoplas | ¿De qué material es el impulsor? | Noryl | "Noryl, un material que ayuda a evitar la corrosión" | Rotoplas p. 1–2 | ✔ |
| P11 | Cisealco (tablas) | ¿Cuánto pesa la STB1 300? | 33 kg | "pesa 33 kg" | Cisealco p. 2–3 | ✔ |
| P12 | Cisealco (tablas) | ¿Qué potencia en HP tiene la STB2 750 T? | 7,5 HP | "7,5 HP (5,5 kW)" | Cisealco p. 1–2 | ✔ |
| P13 | Cisealco | ¿Temperatura máxima del líquido? | 90 °C | "90 °C" | Cisealco p. 1–2 | ✔ |
| P14 | Cisealco | ¿Material del sello mecánico? | Carbón y cerámica | "carbón y cerámica" | Cisealco p. 1–2 | ✔ |
| P15 | Instalación eléctrica | ¿Qué tipos de esquemas se usan? | Topográfico, multifilar, unifilar | Los tres, con su descripción | Instalación p. 1–3 | ✔ |
| P16 | Instalación eléctrica | ¿Qué se necesita para encender una bombilla desde tres puntos? | Conmutador de cruce | "dos conmutadores y un conmutador de cruce" | Instalación p. 3–4 | ✔ |
| P17 | Simdax | ¿Cuántos mg de levosimendán tiene un vial de 5 ml? | 12,5 mg | "12,5 mg de levosimendán (2,5 mg/ml)" | Simdax p. 1–2 | ✔ |
| P18 | Simdax | ¿Dosis de carga inicial? | 6–12 microgramos/kg | "6–12 microgramos/kg … durante 10 minutos" | Simdax p. 1–2 | ✔ |
| P19 | Simdax | ¿Días de monitorización con daño renal o hepático leve a moderado? | 5 días | "al menos 5 días" | Simdax p. 2–3 | ✔ |
| P20 | Simdax | ¿Cuánto etanol por ml? | 785 mg | "785 mg de etanol por cada ml" | Simdax p. 1–2 | ✔ |
| N01 | Potabon K | ¿Cuál es el precio de venta del Potabon K? | *No está en el documento* | "La ficha técnica de Potabon K no indica su precio de venta." | — | ✔ |
| N02 | Cisealco | ¿Cuántos empleados tiene Cisealco? | *No está en el documento* | "No encontré cuántos empleados tiene Cisealco en los documentos de la empresa." | — | ✔ |

## 4. Evolución de las corridas

| Corrida | Resultado | Qué cambió antes de correrla |
|---|---|---|
| 1 | 19/22 | — |
| 2 | 21/22 | Contexto de búsqueda 6.000 → 12.000 caracteres (§5.3) y evaluador más estricto |
| 3 | **22/22** | Prompt: los documentos incluyen fichas técnicas y productos (§5.4) |
| 4 | **22/22** | — (repetición, para descartar suerte) |
| 5 | **22/22** | — (script del repositorio, descargando el corpus de sus URLs) |

La batería del ERP (6 preguntas de datos y del catálogo) se corrió después
del cambio de prompt y siguió respondiendo con la herramienta correcta.

## 5. Defectos que encontró la batería y cómo se corrigieron

### 5.1 Gemini: el cliente se cerraba solo

`genai.Client.__del__` cierra sus conexiones. El lector guardaba solo
`client.aio.models`, así que Python liberaba el cliente y **todos** los
pedidos fallaban cuando el lector se usaba un rato después de creado (todo
documento de varios tramos). Corregido: el lector guarda el cliente. Test de
regresión con `weakref` + `gc`.

### 5.2 Gemini: numeración de páginas por tramo

Gemini devolvió el tramo 6–10 numerado como 1–5, aunque el mensaje pide la
numeración del documento. El validador lo descartaba como "JSON inválido".
Corregido: si ninguna página cae en el rango y todas forman 1..N, se corren
al rango real.

### 5.3 La búsqueda le daba al modelo un solo fragmento

**Causa de los 3 fallos de la primera corrida (P12, P16 y P17).** El tope de
contexto era 6.000 caracteres y los fragmentos miden ~4.000: entraba **uno
solo**. Si el correcto no quedaba primero, el modelo no lo veía y respondía
"no aparece en el fragmento disponible". La lectura estaba bien: los datos
estaban en los fragmentos guardados ("Un vial de 5 ml contiene 12,5 mg",
"conmutada de cruce", la fila "STB2 750 T | 5,5 | 7,5").

Corregido: `COMPANY_DOCS_MAX_CONTEXT_CHARS` pasa de 6.000 a 12.000 (entran
3 fragmentos). Costo: ~1.500 tokens más de entrada por pregunta que usa
documentos (despreciable con `gpt-6-luna`; ~US$0,003 con Sonnet).

**Afecta a todos los documentos, no solo a los leídos con IA**: la Fase 2
se había validado con documentos cortos, donde casi siempre había un solo
fragmento relevante.

### 5.4 El modelo no buscaba fichas técnicas en los documentos

**Causa del fallo de P02 en la segunda corrida.** El prompt describía los
documentos como "políticas, procedimientos, reglamentos, actas y normas".
Ante "¿en qué presentaciones se vende el Potabon K?", el modelo buscó en el
inventario del ERP, no lo encontró y no siguió buscando. Corregido en
`system_prompt.py`:

- los documentos también son fichas técnicas, catálogos, manuales, planos y
  formularios, y se consultan para las características de un producto;
- si un producto no aparece en los datos del ERP, se busca en los documentos
  **antes** de decir que no se encontró.

### 5.5 Defectos del evaluador

- Dio por buena una respuesta que **dedujo** el dato por el nombre del
  modelo (P12, corrida 1). Ahora "parecería", "por la nomenclatura" y
  similares cuentan como fallo.
- Rechazó una respuesta negativa que se negó por estar fuera de tema, que es
  un comportamiento seguro. Ahora pasa mientras no invente.

## 6. Límites de esta batería

- **Un proveedor**: `gpt-6-luna`. Gemini se evaluó en la lectura (spike,
  segunda ronda), no en el chat. Claude no se corrió por costo.
- **Corpus público y chico** (47 páginas). Falta el documento largo de 165
  páginas, pospuesto.
- **Un usuario administrador.** Permisos, varias bases y preguntas
  naturales se prueban en [`bateria-permisos-bases.md`](bateria-permisos-bases.md).
- La verificación del dato es por texto. Una respuesta con el dato correcto
  y un error al lado pasaría: por eso la tabla de §3 se revisó a mano.

## 7. Cómo volver a correrla

Con el backend en `localhost:8000`:

```powershell
cd backend
uv run python scripts/bateria_lectura_ia.py            # sube y pregunta
uv run python scripts/bateria_lectura_ia.py --reusar   # solo pregunta
```

Usa el proveedor activo. Deja el detalle en `resultado.json`, en la carpeta
temporal del corpus.
