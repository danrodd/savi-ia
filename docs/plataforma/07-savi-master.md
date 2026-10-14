# SAVI Master — flota gobernada de SEO Group

> Parte de: [PRD — Plataforma SAVI](00-prd.md)
> Estado: **propuesta, pendiente de aprobación**. Fecha: 2026-10-14.
> Origen: requerimiento del usuario (§1). Redefine el orden del plan y
> **corrige** dos supuestos del PRD (§4).
> Relación con otras specs: reutiliza lo ya construido de las
> [Fase 2](02-fase-vinculacion-y-sincronizacion.md) y
> [Fase 3](03-fase-consola-cloud.md) (E2–E4), y vuelve central la
> [Fase 5](05-fase-creditos-gestionados.md) y el endurecimiento de la
> [Fase 1](01-fase-savi-servidor.md).

## 1. Requerimiento original (2026-10-14, textual)

> Si me parece bien, pero también debemos que funcione para un servidor
> linux, muchas empresas sobretodo las grandes podrían despolegarlo con
> docker. Pero para esta primera etapa nosotros queremos desplegarlo en un
> servidor, linux para mas rapido y sencillo, y tener ese SAVI desde el
> internet accesible, que desde alli pudieran ingresar y si hay BDs en ese
> servidor se configuren, probar todo pero sobre todo, hacer la conexiones
> con los instaladores en cada equipo, aun no estamos con ningun cliente
> (no salimos a produccion) por ahora solo los usuarios de servicio al
> cliente y soporte de la empresa SEO, ademas de los gerentes y
> coordinadores. Con esa version que desplegariamos queremos que podamos
> tener controlado cuantos equipos tienen SAVI, porque todos los
> instaladores deberian apuntar a un SAVI Master que seria este, y desde
> alli podriamos ver hay 5 SAVI funcionando en la empresa, que serian de
> los 5 empleados, podriamos habilitarles los proveedores que tengan
> disponibles, que solo puedan configurar claude o gemini, o los dos, que
> desde ese SAVI Master se configuren las claves APIs y se les de acceso a
> ellos, asi podrian elegir si configuran su propia api key si lo tienen
> habilitado o solo la que le definieron, poder definirle cuantos creditos
> tengan, asi controlar eso, si tenemos 50 dolares den gemini, solo
> permitir que use un usuario 5 dolares o a todos solo eso. Si configuramos
> bases de datos tambien lo mismo, el conocimiento tambien lo mismo. Esto
> es supremamente importante para el soporte. Controlar los permisos desde
> alli para que solo tengan acceso a el chat y no a configurar. Si me hago
> entender lo que queremos? ademas de gestionar los clientes que alli si lo
> que podriamos controlar quizas es que proveedores tendria disponible, si
> el cliente nos paga una suscripcion de SAVI que tendria tantos creditos
> entonces desde alli se le asignaria como eso, se le configuraria una API
> KEY exclusiva para ese o que tome la general. O si el decide pagar el
> cliente mismo su suscripcion el mismo la pueda configurar. Y desde alli
> podamos controlar cuantos usuarios la estarian usando, metricas de uso,
> pero en el caso de los clientes si no manejariamos sus datos, ya que debe
> ser privado. Eso es lo que quisieramos lograr.

## 2. Lectura del requerimiento

En una frase: **SEO opera su propio SAVI en un servidor Linux con acceso
por internet, que además es el maestro de todas las instalaciones y
decide qué IA, qué créditos, qué bases, qué conocimiento y qué permisos
tiene cada persona o equipo.** Los clientes, cuando lleguen, son una
segunda capa del mismo mecanismo, con la regla de que SEO no ve sus datos.

### 2.1 Dos mundos que conviven

| | Organización interna (SEO) | Clientes (futuro) |
|---|---|---|
| Quién | Servicio al cliente, soporte, gerentes, coordinadores | Empresas que contratan SAVI |
| Dónde corre el agente | En el Master (internet) y, para soporte, en equipos gestionados | En la red del cliente (PRD §4) o con clave propia |
| Datos del ERP | Del propio SEO: **pueden** vivir en el Master | **Nunca** salen del cliente |
| Identidad de usuarios | Con nombre (decisión pendiente, P2) | Seudónimo |
| Contenido de chats | Puede almacenarse en el Master | Nunca llega a SEO |
| Quién paga la IA | SEO, con presupuesto por persona | Suscripción con créditos, o clave propia del cliente |

### 2.2 Requerimientos derivados

| ID | Requerimiento |
|---|---|
| RM-01 | SAVI corre en un servidor **Linux con Docker** (backend, frontend, Postgres, proxy HTTPS), desplegable con un solo comando. |
| RM-02 | El Master es **accesible por internet** con HTTPS y un dominio de SEO. |
| RM-03 | En el Master, un administrador entra y configura las bases del ERP que estén en ese servidor. |
| RM-04 | **Todos los instaladores apuntan al Master**: cada equipo queda vinculado y se ve en la consola ("hay 5 SAVI funcionando"). |
| RM-05 | El Master decide **qué proveedores** puede usar cada persona o equipo (solo Claude, solo Gemini, ambos). |
| RM-06 | Las **claves de API se configuran en el Master**. Una persona usa la clave que se le define, o la propia **solo si se lo habilitaron**. |
| RM-07 | **Presupuesto en dólares por persona** y por proveedor: con USD 50 en Gemini se puede dar USD 5 a un usuario o a todos. |
| RM-08 | Las **bases del ERP y el conocimiento** se asignan con el mismo criterio: el Master decide quién las usa. |
| RM-09 | **Permisos centrales:** un equipo gestionado solo tiene el chat, sin acceso a configurar. |
| RM-10 | Clientes: el Master decide qué proveedores ve cada uno, le asigna una suscripción con créditos y una clave **exclusiva o la general**. |
| RM-11 | Un cliente puede **pagar y configurar su propia suscripción** (clave propia). |
| RM-12 | El Master muestra cuántos usuarios usan SAVI y sus métricas. |
| RM-13 | De los clientes **no se guardan ni ven datos**: privacidad por diseño. |
| RM-14 | Para la organización interna se identifica a **cada empleado** (no solo un seudónimo). |

## 3. Análisis de brecha contra el plan vigente

| ID | Qué lo cubre hoy | Brecha | Veredicto |
|---|---|---|---|
| RM-01 | Cloud ya tiene `docker-compose` con Caddy (E2). Fase 1 asumía **Windows Server + WinSW**. | No hay imagen de SAVI (backend + frontend) ni compose. Falta validar el CLI de Claude en Linux. | **Nuevo** |
| RM-02 | Nada. El PRD §3 lo declara **no objetivo** ("solo red interna"). | Endurecimiento de la Fase 1 §6 pasa de "recomendado" a **obligatorio**. | **En conflicto** (se corrige §4) |
| RM-03 | La administración de SAVI ya configura bases (existe). | Solo hay que desplegarlo. | **Cubierto** |
| RM-04 | E2–E4: vinculación con token, heartbeat, instancias en la consola, instalador con página de Cloud (E3c). | Hoy el token es opcional y no hay organización interna. Hay que precargar la URL y hacer la vinculación obligatoria en el build interno. | **Parcial** |
| RM-05 | Fase 5: `ai.allowed` por **cliente**. | No existe por instancia ni por persona. | **Parcial** |
| RM-06 | Fase 5: el gateway guarda las claves de SEO y no las reparte. | Falta la política `allow_own_key` y un **registro de claves por ámbito** (general / exclusiva). | **Parcial** |
| RM-07 | Fase 5: cuenta y ledger **por cliente**. | Faltan bolsas por proveedor y topes **por persona**. | **Nuevo** |
| RM-08 | Nada. | Asignación de bases y conocimiento por persona/equipo, y qué viaja al equipo gestionado. | **Nuevo** |
| RM-09 | Existe la distinción admin / no admin (`SAVI_ADMIN_LOGINS`). | Falta una política central que **bloquee** la configuración local de un equipo gestionado. | **Parcial** |
| RM-10 | Fase 5: modo `managed` por cliente, créditos, estado de cuenta. | Clave exclusiva por cliente (ver RM-06). | **Parcial** |
| RM-11 | Modo `own_key` (ya existe). | — | **Cubierto** |
| RM-12 | E3/E4: métricas, usuarios activos, consola. | — | **Cubierto** |
| RM-13 | E3: sin contenido, lista blanca por esquema y test. | — | **Cubierto** |
| RM-14 | E3 usa seudónimos (HMAC). P2 sin resolver. | Opt-in de nombres para la organización interna. | **Parcial** |

**Resumen:** 4 cubiertos, 6 parciales, 3 nuevos y 1 en conflicto. No se
sale del plan: **la base (E1–E4) sirve tal cual**. Cambia el orden y se
agregan piezas.

## 4. Correcciones al PRD

1. **PRD §3, "Acceso desde internet": deja de ser no objetivo** para el
   SAVI Master de SEO. Sigue siéndolo para los **SAVI de clientes**, que
   no se publican. La decisión del §15 (híbrido vs. SaaS puro) queda
   resuelta así: *híbrido para clientes y "SaaS interno" para SEO*, que
   corre en su propia nube sobre sus propias bases.
2. **El orden de la Fase 1 cambia:** el plan asumía Windows Server como
   primer destino. El primer destino es **Linux con Docker**. El servicio
   de Windows (WinSW) y los modos del instalador quedan para cuando haya
   un cliente que lo pida.
3. **Las claves de IA no se reparten a los equipos.** Cualquier clave que
   viaje a un portátil se puede extraer. El Master las guarda y las usa a
   través de un **gateway** (Fase 5), que además es lo único que permite
   medir y **cortar** el consumo de verdad.

## 5. Decisiones de diseño

| # | Decisión | Por qué |
|---|---|---|
| M1 | **Un Master, dos aplicaciones:** SAVI (chat y administración) y Cloud (consola, flota, gateway), en el mismo servidor y el mismo `compose`, con dos nombres de dominio. | Es lo más simple de operar para la primera etapa y respeta la separación de responsabilidades. |
| M2 | **La organización de SEO es un cliente más** (`internal = true`) en Cloud. | Se reutiliza todo (instancias, métricas, créditos) sin un camino paralelo. Cambia solo la política de identidad. |
| M3 | **La política baja por el heartbeat**, como ya está diseñado (S7: Cloud nunca llama a la instancia). | Un solo canal. Cambios de proveedor, presupuesto y permisos aplican en minutos. |
| M4 | **Gateway desde el inicio**, no "medir y avisar". | Sin gateway el presupuesto es una sugerencia. Con USD 50 de bolsa hay que poder cortar. |
| M5 | **La unidad del presupuesto es USD**, no un "crédito" abstracto. | Coincide con lo que factura el proveedor y con la forma en que se habló ("USD 50 en Gemini"). La abstracción (P5) se agrega después, solo en presentación. |
| M6 | **Presupuesto con tres niveles:** bolsa del proveedor ≥ tope de la organización ≥ tope por persona. | Responde al ejemplo de USD 50 con USD 5 por usuario. El más restrictivo gana. |
| M7 | **Recursos compartidos (bases, conocimiento) viven en el Master** y se usan desde la web. Un equipo gestionado no recibe credenciales del ERP. | Evita repartir contraseñas de bases de datos a portátiles. Ver §6 M4 para la alternativa. |
| M8 | **Identidad con nombre solo en la organización interna.** | Es lo que permite ver "los 5 empleados". Para clientes sigue el seudónimo (RM-13). |

## 6. Plan ajustado: etapa "SAVI Master"

Cada hito se entrega, verifica y commitea por separado, como el resto.

| Hito | Contenido | Reutiliza | Tamaño |
|---|---|---|---|
| **M1 — SAVI en Linux/Docker, en internet** | Imagen de SAVI (backend + frontend). `compose` con Postgres, SAVI, Cloud y Caddy (HTTPS automático, dos dominios). Variables y respaldo. **Endurecimiento obligatorio**: límite de intentos, OpenAPI oculto, headers, CORS cerrado, TOTP para administradores. Verificar el CLI de Claude en Linux. | Fase 1 §6 y §2.1; `deploy/master` | M |
| **M2 — Flota** | Organización interna. Instalador con URL del Master fija y vinculación obligatoria en el build interno. Inventario de equipos (nombre, usuario, versión, última vez visto). Identidad con nombre. Política de **solo chat** en equipos gestionados. | E2–E4, E3c | M |
| **M3 — IA gobernada** | **Spike del gateway (obligatorio primero).** Registro de claves por ámbito, proveedores permitidos por persona y equipo, `allow_own_key`, bolsas y topes por persona, bloqueo antes del chat y mensajes legibles. | Fase 5 (se amplía) | **L** |
| **M4 — Recursos compartidos** | Asignación de bases del ERP y de conocimiento por persona o grupo; qué se usa desde el Master y qué queda en el equipo. | — | M |
| **M5 — Clientes** | Alta de clientes con suscripción, créditos y clave exclusiva o general; modo clave propia. | Fase 5, E4 | M |

El resto del plan original (servicio de Windows, modos del instalador,
pestaña del ERP E6) **se difiere** hasta que haya un cliente real.

### Avance de M1

| Paso | Estado |
|---|---|
| M1.1 Imagen de SAVI (`backend/Dockerfile`: frontend + backend + modelo, usuario sin privilegios) | Hecho; sin construir (sin Docker en el equipo de desarrollo) |
| M1.2 Stack `deploy/master` con la guía de despliegue: compose, `.env`, secretos por archivo, Caddy con Let's Encrypt, `setup.sh`, `backup.sh`, `rollback.sh`, documentación de traspaso | Hecho; verificado de forma estática y por comportamiento (56 comprobaciones) |
| M1.3 OpenAPI oculto en producción | Hecho |
| M1.4 Doble factor (TOTP) para administradores de SAVI: QR y clave manual, configuración obligatoria en el primer ingreso, restablecimiento desde Administración → Seguridad y por línea de comandos | Hecho; recorrido real en navegador (12/12) |
| M1.5 Validar en un servidor Linux real: build de las imágenes, certificados, CLI de Claude y primer chat | Pendiente: requiere el servidor y el dominio (D4) |

> **Hallazgo:** el endurecimiento de red que la Fase 1 daba por inexistente (límite de intentos
> de login por usuario y por IP, bloqueo por fallos, cabeceras de seguridad con CSP, techo global
> por IP, `TRUST_PROXY_HEADERS`) **ya está implementado** en SAVI. M1 solo agrega lo que
> faltaba: ocultar OpenAPI y el segundo factor.

### Orden recomendado y por qué

1. **M1 primero**, porque sin servidor no hay nada que probar con
   personas reales y es lo que el equipo pidió ("probar todo").
2. **M2 enseguida**: es lo que da la visión de flota con casi todo ya
   construido.
3. **M3 es el hito riesgoso y el más valioso.** Se empieza por el
   **spike**: si el CLI de Claude no acepta una URL base propia, hay que
   decidir una alternativa antes de comprometer el diseño (Fase 5 §2).
4. **M4 y M5** dependen de las decisiones de §7.

## 7. Decisiones que necesito de ustedes

| # | Pregunta | Recomendación | Bloquea |
|---|---|---|---|
| D1 | ¿Qué corre en el equipo de cada empleado? **(a)** solo un acceso al Master en el navegador, **(b)** un SAVI local gestionado, **(c)** mixto. | **(c)**: web para gerentes, coordinadores y servicio al cliente; local gestionado solo para soporte que necesita llegar a bases de clientes por VPN. | M2, M4 |
| D2 | ¿El presupuesto se define en **USD** o en créditos abstractos? | USD (M5). | M3 |
| D3 | ¿Se aceptan **nombres reales** de los empleados en la consola? (P2) | Sí, solo en la organización interna. | M2 |
| D4 | Servidor Linux y **dominio** (P3), con salida a internet y puertos 80/443. | Un solo servidor con Docker, dos subdominios. | Despliegue de M1 |
| D5 | ¿Se exige **doble factor** a los administradores del Master expuesto a internet? | Sí, desde el inicio. | M1 |
| D6 | ¿Cuándo un empleado puede usar **clave propia**? ¿Por usuario, por grupo o nunca? | Por usuario, desactivado por defecto. | M3 |

## 8. Riesgos

| # | Riesgo | Mitigación |
|---|---|---|
| RK1 | El CLI de Claude no funciona con una URL base propia o en Linux. | Spike antes de diseñar M3; alternativa documentada en Fase 5 §2. |
| RK2 | Un SAVI con credenciales de ERP expuesto a internet es un blanco. | Endurecimiento obligatorio en M1, TOTP, límite de intentos, firewall, respaldos cifrados. Revisión de seguridad antes de abrir. |
| RK3 | El Master es punto único de falla para la IA gestionada. | Aceptado en la primera etapa. Un equipo con clave propia habilitada sigue funcionando. |
| RK4 | La identidad por persona que declara el equipo se puede falsificar. | Aceptable entre empleados. Para control estricto, tokens por persona emitidos por el Master tras iniciar sesión. |
| RK5 | Presupuesto cortado a mitad de una respuesta. | El gateway cobra lo que el proveedor informa; mensaje legible; tope blando antes del corte (alerta al 80 %). |
| RK6 | Modelos sin precio vigente. | Regla G7 de Fase 5: sin precio no hay servicio. |

## 9. Criterios de cierre de la primera etapa

- El Master responde por HTTPS en un dominio de SEO y un empleado
  entra, configura una base y chatea.
- La consola muestra **todos** los equipos instalados con su persona,
  versión y última conexión.
- Un equipo con proveedor restringido **no puede** elegir otro, ni
  configurar claves si no se le habilitó.
- Con una bolsa de USD 50 y un tope de USD 5 por persona, la persona
  queda **cortada** al llegar a USD 5 y el resto sigue.
- Ninguna clave de IA ni contraseña de ERP aparece en un equipo gestionado
  (test que recorre su disco y su configuración).
