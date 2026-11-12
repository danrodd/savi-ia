# 12 — Generación de documentos (Excel, PDF, Word)

**Estado:** análisis (Fase A del plan `odd/tasks/hallazgos-primera-demo.md`).
**Origen:** demo con cliente del 2026-11-11: "la posibilidad de que SAVI genere documentos, ya sea un Word, PDF o Excel, donde lleve la información que se le solicita".
**Depende de:** P1 (`10-datos-por-permiso.md`), por los permisos, y P2 (`11-resultados-completos.md`), por los conjuntos de resultados y la exportación.

## 1. Objetivo

Que el usuario pida en el chat "hágame un informe de la cartera vencida en PDF" o "páseme en Excel los clientes con su teléfono" y reciba un archivo para descargar, **correcto** y **sin abrir agujeros de seguridad**.

## 2. Dos tipos de archivo

| Tipo | Qué es | Formatos | Ejemplo |
|---|---|---|---|
| **Exportación** (P2) | Una tabla tal cual, con todas sus filas | Excel, CSV, PDF | "Páseme en Excel los clientes que compraron LLANTAS0183" |
| **Documento** (P3) | Título, texto, una o varias tablas y datos clave, con presentación de la empresa | Word, PDF | "Informe de llantas sin movimiento en el último año, para la gerencia" |

Las dos salen del **mismo generador**, en el servidor.

## 3. Principio de diseño: el modelo describe, el servidor arma

El modelo **no escribe el archivo** (ni HTML, ni código, ni bytes). Entrega una **especificación estructurada** que el servidor valida y convierte con plantillas fijas:

```json
{
  "formato": "pdf",
  "titulo": "Llantas sin movimiento en el último año",
  "bloques": [
    { "tipo": "parrafo", "texto": "Al 11 de noviembre de 2026 hay 38 referencias..." },
    { "tipo": "datos_clave", "items": [["Referencias", "38"], ["Unidades", "112"]] },
    { "tipo": "tabla", "conjunto": "c-7f3a...", "columnas": ["referencia", "llanta", "existencia", "dias_sin_venta"] },
    { "tipo": "titulo2", "texto": "Recomendaciones" },
    { "tipo": "lista", "items": ["Revisar el DOT de las referencias con más de 2 años"] }
  ]
}
```

- **Las tablas no llevan datos, llevan la referencia de un conjunto de resultados** (P2). El servidor pone las filas desde la base. El modelo no puede inventar, saltarse ni cambiar una fila del documento.
- **El texto es texto plano**, con un Markdown mínimo (negrita, cursiva y listas) que el servidor interpreta. No pasa HTML ni enlaces.
- Esto deja fuera, por diseño, la familia de problemas que trae dejar que el modelo programe el documento.

## 4. Riesgos y cómo se cubren

| # | Riesgo | Cómo se cubre |
|---|---|---|
| 1 | **Fuga entre usuarios:** el modelo referencia un conjunto de otra conversación o de otro usuario. | El servidor solo acepta conjuntos de la **misma conversación y del mismo dueño** (usuario y base del ERP). Si no, se rechaza. |
| 2 | **Datos que el usuario no puede ver.** | Los conjuntos ya nacen filtrados por P1: los campos sin permiso nunca entran. El documento no consulta la base por su cuenta. |
| 3 | **Inyección de fórmulas en Excel y CSV:** un nombre del ERP como `=HYPERLINK("http://...")` se ejecuta al abrir el archivo. | Toda celda de texto se escribe como texto. Las que empiezan con `=`, `+`, `-`, `@`, tabulador o retorno de carro se neutralizan con `'` delante, también en CSV. Los números y las fechas se escriben con su tipo. |
| 4 | **Contenido activo:** macros, enlaces externos, imágenes remotas. | Solo `.xlsx` y `.docx`, nunca `.xlsm` ni `.docm`. Sin hipervínculos. Las imágenes solo pueden ser el logo de la empresa, guardado en SAVI; nada se descarga de una URL, lo que evita SSRF. |
| 5 | **Instrucciones escondidas en los datos:** un campo del ERP que dice "ignora las instrucciones". | Las filas no pasan por el modelo para armar la tabla (§3), y se renderizan como datos. |
| 6 | **Contenido fuera de tema:** "hágame un ensayo de historia en PDF". | La especificación la escribe el mismo modelo, con las mismas reglas del prompt de SAVI: se niega igual que en el chat. Un documento sin tablas del ERP se permite si el tema es del negocio, como una carta de cobro o un acta (§8). |
| 7 | **Datos internos en el archivo:** SQL, nombres de herramientas, modelo, rutas. | La especificación no tiene campos para eso. Los metadatos del archivo (autor, título) los pone el servidor: autor "SAVI" y el nombre de la empresa. |
| 8 | **Archivos gigantes o generación que no termina.** | Hasta 10.000 filas por tabla (P2), hasta 10 tablas y 200 bloques por documento, y un tiempo máximo de generación. Se genera en un hilo aparte, para no frenar el chat. |
| 9 | **Descarga por terceros.** | Mismo criterio que los adjuntos actuales (`conversations/.../attachment_routes.py`): el archivo pertenece al dueño de la conversación. Se sirve con `Content-Disposition: attachment`, el MIME correcto, `X-Content-Type-Options: nosniff` y un nombre de archivo saneado. |
| 10 | **Retención.** | Se guarda con la conversación, se borra con ella, y vence a los 90 días como los conjuntos (P2). |
| 11 | **Datos personales en archivos.** | Cada documento o exportación con datos personales (P1) queda auditado: quién, cuándo, qué conjunto y qué formato. Las descargas también. |
| 12 | **Números del texto que no coinciden con la tabla.** | Es el riesgo que queda: el párrafo lo escribe el modelo. Se mitiga con el bloque `datos_clave`, que puede tomar sus valores de los totales del conjunto en vez de escribirlos el modelo, y con la regla del prompt de citar solo cifras de los resultados. |

## 5. Componentes

### 5.1 Backend

- **Módulo nuevo `documents`** (Clean Architecture, como los demás):
  - dominio: la especificación (`DocumentSpec`, con bloques tipados), sus límites y sus errores;
  - aplicación: validar la especificación, resolver los conjuntos con control de dueño y generar;
  - infraestructura: un generador por formato y la persistencia del archivo.
- **Generadores**, todos en Python puro, para que entren en el instalador de PyInstaller sin dependencias del sistema:

  | Formato | Librería | Licencia |
  |---|---|---|
  | Excel | `openpyxl` | MIT |
  | Word | `python-docx` | MIT |
  | PDF | `reportlab` | BSD |
  | CSV | `csv` de la biblioteca estándar | — |

  Se descartan WeasyPrint (necesita GTK en Windows) y fpdf2 (LGPL, delicada de empaquetar en un ejecutable).
- **Archivo generado:** una entidad como `ChatAttachment` (metadata en una tabla, bytes en otra), atada al mensaje del asistente, con `kind = generated`.
- **Endpoints:**
  - `POST /result-sets/{id}/export?format=xlsx|csv|pdf`, para el botón Exportar;
  - `GET /files/{id}`, para descargar. Los dos controlan el dueño.

### 5.2 Herramienta del chat, dentro del límite de 4

Hoy un administrador tiene las 4 permitidas: `info_empresa`, `consultar_datos`, `consultar_libre` y `consultar_conocimiento`. Agregar una quinta rompe la regla de CLAUDE.md (modo "deferred tools").

**Propuesta:**

- `info_empresa` pasa a ser un tipo más de `consultar_conocimiento`, que ya es un dispatcher de 7 tipos. Los datos de la empresa son conocimiento de la empresa.
- El lugar que queda libre lo ocupa **`entregar_archivo`**, un dispatcher con dos tipos:
  - `exportar`: un conjunto y un formato (P2, "pásemelo en Excel");
  - `documento`: la especificación de §3.
- Hay que correr el checklist de `backend/docs/mcp_deferred_tools_gotcha.md` y medir con los tres proveedores que `info_empresa` sigue funcionando dentro de `consultar_conocimiento`.

### 5.3 Frontend

- La **tarjeta de archivo** en el mensaje del asistente: nombre, formato, tamaño y "Descargar".
- La **tabla del chat** se arma desde el conjunto (P2), con su botón Exportar, que llama al endpoint. La exportación ya no se hace en el navegador.
- Se quita la dependencia `xlsx` (SheetJS 0.18.5, la última publicada en npm, que tiene avisos de seguridad conocidos en la lectura de archivos). Hoy solo la usamos para escribir, pero al pasar la exportación al servidor deja de hacer falta.

### 5.4 Presentación

- Una plantilla por formato: encabezado con el nombre de la empresa (y su logo, si se cargó), título, fecha y hora de generación, y "Generado por SAVI con datos del ERP al <fecha>".
- Tablas con encabezados claros, montos con separador de miles y signo $, y fechas en formato colombiano.
- Excel: una hoja por tabla, encabezado fijo, filtros y ancho de columnas ajustado.
- PDF horizontal automático si la tabla tiene muchas columnas.

## 6. Fases

1. **F1, exportación (P2):** conjuntos de resultados, botón Exportar y `entregar_archivo` con el tipo `exportar`. Excel, CSV y PDF de tabla.
2. **F2, documentos:** el tipo `documento` en Word y PDF, con texto, varias tablas y datos clave.
3. **F3, presentación de la empresa:** logo y colores por base del ERP, y gráficos simples (barras y torta) generados por el servidor desde un conjunto.

F1 es la base de F2, y F2 es lo que pidió el cliente.

## 7. Criterios de aceptación

1. "Páseme en Excel los clientes que compraron LLANTAS0183, con teléfono": un `.xlsx` con todas las filas, los teléfonos solo si el usuario tiene permiso (P1), descargable desde la respuesta.
2. "Informe de llantas sin movimiento en PDF": un PDF con título, resumen, la tabla completa y la fecha de los datos.
3. Una celda del ERP con `=1+1` o `=HYPERLINK(...)` aparece como texto en Excel y en CSV (test).
4. Una especificación que referencia un conjunto de otra conversación se rechaza (test).
5. Una especificación con HTML, una URL de imagen o un bloque desconocido se rechaza (test).
6. Otro usuario no puede descargar el archivo (403 o 404).
7. "Hágame un ensayo de historia en Word" se niega como en el chat.
8. Siguen registradas a lo sumo 4 herramientas, y `info_empresa` responde igual que antes dentro de `consultar_conocimiento` con los tres proveedores.
9. El instalador compilado genera los tres formatos en un Windows limpio.
10. Textos visibles de usted; Ruff, Pyright strict, vue-tsc, Biome y Vitest en verde.

## 8. Decisiones abiertas

1. ~~¿Se permiten documentos sin datos del ERP?~~ **Cerrada (2026-11-11):** sí, si el tema es del negocio (una carta de cobro, un acta), con las mismas reglas del chat.
2. **Logo y colores de la empresa (F3):** quién los carga y dónde. Propuesta: el administrador, en la Administración de SAVI.
3. **Cartas masivas** (una carta por cliente): fuera de alcance por ahora; queda anotado.
