# Revisión de la interfaz de documentos

> Fecha: 2026-09-15 · Pantalla `/admin/conocimiento`, revisada con 10 documentos
> reales cargados, en escritorio (1440 px) y móvil (400 px), más lectura del código.

## Veredicto

La pantalla es **correcta y consistente** con el resto de la administración.
Funciona de punta a punta, los permisos se entienden y los errores se
explican. **No está a la altura de "moderna e intuitiva" en tres puntos**, que
son los que siente un administrador con documentos grandes o muchos documentos:

1. No se ve el **avance** de un documento largo: "Procesando…" durante casi 2 minutos sin más información.
2. En **móvil**, las acciones de cada fila quedan escondidas a la derecha de la tabla.
3. Con **muchos documentos** no hay forma de buscar ni filtrar.

## Qué está bien

| Aspecto | Detalle |
|---|---|
| Subida | Arrastrar y soltar, varios archivos a la vez, título editable por archivo, estado de cada uno (subido, duplicado con el nombre del existente, rechazado con motivo). |
| Permisos | Preguntas en lenguaje claro ("¿Quién puede consultar este documento?") con una ayuda debajo de cada opción. |
| Estados | Insignias con color y punto animado mientras procesa. La animación respeta `prefers-reduced-motion`. |
| Actualización | La lista se refresca sola cada 3 s mientras haya documentos en proceso, y se detiene cuando no. |
| Probar búsqueda | Deja verificar qué encontraría SAVI y qué documentos quedan excluidos para un usuario concreto, antes de que alguien pregunte. |
| Eliminar | Pide confirmación y explica la consecuencia. |
| Privacidad | Aviso de que los fragmentos se envían al proveedor de IA. |
| Diálogos en móvil | Se adaptan bien a 400 px. |

## Problemas encontrados

Prioridad: **Alta** = lo nota cualquier administrador · **Media** = molesta en
casos frecuentes · **Baja** = pulido.

| # | Prioridad | Problema | Evidencia | Propuesta |
|---|---|---|---|---|
| 1 | Alta | **Sin avance ni tiempo estimado.** Un PDF de 500 páginas muestra "Procesando…" ~1 min 45 s. En cola no se sabe cuántos hay delante. | [Validación de importación](validacion-importacion.md): ~0,2 s por página, de a uno. | Mostrar "Procesando 120 de 500 fragmentos" con barra, y "En cola (2 antes)". Requiere que el backend guarde el avance. |
| 2 | Alta | **Acciones ocultas en móvil.** La tabla hace scroll horizontal y "Editar / Reemplazar / Eliminar" quedan fuera de la pantalla. | Captura a 400 px: solo se ven Documento, Quién lo ve, Bases y Estado. | Debajo de ~720 px, mostrar tarjetas en lugar de tabla, o un menú "⋯" por fila. |
| 3 | Media | **Soltar un archivo fuera de la zona** hace que el navegador abra el archivo y se pierda la pantalla. | Código: solo la zona punteada cancela el `drop`; ni el diálogo ni la página lo hacen. Es el comportamiento estándar del navegador. | Aceptar el `drop` en todo el diálogo (o cancelarlo a nivel de ventana mientras está abierto). |
| 4 | Media | **Sin búsqueda, filtro ni orden** en la tabla. | Con 10 documentos ya ocupa la pantalla completa. | Buscador por título y filtro por estado ("con errores", "procesando"). |
| 5 | Media | **Tres botones de texto por fila** siempre visibles: la tabla se ve cargada y "Eliminar" queda al lado de "Reemplazar". | Captura de escritorio. | Dejar "Editar" visible y mover "Reemplazar / Reprocesar / Eliminar" a un menú "⋯". |
| 6 | Media | **El fragmento de "Probar búsqueda" muestra el comienzo del texto, no la parte que coincidió.** En "¿Cómo debo ir vestido?" se ve el artículo del horario aunque la respuesta (uniforme) está más abajo. | Captura de la búsqueda. | Mostrar el pasaje alrededor de los términos coincidentes o resaltar las palabras. |
| 7 | Media | **Páginas imprecisas en documentos de páginas cortas.** El reglamento (4 páginas cortas) quedó en un solo fragmento "p. 1-4". Al abrir la fuente desde el chat, el PDF se abre en la página 1 y no en la 3, donde está la respuesta. | Captura de la búsqueda. En PDF con páginas llenas cada fragmento ≈ 1 página, así que afecta sobre todo a documentos cortos. | Backend: no unir páginas en un mismo fragmento cuando el texto de la página ya es suficiente, o guardar la página donde cae cada párrafo. |
| 8 | Baja | **Títulos con guiones del nombre de archivo** ("politica-devoluciones"). | `titleFromFilename` solo quita la extensión. | Reemplazar `-` y `_` por espacios y poner mayúscula inicial ("Politica devoluciones"); el usuario lo puede corregir igual. |
| 9 | Baja | **Puntajes técnicos sin explicar** ("similitud 0.83 · coincidencia 0.00"). | Captura de la búsqueda. | Tooltip que explique qué es cada uno, o reemplazarlos por "Por significado / Por palabras". |
| 10 | Baja | **Estado vacío sin acción.** "Aún no hay documentos" no tiene botón para subir. | Código de la vista. | Poner el botón "Subir documentos" dentro del estado vacío. |
| 11 | Baja | **Barra de uso casi invisible** (258 de 50.000 fragmentos = 0,5%). | Captura de escritorio. | Mostrarla solo desde un umbral (p. ej. > 50%) o mostrar el porcentaje. |
| 12 | Baja | **"Reemplazar" sin confirmación**: cambia el contenido y reprocesa en el acto. | Código de la vista. | Confirmación breve con el nombre del archivo nuevo. |

## Descartados en la revisión

- **Diálogo translúcido en móvil:** en la primera captura el diálogo se veía transparente, pero era la animación de apertura a mitad de camino. Pasada la animación se ve bien.
- **Scroll horizontal de la página en móvil:** el ancho extra (466 px) viene del contenedor de notificaciones, fuera de pantalla. La página tiene `overflow-x: hidden` y el usuario no llega a ver scroll.

## Orden sugerido

1. **#1 avance del procesamiento** y **#2 acciones en móvil**: son los que más cambian la experiencia.
2. **#3 soltar fuera de la zona**, **#5 menú por fila** y **#4 búsqueda**: rápidos y visibles.
3. **#6 pasaje coincidente** y **#7 páginas**: mejoran la confianza en las citas.
4. El resto, como pulido.
