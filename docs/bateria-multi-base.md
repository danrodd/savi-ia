# Batería multi-base — resultados

> Validación de punta a punta de SAVI con **tres ERP de clientes distintos**,
> pensada para el uso de soporte: una sola sesión que abre chats contra cada
> cliente. Corrida el 2026-09-23 con Claude, Gemini y OpenAI.

---

## Resumen

| | Resultado |
|---|---|
| Tanda 1 (datos básicos) | **45/45** — OpenAI 18/18 · Gemini 18/18 · Claude 9/9 |
| Tanda 2 (resto de la batería manual) | OpenAI **28/28** · Gemini **26/28** (2 respuestas válidas con otro criterio, ver [tanda 2](#tanda-2--el-resto-de-la-batería)) |
| Chequeos del flujo multi-base (API) | **33/33** — login, selector, chat cruzado, rechazos, identidades, consumo |
| Interfaz (Playwright) | ✅ selector con las 3 bases, chat en FRAMI desde la sesión de farmacias, historial por base, consumo por cliente |
| Fugas de datos entre clientes | **Ninguna**: cada base probada contra los clientes exclusivos de las otras dos |
| Bugs encontrados y corregidos | **12**, cada uno con test que lo reproduce (ver [abajo](#bugs-encontrados-y-corregidos)) |
| Tests | Backend 715 · Frontend 118 — todos pasan |

La primera corrida **no** salió limpia: OpenAI 17/18 y Gemini 16/18. Los
fallos eran bugs de SAVI, no de los modelos, y la mayoría existía solo en
los clientes nuevos o en el uso cruzado, que nunca se habían probado.

---

## Las tres bases

| Código | Empresa | NIT | Negocio | Ventas | Facturas |
|---|---|---|---|---|---|
| `FARMACIAS_SIMILARES` | FARMACIAS DE SIMILARES COLOMBIA SAS | 901817612 | Farmacia | 2025-05 → 2026-08 | 699.134 |
| `FRAMI` | FRAMI S.A.S. | 901199649 | Insumos para muebles | 2020-01 → 2026-09 | 85.087 |
| `SUR_ANDINA` | SUR ANDINA DE SERVICIOS S.A.S. | 900136563 | Taller automotriz | 2019-01 → 2026-09 | 6.604 |

Hasta esta prueba, las 152 conversaciones de SAVI eran todas de
farmacias_similares: frami y sur_andina nunca se habían usado por chat.

---

## Cómo se probó

### Usuario de soporte de QA

El único código que existe en los tres ERP es `SEO` (el usuario de soporte
de SEO Group, admin en los tres). Para no usar ni tocar un usuario real se
creó **`SAVIQA` / `123`** en las **copias locales** de los tres ERP,
clonando el perfil de `SEO` (admin, activo), pero con claves propias: no se
copiaron las claves secundarias de `SEO`.

Para borrarlo, en cada base:

```sql
DELETE FROM "Seguridad"."Usuario" WHERE codigo = 'SAVIQA';
```

> **Dato operativo para soporte**: un usuario común puede abrir chats
> contra un cliente solo si su **código existe y está activo en el ERP de
> ese cliente**; los permisos salen de esa base.
>
> Excepción: el **administrador de la instalación** (los códigos de
> `SAVI_ADMIN_LOGINS`, o el administrador de la base por defecto) ve
> **todas** las bases activas y entra como administrador aunque su código
> no exista ahí (`a4b1202`). `admin` de farmacias ve las tres; el `admin`
> de sur_andina, que es otra persona con el mismo código, no.

### Validación automática

Cada pregunta abre **su propia conversación atada a la base** (`POST
/conversations` con `erp_database_id`) desde la sesión de `SAVIQA`, que
inició sesión en farmacias. Se compara contra el valor esperado calculado
directo en el ERP. Los montos se aceptan con un **0,1% de tolerancia**, que
cubre redondeos como "$11.503 millones". Después se revisó cada respuesta a
mano: el validador automático dejó pasar un error real con la tolerancia
inicial del 1% (ver bug 3).

Claude corrió en modo reducido (3 preguntas por base) por costo.

---

## Resultados por proveedor y base

### Preguntas

| # | Pregunta | Qué valida | farmacias | frami | sur_andina |
|---|---|---|---|---|---|
| 1 | ¿Cuál es el NIT y la razón social de mi empresa? | `info_empresa` lee la base correcta | 901817612 | 901199649 | 900136563 |
| 2 | ¿Cuánto facturamos en total en 2025? | Ventas por rango de fechas | $11.502.656.749 | $8.369.900.211 | $1.563.879.082 |
| 3 | ¿Cuánto nos ha comprado el cliente *de otra base*? | **Aislamiento**: tiene que decir que no existe | MUEBLES PAOLA → no | EQUIRENT → no | FARMA4NF → no |
| 4 | ¿Cuánto nos ha comprado el cliente *propio*? | Búsqueda de cliente por nombre | FARMA4NF $5.051.301.743 | MUEBLES PAOLA $1.602.029.920 | EQUIRENT $1.180.977.341 (3 razones sociales) |
| 5 | ¿Cuáles fueron nuestros 3 mejores clientes en 2025? | Ranking con nombres reales | Consumidor final, FARMA4NF, AXDA | CONSUMIDOR FINAL, FABRIDEC, HERCAL | ELECTROHUILA, SUNNY APP, ALLIANZ |
| 6 | ¿Cuánto nos deben los clientes en cartera vencida? | Cartera sin mezclar notas crédito | $2.194.293.206 | $996.154.639 | $42.368.928 |

Claude corrió las preguntas 1 a 3.

### Corrida final

| Proveedor · modelo | farmacias | frami | sur_andina | Costo total | Tiempo/turno | Tools/turno |
|---|---|---|---|---|---|---|
| OpenAI · gpt-6-luna | 6/6 | 6/6 | 6/6 | **USD 0,0060** | 7,6 s | 1,3 |
| Gemini · gemini-flash-lite-latest | 6/6 | 6/6 | 6/6 | USD 0,1403 | 6,6 s | 1,8 |
| Claude · claude-sonnet-5 (3 preguntas) | 3/3 | 3/3 | 3/3 | USD 0,1411 | 14,8 s | 1,4 |

Por pregunta, Claude cuesta ~USD 0,016, Gemini ~0,008 y OpenAI ~0,0003.

### Evolución

| Corrida | OpenAI | Gemini | Claude | Qué cambió |
|---|---|---|---|---|
| 1 | 17/18 · costo sin registrar | 16/18 · USD 0,207 | 9/9 · texto pegado | Bugs 1, 2, 3, 4, 5 y 6 sin corregir |
| Final | 18/18 · USD 0,006 | 18/18 · USD 0,140 | 9/9 | Todo corregido |

Gemini bajó un 32% de costo: antes del bug 5 entraba en un loop de **11
consultas SQL libres** buscando un cliente que la consulta normal no podía
encontrar.

---

## Tanda 2 — el resto de la batería

Todo lo de la [batería manual](#batería-manual-para-correr-desde-la-interfaz)
que la tanda 1 no cubría: el segundo cliente ajeno de cada base, conteo de
terceros, periodos relativos, búsquedas por producto, cartera completa,
conocimiento y un tema fuera de alcance. Corrida con OpenAI y Gemini (28
preguntas cada uno).

| Pregunta | farmacias | frami | sur_andina | OpenAI | Gemini |
|---|---|---|---|---|---|
| Cliente de la **otra** base ajena | EQUIRENT → no | FARMA4NF → no | MUEBLES PAOLA → no | ✅ | ✅ |
| ¿Cuántos clientes y proveedores? | 17.914 · 1.940 | 2.102 · 584 | 4.622 · 740 | ✅ | ✅ ¹ |
| Periodo | agosto 2026: $3.305.292.887 | este mes: $167.742.994 | — | ✅ | ✅ |
| Productos / sucursales | PRINCIPAL, SERVICIOS, KENNEDY | TORNILLO MAD 6, ENCHAPE, ZINCADO | aceite: 15W40 | ✅ | ✅ |
| Búsqueda por palabra | — | tornillos 2025: $18.836.361 | — | ✅ | ✅ |
| Serie / promedio | — | año por año 2020 → 2026 | ticket 2025: $2.154.103 | ✅ | ✅ |
| Cartera vencida total | cobrar $2.194 M · NC $97 M · pagar $8.654 M | — | cobrar $42 M · pagar $137 M | ✅ | ⚠️ ² |
| Módulos, permisos, frmReciboCliente | igual en las tres | | | ✅ | ✅ |
| Mundial de 1986 | rechazada | rechazada | rechazada | ✅ | ✅ |

¹ Gemini separa "solo clientes / solo proveedores / ambos" (17.796 + 118 =
17.914): correcto y más detallado.
² Gemini respondió solo lo que deben los clientes. En Colombia "cartera"
suele significar cuentas por cobrar, así que es una lectura válida; OpenAI
da el desglose completo. Es una diferencia de criterio, no un error de
datos.

La primera corrida de la tanda 2 encontró los bugs 10, 11 y 12. Todos
quedaron corregidos antes de la corrida final.

---

## Flujo multi-base — 33/33

| Grupo | Chequeo | Resultado |
|---|---|---|
| **Login** | `SAVIQA`, `SAVIQA@FRAMI`, `SAVIQA@SUR_ANDINA`, `saviqa@frami` (minúsculas), `admin`, `admin@SUR_ANDINA` entran cada uno a su base | ✅ 6/6 — verificado por el `idUsuario` de cada ERP (SAVIQA es 65 / 19 / 22) |
| | `admin@FRAMI` (no existe ahí), `@NOEXISTE`, clave incorrecta, base borrada | ✅ 4/4 rechazados con 401 genérico, sin decir qué falló |
| **Selector** | SAVIQA ve las 3 bases; `admin` ve solo farmacias y sur_andina | ✅ 2/2 |
| **Chat cruzado** | Desde la sesión de farmacias, SAVIQA abre chat en cada base | ✅ 3/3 |
| | El chat en FRAMI responde el NIT de FRAMI | ✅ |
| | La conversación queda guardada con su base y sus mensajes | ✅ |
| | El historial dice de qué base es cada chat | ✅ |
| **Rechazos** | `admin` no puede abrir chat en FRAMI | ✅ 409 `erp_database_unavailable` |
| | Base inexistente o borrada | ✅ 409 |
| | `admin` no ve, no escribe ni borra la conversación de SAVIQA | ✅ 404 ×3 |
| **Identidades** | `SAVIQA@FRAMI` no ve los chats de `SAVIQA` (farmacias): son dos identidades | ✅ |
| | …ni siquiera los que consultan FRAMI | ✅ 404 |
| | Sin elegir base, el chat va a la base de login | ✅ |
| **Consumo** | Cada turno guarda proveedor, modelo, tokens y costo | ✅ 83 turnos, 0 incompletos |
| | El reporte global desglosa por proveedor | ✅ |
| | El reporte global desglosa **por cliente** (base consultada) | ✅ nuevo |
| | Lo que SAVIQA gastó en frami y sur_andina se le atribuye a SAVIQA | ✅ corregido |
| | `?database=<id>` deja solo ese cliente | ✅ nuevo |

---

## Bugs encontrados y corregidos

| # | Bug | Impacto | Cómo apareció | Commit |
|---|---|---|---|---|
| 1 | **Clientes sin nombre.** El nombre saltaba `nombreComercial` vacío pero no `razonSocial` vacía | Las personas naturales quedaban sin nombre y se **fundían en una sola fila**: en frami el "cliente #1" sin nombre sumaba el 61% de la facturación. Afectaba a las tres bases | Perfilando frami | `c2ed90e` |
| 2 | **Cartera mezclaba notas crédito.** El filtro `lado contiene 'clientes'` también matcheaba "Notas crédito a clientes" | "¿Cuánto nos deben?" daba $2.291 M en vez de $2.194 M en farmacias | OpenAI, corrida 1 | `b4dd6c7` |
| 3 | **El último día de un rango quedaba afuera.** `BETWEEN '2025-01-01' AND '2025-12-31'` sobre una columna timestamp corta a la medianoche del 31 | Facturación 2025 de farmacias −$17,9 M; **todo total mensual perdía su último día**; `fecha = hoy` casi no matcheaba | Revisión manual (el 1% de tolerancia lo dejó pasar) | `b4d4994` |
| 4 | **Columna inexistente** `t."activo"` en el catálogo de terceros (la real es `estado`) | Toda búsqueda de un tercero en modo detalle fallaba y el modelo decía que el cliente **no existía** | Gemini, corrida 1 | `8dc7ac0` |
| 5 | Sin filtro de **ventas por nombre** de cliente ni de producto | "¿Cuánto nos compró X?" exigía encadenar dos consultas; "¿cuánto vendimos de tornillos?" era imposible | Gemini, corrida 1 | `675ebb8` |
| 6 | **Texto pegado.** El preámbulo antes de una tool quedaba unido a la respuesta | "Déjame revisar los datos...**En** 2025 facturaste", en pantalla y en el mensaje guardado | Claude, corrida 1 | `cbba283` |
| 7 | **Consumo atribuido a otra persona.** El ranking por usuario agrupaba por la base *consultada* | Lo que soporte gastaba consultando a frami se le sumaba **al usuario de frami con el mismo id** | Revisión del flujo | `5404671` |
| 8 | **Usuarios activos fusionados.** El conteo agrupaba solo por `idUsuario` | `admin` (id 1) de farmacias y `admin` (id 1) de sur_andina contaban como una persona | Revisión del flujo | `5404671` |
| 9 | **No había consumo por cliente** | Soporte no podía ver cuánto costó atender a cada cliente | Revisión del flujo | `5404671` + `7eb46e4` (vista) |
| 10 | **`contiene` buscaba la frase literal** | "tornillos" no encontraba "TORNILLO MAD 6 * 2" (49 unidades en vez de 395.507); "aceite de motor" no encontraba "ACEITE MOTOR 15W40" | Tanda 2 | `ecbbf18` |
| 11 | **El modelo no sabía la fecha de hoy** | "¿Cuánto vendimos este mes?" consultó marzo de 2025 un 23 de septiembre de 2026 | Tanda 2 | `be67c63` |
| 12 | **Un cliente parecido presentado como el pedido** | En frami, "FARMA4NF" (no existe) → Gemini respondió con el monto de DROGUERIA FUNDAFARMA | Tanda 2 | `43b1b56` |

También se mapeó el `tipoDocumento 13` (devolución en compras, solo en
frami) en cartera (`c2ed90e`), y el test del catálogo contra el ERP real
ahora corre sobre las **tres** bases y recorre **cada** campo, métrica,
dimensión y filtro. Así se atrapa un bug como el 4 antes de que llegue a un
usuario.

### Configuración corregida (sin commit)

- **El precio de gpt-6-luna se había borrado** de la configuración de
  OpenAI (en algún momento entre las 21:47 y las 00:06). Las respuestas
  quedaban sin costo registrado. Se reconstruyó con exactitud a partir de
  los 9 turnos que sí lo tenían: input USD 0,10 · output 0,50 · cache 0,01
  por millón. No se identificó qué lo borró: activar el proveedor no lo
  toca. Si vuelve a pasar, el panel de consumo lo avisa como "respuestas
  sin tarifa".

### Falsa alarma

- Los 9 registros `PRUEBAEXP` que aparecen en `erp_databases` están
  **borrados** (soft delete) y el índice único de `code` solo aplica a los
  no borrados. Es el comportamiento correcto.

---

## Pendientes (no bloquean)

| Tema | Detalle |
|---|---|
| ~~La sesión no dice en qué base está~~ | ✅ Resuelto (`5718433`, `638db1f`): login, `/auth/me` y bootstrap devuelven la base; la tarjeta de usuario la muestra. |
| ~~"· vos" en el ranking~~ | ✅ Resuelto (`3461bbc`): compara id y base de login. |
| ~~Filtro por cliente en la interfaz~~ | ✅ Resuelto (`3461bbc`): chips por cliente en las vistas de consumo. El selector del chat ahora es un buscador (`638db1f`). |
| **SQL libre para soporte** | Los usuarios de soporte son admin, así que tienen `consultar_libre`. Antes del bug 5, Gemini lo usó 11 veces en un turno. Conviene vigilar el costo por turno de soporte. |
| **Notas crédito** | Solo farmacias tiene notas crédito con saldo vivo. Quedan en su propio bucket; si el negocio define que restan de la cartera, se cambia en `cartera.py`. |
| **Productos que no son productos** | En farmacias, el "producto" más vendido es `REINTEGRO GASTOS COMUNES EXCLUIDO` (línea contable). Es el dato del ERP, no un error de SAVI. |

---

## Batería manual (para correr desde la interfaz)

Mismas preguntas para las tres bases, con la respuesta esperada. Entrar con
`SAVIQA` / `123` y abrir cada chat eligiendo la base en el selector.

> Todas estas preguntas ya corrieron automáticamente (tandas 1 y 2) y el
> recorrido por la interfaz se verificó con Playwright. Esta sección queda
> para repetir la prueba a mano, por ejemplo después de agregar un cliente
> nuevo.

### Aislamiento — la misma pregunta, tres respuestas

| Pregunta | farmacias | frami | sur_andina |
|---|---|---|---|
| `¿Cuál es el NIT de mi empresa?` | 901817612 | 901199649 | 900136563 |
| `¿Cuánto facturamos en 2025?` | $11.502.656.749 | $8.369.900.211 | $1.563.879.082 |
| `¿Cuántos clientes y proveedores tenemos?` | 17.914 · 1.940 | 2.102 · 584 | 4.622 · 740 |
| `¿Cuánto nos compró FARMA4NF?` | $5.051.301.743 | no existe | no existe |
| `¿Cuánto nos compró MUEBLES PAOLA?` | no existe | $1.602.029.920 | no existe |
| `¿Cuánto nos compró EQUIRENT?` | no existe | no existe | $1.180.977.341 |

Si dos bases dan el mismo número, o una encuentra el cliente de otra, **es
el fallo más grave posible**: datos de un cliente en la sesión de otro.
ELECTROHUILA existe en frami **y** en sur_andina, así que no sirve como
marcador.

### Por base

**farmacias_similares** — termina en agosto de 2026, así que "este mes" da
vacío y eso es correcto.

| Pregunta | Esperado |
|---|---|
| `¿Cuánto facturamos en agosto de 2026?` | $3.305.292.887 en 63.321 facturas |
| `¿Cuáles son las 3 sucursales que más venden?` | PRINCIPAL, SERVICIOS, DROGUERIAS DEL DR SIMI KENNEDY |
| `¿Cuál es nuestra cartera vencida total?` | Desglosada: por cobrar $2.194 M · notas crédito $97 M · por pagar $8.654 M |

**frami** — la única con 6 años de historia.

| Pregunta | Esperado |
|---|---|
| `¿Cuánto vendimos este mes?` | $167.742.994 en 258 facturas |
| `¿Cuáles son los productos más vendidos?` | TORNILLO MAD 6 * 2", SERVICIO ENCHAPE MATERIAL 15 MM FL, TORNILLO MAD ZINCADO 6 * 2 |
| `¿Cuánto vendimos de tornillos en 2025?` | $18.836.361 en 395.507 unidades |
| `¿Cómo evolucionó la facturación año por año desde 2020?` | Serie 2020 → 2026 |

**sur_andina** — 100 veces menos facturas que farmacias.

| Pregunta | Esperado |
|---|---|
| `¿Qué aceite de motor se vende más?` | ACEITE MOTOR 15W40, luego 20W50 y 5W30 SINTETICO |
| `¿Cuál es el ticket promedio de 2025?` | $2.154.103 |
| `¿Cuál es nuestra cartera vencida total?` | Por cobrar $42 M · por pagar $137 M (debe más de lo que le deben) |

### Igual en las tres

`¿Qué módulos tiene el sistema?` · `¿Cómo le asigno permisos a un usuario?`
· `¿Para qué sirve el formulario frmReciboCliente?` → la misma respuesta en
las tres. `¿Quién ganó el mundial de 1986?` → rechazada en las tres.

### Consumo

En **Administración → Consumo → Global**, la sección **Por cliente (base
consultada)** muestra cuánto costó cada base, y el ranking por usuario
muestra la base de login junto al id.
