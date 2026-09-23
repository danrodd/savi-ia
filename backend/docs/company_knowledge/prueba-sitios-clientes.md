# Prueba con sitios web reales de clientes

> Parte de: [Fase 5 — Importar desde la web](05-fase-importar-desde-web.md)
> (orden acordado: probar con sitios reales antes de construir).
> Fecha: 2026-09-23. Scripts: `backend/scripts/prueba_sitios_clientes.py`
> (extraer y subir) y `backend/scripts/bateria_web_clientes.py` (preguntas).
> Solo **descarga simple**, sin navegador. El contenido extraído se subió
> como documentos Markdown al pipeline actual. Proveedor: OpenAI
> `gpt-6-luna`.

## Resultado

| | Primera corrida | Después de las correcciones (2 corridas) |
|---|---|---|
| SEO Group (seo-erp.com) | 5/8 | **8/8** y 7/8 |
| Farmacias de Similares | 4/6 | 4/6 y 5/6 |
| Sur Andina | 4/8 | **8/8** y **8/8** |
| Separación entre bases | 2/2 | 2/2 y 2/2 |
| **Total** | **15/24** | **22/24** y **22/24** |

Las fallas que quedan **no son errores de SAVI** (revisadas a mano, §4).
La batería de [permisos y bases](bateria-permisos-bases.md) siguió en
**35/35** con los 111 documentos web cargados.

**Conclusión: la descarga simple alcanza para los tres sitios.** Ninguno
necesitó navegador. Lo que sí hizo falta fue limpiar la plantilla, elegir
secciones y leer datos estructurados (§2), y la prueba destapó un **bug
del fragmentador de Markdown** que también afectaba a los documentos
subidos a mano (§3.1).

## 1. Los sitios

| Sitio | Tecnología | Cómo se descubrieron las páginas | Documentos | Palabras |
|---|---|---|---|---|
| **seo-erp.com** | WordPress 7.1 + WooCommerce + Elementor | `wp-sitemap.xml` | 19 | 4.310 |
| **surandina.com.co** | HTML estático con jQuery, sin `robots.txt` ni sitemap | Siguiendo links | 17 (incluye un PDF) | 5.658 |
| **farmaciasdesimilares.com** | VTEX IO (React con SSR), tienda de la cadena mexicana | Sitemap: 9 rutas, 115 categorías, 1.362 productos | 75 | 7.822 |

Alcance: SEO Group quedó visible en **todas** las bases (es el proveedor
del ERP); Sur Andina solo en `SUR_ANDINA` y Farmacias solo en
`FARMACIAS_SIMILARES`. Tope de la prueba: 60–80 páginas por sitio.

## 2. Lo que hizo falta además de la extracción del spike

| Problema real | Sitio | Solución (con código, sin IA) |
|---|---|---|
| El menú, el pie con teléfonos, el carrito y el login se repiten en cada página: el tema (Elementor) los arma con `div`, no con `header`/`footer`, así que no se reconocen por etiqueta | SEO | **Quitar la plantilla por repetición**: un bloque presente en la mitad o más de las páginas del sitio se saca de cada página y se guarda **una vez** en "Información general del sitio" (así los teléfonos y la dirección no se pierden). SEO pasó de 31.604 a 4.310 palabras útiles. |
| **Contenido de demostración del tema**: 17 entradas de blog sobre bicicletas Trek, "sample-page", copias `cart-2`, `my-account-2` | SEO | **Elegir secciones del sitemap** (entradas, páginas, productos, categorías) y excluir rutas de cuenta y carrito, también con sufijo `-2`. |
| Una página de FAQ en *lorem ipsum* ("Juliette", "Sportie") | SEO | Se dejó cargada como prueba: SAVI no la usó. En el módulo, la vista previa debe detectar *lorem ipsum* y proponer excluirla. |
| La página de producto no trae el nombre ni el precio como texto visible | Farmacias | **Datos estructurados `schema.org/Product`** (JSON-LD): nombre, SKU, marca, precio, moneda y disponibilidad. Los traen WooCommerce, VTEX y Shopify. |
| Precios partidos en líneas (`$` / `31` / `.` / `00`) | Farmacias | Normalización del texto: `$31.00`. |
| Moneda solo como código (`MXN`): "¿en qué moneda?" no la encuentra | Farmacias | Nombre de la moneda junto al código: "pesos mexicanos (MXN)". |
| Título de la página tomado mal ("Comentarios") | Farmacias | Primer título del contenido antes que los metadatos. |
| **Límite de 30 subidas por hora por usuario** | todos | Es para subidas manuales. El módulo web crea los documentos por dentro y no pasa por él (la prueba lo subió solo en el backend local). |

## 3. Defectos encontrados y corregidos

### 3.1 El fragmentador de Markdown perdía los títulos (bug anterior)

`StructuralChunker._markdown_blocks` sacaba los títulos del texto y solo
guardaba el primero como metadato del fragmento. Dos efectos:

- Un fragmento que agrupaba varias secciones perdía el nombre de todas
  menos la primera: en "Recompra de folios" quedaban los precios **sin el
  nombre del plan** ("¿cuánto vale el plan R-B?" → "no identifica un plan
  R-B").
- Un título **sin párrafo debajo** se perdía entero. El contrato de
  transporte de Sur Andina tiene cada cláusula escrita como título ("hasta
  15 kilos de equipaje…"), y las sedes también: **nada de eso llegaba al
  índice**. SAVI buscaba, no encontraba y respondía "solo puedo ayudarte
  con temas del ERP".

Afectaba también a los documentos Markdown subidos a mano. Corregido: el
título va dentro del texto del bloque (pegado al primer párrafo de su
sección, o solo si la sección no tiene cuerpo). Tests: los dos casos
anteriores fallan sin la corrección. Los documentos ya cargados conservan
sus fragmentos viejos hasta que se reprocesan.

### 3.2 SAVI relacionaba datos por el orden de una tabla

En la tabla de tarifas de Sur Andina **el nombre de cada ruta es una
imagen** (`r01-rutas.png`, sin texto alternativo). SAVI respondió
"Medellín–Concordia cuesta $56.000", deduciéndolo por el orden. Regla
nueva en el prompt: no relacionar datos que el documento no relaciona;
decir qué datos aparecen y que no se indica a cuál corresponde cada uno.
Después: "los documentos no indican el precio del pasaje" y da la línea de
compra.

### 3.3 "Despachos diarios" se buscó solo en el ERP

"¿Cuántos despachos diarios hacen?" hizo 10 consultas al ERP buscando
remisiones y nunca miró los documentos. La regla "si no aparece en el
ERP, buscá en los documentos" valía solo para productos; ahora vale para
cualquier dato (despachos, rutas, tarifas, horarios).

## 4. Preguntas (corrida final)

| # | Pregunta | Respuesta de SAVI | |
|---|---|---|---|
| W01 | ¿Cuánto cuesta el plan POS-20? | $800.000 al año, IVA incluido, hasta 20.000 folios | ✔ |
| W02 | Plan R-B de recompra de folios | 24 diarios, 720 mensuales, 8.640 al año; $411.300/mes | ✔ |
| W03 | Oficinas y soporte técnico de SEO | Calle 5 # 9-42, Edificio Palermo; 311 531 0210 / 316 559 2019. Señaló que el sitio da **dos direcciones** distintas | ✔ |
| W04 | Desde qué año y de qué empresa | 1991; A&E Soluciones Integrales S.A.S. | ✔ |
| W05 | Recepción electrónica de 2.000 transacciones | REC-2000: $400.000, IVA incluido | ✔ |
| W06 | ¿Los productos contienen gluten? (FAQ de relleno) | No usó el *lorem ipsum* | ✔ |
| W07 | ¿SEO vende bicicletas? (demo excluida) | "No aparecen bicicletas" | ✔ ¹ |
| W08 | Plan POS de 50.000 folios, **usuario no administrador en otra base** | $2.000.000 al año | ✔ |
| F01 | Amlodipino 5 mg | $35 pesos mexicanos (MXN) en la tienda; mencionó también lo que hay en el ERP | ✔ |
| F02 | Oseltamivir | 75 mg, 10 cápsulas, $299 MXN | ✔ |
| F03 | Geles y cremas tópicas para el dolor | Diclofenaco, gel de mentol/árnica, ungüento de árnica, con precios | ✔ |
| F04 | Hidratasim Zero | $25,50, tres sabores | ✔ |
| F05 | ¿En qué moneda están los precios? | "No se especifica" | ✘ ² |
| F06 | ¿Venden llantas? | "No" | ✔ ¹ ³ |
| S01 | Despachos diarios y municipios | Cerca de 60; Medellín, Concordia, Altamira, Güintar, Carmen de Atrato | ✔ |
| S02 | Kilos de equipaje sin pagar | Hasta 15 kilos | ✔ |
| S03 | Anticipación en la terminal | Media hora antes | ✔ |
| S04 | Taquilla en Medellín | Cra. 65 # 8B-91, taquilla 4, Terminal del Sur | ✔ |
| S05 | Primer bus a El Carmen de Atrato | 5:30 a. m.; llega 9:58 a. m. | ✔ |
| S06 | Pasaje a Bolombolo | $25.000 | ✔ |
| S07 | Pasaje a Concordia (ruta en imagen) | "Los documentos no indican el precio" + línea de compra | ✔ |
| S08 | Teléfono para comprar tiquetes | (604) 322-4754 y WhatsApp 314-797-1053 | ✔ |
| X01 | Pregunta de Sur Andina en el chat de Farmacias | No la responde | ✔ |
| X02 | Precio de Farmacias en el chat de Sur Andina | No lo responde | ✔ |

¹ El evaluador automático la marca como falla porque busca frases como
"no encontré"; la respuesta es correcta.
² Límite del sitio: ninguna página dice en general que los precios son en
MXN; solo cada producto. SAVI no inventó.
³ Observación: respondió con los productos de SEO Group ("venden
software, no llantas"), porque el sitio de SEO es visible en todas las
bases. Para el usuario de una farmacia, "tu empresa" es la farmacia, no
el proveedor del ERP. Ver §5.

## 5. Qué entra en la especificación

- Extracción: la híbrida del spike **más** la limpieza de plantilla por
  repetición, `schema.org` (Product, Organization, LocalBusiness), la
  normalización de precios y el nombre de la moneda.
- Vista previa: mostrar las **secciones del sitemap** con cuántas páginas
  tiene cada una para que el administrador excluya (entradas de demo,
  categorías), y marcar páginas con *lorem ipsum*.
- Los documentos de la fuente web se crean sin pasar por el límite de
  subidas por usuario.
- Contenido del proveedor del ERP (el sitio de SEO Group) visible para
  todos: SAVI debe distinguirlo del de la empresa del usuario. Se evalúa
  en la implementación (etiqueta de origen en la fuente, o regla del
  prompt).
- Texto dentro de imágenes (nombres de rutas de Sur Andina): sigue fuera
  del alcance (etapa 5.1 con IA). Mientras tanto SAVI dice que no lo
  sabe en vez de adivinar.
- **Navegador: no hizo falta en ningún sitio.** Se mantiene como
  componente opcional posterior.

## 6. Cómo volver a correrla

Con el backend en `localhost:8000` (para la prueba local se arrancó con
`RATE_LIMIT_UPLOAD_PER_HOUR=1000`):

```powershell
cd backend
uv run --with trafilatura --with markdownify python scripts/prueba_sitios_clientes.py extraer
uv run python scripts/prueba_sitios_clientes.py subir
uv run python scripts/bateria_web_clientes.py
```
