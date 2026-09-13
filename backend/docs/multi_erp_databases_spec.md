# Multi-BD del ERP — Especificación

> Estado: **en implementación** — backend completo (Fases 1-5, 8); resta frontend (6-7)
> Alcance: backend (`app/`), frontend (`frontend/src/`), instalador (`installer/`)
> Fecha: 2026-09-09
>
> Decisiones cerradas: D1–D10 (§4), autenticación (§5).
> Quedan dos puntos abiertos que no bloquean el arranque: §13.4 (tamaño
> de los pools) y §13.6 (limpieza de `ERP_DB_PASSWORD` del `.env`).

---

## 1. Problema

Un agente de soporte de SEO ERP atiende a varios clientes. Cada cliente
tiene su propia base de datos del ERP. Hoy SAVI está atado a **una sola**
BD del ERP, fijada en `.env` en tiempo de instalación
(`ERP_DB_HOST/PORT/USER/PASSWORD/NAME`, ver `app/infrastructure/config/settings.py`).

Para atender a otro cliente el agente tiene que volver al instalador y
reconfigurar la BD. Eso significa: reiniciar el servicio, perder el
contexto de trabajo y no poder alternar entre clientes durante la misma
jornada. Es el cuello de botella operativo del producto en soporte.

## 2. Objetivo

Permitir registrar **N bases de datos de clientes del ERP** y elegir
cuál usa cada conversación de SAVI, sin reinstalar ni reiniciar.

### Fuera de alcance

- Motores distintos de PostgreSQL.
- Consultas que cruzan datos de dos clientes en un mismo turno.
- Migración de conversaciones existentes de una BD a otra.
- Rotación automática de la clave de cifrado.

---

## 3. Estado actual: dónde está el acoplamiento

Esta es la lista completa de puntos que asumen "una sola BD del ERP".
Cualquier solución tiene que atravesarlos todos.

### 3.1 El engine es un singleton global de proceso

`app/infrastructure/database/pool.py` guarda `_erp_engine` en una
variable de módulo, lo crea en `init_engines()` durante el `lifespan` y
lo expone por `get_erp_engine()`. Los consumidores lo llaman **directo**,
sin inyección:

| Consumidor | Archivo |
|---|---|
| `ErpUserRepository` | `auth/infrastructure/http/dependencies.py:64` |
| `ErpPermissionRepository` | `auth/infrastructure/http/dependencies.py:105` |
| `ErpSeoPlanRepository` | `auth/infrastructure/http/dependencies.py:113` |
| `info_empresa` (tool MCP) | `chat/.../mcp/tools/info_empresa.py:35` |
| `consultar_libre` (tool MCP) | `chat/.../mcp/tools/consultar_libre.py:63` |
| `execute_compiled` (data_query) | `data_query/infrastructure/erp_query_executor.py:29` |
| `get_erp_session` | `app/infrastructure/database/session.py:38` |
| `_collect_report` (diagnóstico) | `app/launcher.py:689` ← **encontrado en la Fase 1** |

> El octavo apareció recién al implementar: el reporte de diagnóstico
> del launcher abre el ERP antes de que exista el registry. Se resolvió
> armando un engine descartable desde el `.env`, y con el `.env` vacío
> el chequeo simplemente no corre en vez de fallar.

### 3.2 La identidad del usuario NO es única entre bases

Este es el hallazgo crítico del análisis.

`AuthenticatedUser.id` es el `"idUsuario"` de `Seguridad.Usuario`, un
`integer` propio de **cada** BD del ERP
(`auth/infrastructure/persistence/erp_user_repository.py`). Ese entero se
propaga sin calificar a:

- El claim `sub` del JWT (`auth/domain/value_objects/token_claims.py`).
- `conversations.user_id` (`Integer`, indexado) — filtra el listado y la
  verificación de propiedad del chat.
- `refresh_tokens.user_id`.
- Todos los agregados del módulo `usage` (ranking por usuario, KPIs).
- El `version_hash` de `ResolveUserModulesUseCase`.

**Con varias bases, `idUsuario = 5` en el cliente A y `idUsuario = 5` en
el cliente B son personas distintas y el código actual las trata como la
misma.** Concretamente: el usuario 5 del cliente B vería en su barra
lateral las conversaciones del usuario 5 del cliente A, y su consumo se
sumaría al de esa otra persona.

No es un riesgo teórico: es la consecuencia directa de agregar una
segunda base sin tocar la identidad. **La identidad tiene que pasar a ser
el par `(erp_database_id, user_id)`.**

### 3.3 Los permisos también se resuelven contra el ERP

`ResolveUserModulesUseCase` cruza `Seguridad.PermisoFormulario`,
`Seguridad.Formulario` y `SEO.Modulo` (el plan contratado). Las tres
tablas viven en la BD del cliente. Cada base tiene su propio set de
permisos y su propio plan contratado, así que **los módulos habilitados
cambian según la base**, no solo según el usuario.

Ese set alimenta el filtro de las tools de conocimiento
(`chat/infrastructure/http/routes.py:62-63`), así que la respuesta del
agente depende de qué base se resolvió.

### 3.4 El instalador es hoy la única fuente de configuración

`installer/env.template` escribe el bloque `ERP_DB_*` en `backend/.env`.
`Settings.erp_db_url` lo compone y `init_engines()` lo consume. No hay
persistencia de configuración de conexiones: el `.env` **es** la
configuración.

---

## 4. Decisiones de diseño

### D1 — Registro de bases en la BD del agente, no en `.env`

Nueva tabla `erp_databases` en `agent_db` (la que ya usa
`conversations`/`messages`, SQLite en escritorio o Postgres en servidor).

El `.env` deja de ser la fuente de verdad en runtime y queda solo como
**semilla de arranque** (ver D7).

**Por qué:** las bases se administran desde la UI, en caliente. Escribir
`.env` desde la aplicación exigiría reiniciar el proceso para que
`Settings` (cacheado con `@lru_cache`) lo relea, lo que anula el objetivo
del requerimiento.

### D2 — La conversación queda atada a una base, de forma inmutable

`conversations.erp_database_id` se fija al crear la conversación y **no
se puede cambiar**. Cambiar de cliente = conversación nueva.

**Por qué:** el historial de una conversación es el contexto que se le
manda al LLM en cada turno. Si a mitad del hilo cambia la base, los
turnos anteriores describen los datos de otro cliente y el modelo
razona sobre una mezcla incoherente — y peor, puede repetir al aire
datos del cliente A dentro de una sesión del cliente B. Es una fuga de
datos entre clientes, no solo un problema de calidad.

Esto responde la duda del requerimiento ("las conversaciones tengan
referencia o si no los mensajes"): **a nivel conversación**. Ponerlo en
`messages` solo tiene sentido si se permite cambiar de base a mitad del
hilo, que es justamente lo que estamos prohibiendo. La columna en
`conversations` es la referencia de auditoría suficiente.

`audit_query.erp_database_id` **sí** se agrega, porque esa tabla audita
SQL ejecutado y necesita decir contra qué base se ejecutó.

### D3 — Los permisos se resuelven SIEMPRE en la base que se va a consultar

Regla única, sin excepciones: para un turno contra la base B, los
módulos del usuario se resuelven leyendo `Seguridad.PermisoFormulario` y
`SEO.Modulo` **de B**, haciendo match del usuario por `codigo` (el login,
que sí es estable entre bases porque el esquema es el mismo).

Si el `codigo` del usuario autenticado no existe en B, o existe pero está
inactivo: **no tiene acceso a esa base**. No se hereda el `is_admin` ni
los módulos de la base de identidad.

**Por qué:** los permisos son una propiedad de la relación
usuario–cliente, no del usuario. Heredarlos desde la base default le
daría a un admin de la base default acceso total a los datos de todos los
clientes, que es exactamente lo que el modelo de permisos del ERP existe
para evitar.

### D4 — Cifrado de la columna de contraseña

La contraseña de conexión al ERP tiene que ser **reversible**: SAVI la
necesita en claro, en memoria, para armar la URL de conexión. Así que
esto es **cifrado simétrico**, no hashing. Un `bcrypt` o un `argon2`
—lo correcto para contraseñas de usuario— acá no sirve: no se puede
deshacer.

#### Algoritmo

`cryptography.fernet.Fernet`: AES-128-CBC para confidencialidad +
HMAC-SHA256 para integridad, con IV aleatorio y timestamp, todo empacado
en un token base64 urlsafe que entra tal cual en una columna `Text`.

Se elige Fernet y no AES a mano por una razón concreta: **autentica**.
Un AES-CBC sin HMAC deja modificar el ciphertext sin que se note. Y
sobre todo, no hay que escribir criptografía propia — el modo, el
padding y el IV ya vienen resueltos y probados.

`cryptography` ya es una dependencia transitiva del proyecto (la usa
`PyJWT` para firmar), así que no entra una dependencia nueva pesada.

#### La clave

Variable nueva `ERP_CREDENTIALS_KEY`: 32 bytes al azar en base64
urlsafe, generada **por instalación** por el instalador, igual que ya
hace con `JWT_SECRET`.

```python
Fernet.generate_key()   # -> b'kZ3v...=' (44 chars base64)
```

**No se reutiliza `JWT_SECRET`.** Son secretos con ciclos de vida
distintos: rotar el de JWT solo invalida sesiones (molesto pero
inofensivo), rotar el de credenciales deja ilegibles todas las
contraseñas guardadas. Mezclarlos convierte una operación rutinaria en
una pérdida de datos.

#### Puerto de dominio, no llamada directa

```
domain/interfaces/credential_cipher.py     → CredentialCipher (ABC)
    encrypt(plaintext: str) -> str
    decrypt(ciphertext: str) -> str

infrastructure/security/fernet_credential_cipher.py   → impl Fernet
```

Sigue el mismo patrón que `PasswordHasher` / `Md5PasswordHasher` del
módulo `auth`. Permite testear los casos de uso con un cipher falso y
cambiar mañana a DPAPI de Windows o a un gestor de secretos sin tocar
`application/`.

#### Rotación de clave

`MultiFernet` acepta una lista de claves: cifra siempre con la primera y
descifra probando todas. Con una variable opcional
`ERP_CREDENTIALS_KEY_OLD` se puede rotar sin downtime:

1. Se agrega la clave nueva como `ERP_CREDENTIALS_KEY` y la vieja pasa a
   `ERP_CREDENTIALS_KEY_OLD`.
2. Un comando de mantenimiento re-cifra las filas existentes.
3. Se borra `ERP_CREDENTIALS_KEY_OLD`.

No es Fase 1, pero el puerto tiene que dejarlo posible desde el diseño —
agregarlo después obligaría a migrar datos.

#### Qué pasa si la clave se pierde o cambia

Escenario real: alguien reinstala, restaura un backup del `.env` viejo o
edita `ERP_CREDENTIALS_KEY` a mano. Todas las contraseñas guardadas
quedan indescifrables.

**Regla: eso no puede tumbar la aplicación.** El `decrypt` que falla con
`InvalidToken` se traduce a un estado visible de la base —
`credentials_unreadable`— y la UI la muestra como "credenciales
ilegibles, volvé a ingresar la contraseña". La base no se puede usar
hasta que se re-ingrese, pero el resto de SAVI arranca y funciona.

Sin esta regla, un `.env` restaurado del backup equivocado deja la
aplicación sin arrancar y con un stacktrace de criptografía que nadie en
soporte va a saber leer.

#### Reglas de manejo del dato

- La contraseña **nunca** sale del backend: ningún response la incluye,
  ni en claro ni cifrada. Los DTOs de respuesta no tienen el campo.
- El formulario de edición la deja **vacía**; solo se reemplaza si el
  usuario escribe una nueva. Vacío = conservar la actual.
- Nunca se loguea, ni cifrada. Cuidado especial con `app_debug=true`:
  `echo` de SQLAlchemy imprime los parámetros de las sentencias. El
  engine del ERP ya se crea con `echo=False` fijo y hay que mantener ese
  criterio para los engines del registry.
- La URL de conexión se arma en memoria y no se persiste ni se expone en
  ningún endpoint de diagnóstico.
- Un test verifica que ningún response del CRUD contenga el valor, ni el
  claro ni el cifrado.

#### Limitación, dicha en voz alta

Esto es cifrado **en reposo**, no secreto. La clave vive en
`backend/.env`, en el mismo equipo que la base de datos. Quien tenga
acceso al filesystem del equipo puede descifrar.

Lo que **sí** protege:

- Una copia del archivo `savi.db` que se filtre sola (backup, adjunto,
  disco reciclado).
- Una lectura accidental de la tabla — soporte, un dump, un log.
- Que la contraseña aparezca en claro en una respuesta del API.

Lo que **no** protege: un atacante con acceso al equipo. Si eso hace
falta, el camino es DPAPI de Windows (cifra con la credencial del
usuario del sistema) o un gestor de secretos externo. El puerto
`CredentialCipher` deja esa puerta abierta; hoy sería sobredimensionado
para una instalación de escritorio.

### D5 — Test de conexión obligatorio antes de guardar, y disponible solo

Dos usos del mismo caso de uso:

- `POST /admin/erp-databases/test-connection` — con credenciales en el
  body, sin persistir nada. Es el botón "probar conexión" del formulario.
- Invocado internamente por `create` y `update`: si el test falla, la
  operación devuelve `422` y no persiste.

El test no es solo `SELECT 1`. Verifica que la base **sea un ERP de SEO**:

1. Conecta con `default_transaction_read_only=on` y un
   `statement_timeout` corto (5 s).
2. `SELECT 1`.
3. Comprueba que existan `Seguridad.Usuario`, `Seguridad.Formulario`,
   `Seguridad.PermisoFormulario`, `SEO.Modulo` y `Empresa.Empresa`.
4. Lee `Empresa.Empresa."razonSocial"` y la devuelve, para que la UI
   pueda proponerla como nombre y el usuario confirme que apuntó al
   cliente correcto. El nombre propuesto es **editable**: los agentes de
   soporte suelen usar nombres internos más cortos que la razón social
   legal.

**Por qué el paso 3:** sin él se puede registrar cualquier Postgres, y el
error aparecería recién en mitad de un chat, con un mensaje ilegible para
un agente de soporte.

### D6 — Baja lógica y desactivación son cosas distintas

| Estado | Campo | Efecto |
|---|---|---|
| Activa | `is_active=true`, `deleted_at IS NULL` | Uso normal |
| Desactivada | `is_active=false` | No se puede iniciar conversación nueva ni enviar turnos. Historial legible. Reversible desde la UI. |
| Eliminada | `deleted_at=now()` | Igual que desactivada + oculta del listado y del selector. Irreversible desde la UI. |

Nunca se hace `DELETE` físico: `conversations.erp_database_id` es una FK
y el historial tiene que seguir siendo legible y auditable.

La base marcada como default **no se puede eliminar ni desactivar** sin
antes designar otra como default.

### D7 — El instalador sigue configurando una base, que se siembra como default

`installer/env.template` no cambia su bloque `ERP_DB_*`. Al arrancar,
después de `ensure_schema()`, un paso de seed idempotente:

```
si la tabla erp_databases está vacía y ERP_DB_HOST tiene valor:
    insertar esa conexión como is_default=true, is_active=true
    nombre = razonSocial leída del ERP, o "<ERP_DB_NAME>" como fallback
```

Idempotente por "tabla vacía", no por `(host, port, name)`: si el
administrador borró esa fila a propósito, el arranque no debe
resucitarla.

Tras el seed, `Settings.erp_db_url` y `get_erp_engine()` **dejan de
usarse** en el camino de runtime. Se conservan solo para el seed y para
que un `.env` viejo siga arrancando.

### D8 — Registry de engines con creación diferida y evicción

Nuevo `ErpEngineRegistry`: mapa `erp_database_id → AsyncEngine`.

- Creación diferida: el engine de una base se crea en su primer uso, no
  al arrancar. Con 30 clientes registrados, arrancar 30 pools de 5
  conexiones (150 conexiones) sería absurdo.
- `pool_size=3, max_overflow=2` por base (hoy es 5+2 para una sola).
- `pool_recycle` y disposición de engines sin uso por más de N minutos.
- Tope configurable de engines vivos simultáneos, con evicción LRU.
- **Invalidación explícita**: editar o desactivar una base dispone su
  engine de inmediato. Sin esto, cambiar una contraseña no tendría
  efecto hasta reiniciar.
- Mantiene los `server_settings` actuales: `default_transaction_read_only=on`
  y `statement_timeout`. La BD del ERP sigue siendo solo lectura, siempre.

Vive en `app/modules/erp_databases/infrastructure/engine_registry.py` con
un provider de proceso, siguiendo el patrón ya establecido por
`knowledge/infrastructure/catalog_provider.py`.

### D9 — Quién administra las bases

Gate: `is_admin` **de la base de identidad** — la misma que ya usa
`AdminUserDep` para `/usage/system` y `/usage/kpis`. No se inventa un
modelo de permisos paralelo.

**Escape hatch necesario:** un agente de soporte puede no ser
`administrador` en ninguna base del ERP y aun así ser el dueño de su
propia instalación de escritorio. Exigirle un flag del ERP lo dejaría
afuera de su propia herramienta.

Variable nueva `SAVI_ADMIN_LOGINS`: lista separada por comas de `codigo`s
que reciben rol de administrador de SAVI aunque el ERP no los marque
como tales. Vacía por default. El instalador puede sembrarla con el
usuario de quien instala.

Alcance limitado a propósito: **solo habilita la sección de
administración de SAVI.** No toca `ResolveUserModulesUseCase`, no otorga
módulos del ERP y no altera qué datos puede consultar. Administrar
conexiones y tener acceso a datos son dos cosas distintas, y esta
variable solo concede la primera.

Vive en `.env` y por lo tanto cambiarla exige reiniciar. Es aceptable:
es una lista que se toca una vez por instalación.

### D10 — Conversaciones de clientes distintos, en simultáneo

Un usuario puede tener conversaciones abiertas de varios clientes al
mismo tiempo. No hay noción de "cliente activo" de sesión.

**Por qué:** el caso de uso real es un agente de soporte que atiende
llamadas de clientes distintos en la misma jornada, a veces alternando
entre dos en minutos. Un "cliente activo" global lo obligaría a cambiar
de modo cada vez y volvería a introducir el problema que el
requerimiento quiere eliminar, solo que más barato.

La consecuencia es que la base **tiene** que estar visible en cada
conversación de la barra lateral (§8.3). Con los títulos autogenerados de
SAVI, dos conversaciones de clientes distintos pueden llamarse casi
igual, y confundirlas es exactamente el error que hay que evitar.

---

## 5. Autenticación: login calificado

### 5.1 El login solo decide identidad, no acceso

Aclaración que ordena todo lo demás: **elegir en qué base autenticar no
determina a qué clientes se puede consultar.**

Por D3, los permisos se resuelven siempre en la base que se va a
consultar, matcheando por `codigo`. Entonces el login decide una sola
cosa: la identidad del usuario — qué `idUsuario`, de qué base — para
colgar sus conversaciones, sus refresh tokens y su consumo.

Un agente de soporte con usuario en los clientes A, B y C entra por
cualquiera de las tres y desde ahí ve las tres (D3 + `GET
/erp-databases/available`). El login solo necesita **dejarlo entrar**.

### 5.2 Decisión: identificador de cliente en el propio campo de login

`POST /auth/login` acepta un identificador de cliente opcional, embebido
en el campo de login con `@` como separador:

```
JPEREZ            → base default            (1 consulta)
JPEREZ@NORTE      → base con code "NORTE"   (1 consulta)
```

El backend hace `rsplit("@", 1)`, resuelve el `code` contra
`erp_databases` (activa y no eliminada), y ejecuta el mismo
`find_by_login` de siempre contra el engine de esa base.

Se usa `rsplit` y no `split`: si el `codigo` del ERP llegara a contener
un `@`, el separador válido es el último.

Propiedades:

- **Determinista**: una base, una consulta, una identidad. Siempre.
- **Sin listado público**: no existe ningún endpoint sin autenticar que
  enumere las bases. Hay que conocer el `code`.
- **Sin amplificación ni oráculo de tiempo**: nunca se recorre más de una
  base por intento.
- **Compatible hacia atrás**: sin `@` se comporta exactamente como hoy.
- Cubre el caso que motiva el requerimiento: el agente cuyo usuario solo
  existe en el cliente B entra con `JPEREZ@B`.

Es el patrón de `DOMINIO\usuario` de Windows, de `usuario@tenant` en
Odoo y del login de SQL Server.

### 5.3 Regla que impide enumerar clientes

Un `code` de cliente **inexistente, inactivo o eliminado** devuelve el
**mismo** `InvalidCredentialsError` que una contraseña incorrecta:
idéntico status, idéntico `errorCode`, idéntico mensaje.

Esto extiende una regla que el `LoginUseCase` ya aplica y documenta: no
distinguir "el usuario no existe" de "la contraseña está mal", para no
filtrarle información al atacante. Acá vale igual para el cliente.

Consecuencia de implementación: hay que **igualar el tiempo** de todos
los caminos de fallo, no solo la respuesta.

> **Medido en la implementación (Fase 2).** El primer intento fue
> verificar contra un hash dummy cuando el `code` no resuelve. **No
> alcanza.** Contra el ERP real: cliente inexistente 3,4 ms, contraseña
> incorrecta 14,0 ms — una diferencia de 4×, perfectamente medible. El
> motivo es que MD5 es prácticamente gratis y el costo que domina es el
> viaje a la BD del ERP, que el camino "el cliente no existe" nunca
> hace. Igualar el hash iguala lo barato y deja pasar lo caro.
>
> La mitigación que sí funciona es un **piso de duración constante**
> sobre todo el camino de fallo (`_MIN_FAILED_LOGIN_SECONDS = 0.25`).
> Medido después del cambio: 242 / 254 / 250 ms para cliente
> inexistente, cliente correcto y login sin `@`. La diferencia restante
> es granularidad del timer.
>
> El `sleep` tiene que ser `asyncio.sleep` y no `time.sleep`: bloquear
> el event loop convertiría la mitigación en una denegación de servicio
> con un puñado de logins fallidos concurrentes.
>
> El camino `UserDisabledError` **no** pasa por el piso: para llegar ahí
> hay que haber acertado la contraseña, así que no revela nada nuevo.

### 5.4 Cómo se recuerda el `code` (frontend)

El agente necesita conocer el `code` la primera vez — es un dato que le
da un administrador, igual que su usuario.

A partir de ahí, `LoginView.vue` guarda en `localStorage` los `code` que
**ese usuario en ese equipo** ya usó con éxito, y los ofrece como
`<datalist>` de autocompletado.

No es una lista pública: es historial local del navegador, del mismo
tipo que el que ya recuerda el nombre de usuario. Nunca sale del equipo
ni se consulta al backend.

### 5.5 Rechazado: búsqueda en cascada

La propuesta original era buscar en la default y, si no está, recorrer
las demás. Se descarta por:

1. **Identidad no determinista.** Códigos como `ADMIN`, `SOPORTE` o
   `JPEREZ` se repiten entre clientes. Si existe en A y en B, quién gana
   depende del orden de recorrido, y ese orden cambia al agregar bases o
   al cambiar la default.
2. **Amplificación de intentos de credenciales.** Un `POST /auth/login`
   se convierte en N verificaciones contra N bases de producción de
   clientes. Con 30 clientes, la fuerza bruta rinde 30× por petición.
3. **Fuga por tiempo de respuesta.** Un login que falla en todas tarda N
   veces más que uno que acierta primero. Oráculo medible.

Se puede endurecer (orden fijo, rate limit, piso de duración constante),
pero ninguna mitigación elimina que cada intento de login golpee N bases
de producción de clientes. El login calificado no paga ese precio y no
pierde ninguna capacidad.

### 5.6 Rechazado: selector de bases en la pantalla de login

Determinista y sin fricción, pero exige un endpoint **sin autenticar**
que liste las bases activas. Eso expone los nombres de los clientes de
SEO a cualquiera que llegue al login.

En escritorio, con `APP_HOST=127.0.0.1`, el riesgo es casi nulo. En un
despliegue servidor — que el código ya soporta
(`agent_db_engine=postgresql` + CORS) — es una fuga real. El login
calificado sirve a los dos escenarios con un solo diseño.

### 5.7 Impacto en el JWT

Independiente de lo anterior, la identidad queda calificada (§3.2):

```json
{
  "sub": "<erp_database_id>:<idUsuario>",
  "erp_db": "<erp_database_id>",
  "login": "JPEREZ",
  "purpose": "access"
}
```

`sub` sigue siendo un string, como exige el estándar JWT y como ya lo
trata `TokenClaims`. Se agrega `erp_db` como claim propio para no tener
que parsear `sub` en cada uso.

**Los tokens emitidos antes de este cambio dejan de ser válidos.** Un
`sub` sin `:` no se puede atribuir a ninguna base con certeza y hay que
rechazarlo — adivinar que era la default es exactamente el bug de §3.2.
El efecto para el usuario es tener que volver a iniciar sesión una vez,
que es lo mismo que ya provoca hoy un cambio de `JWT_SECRET`.

---

## 6. Modelo de datos

### 6.1 Tabla nueva `erp_databases` (en `agent_db`)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | |
| `code` | `String(32)` NOT NULL | Identificador corto del cliente. **Es el que se escribe después del `@` en el login** (§5.2). Mayúsculas, sin espacios ni `@`. Único entre no eliminadas. |
| `name` | `String(120)` NOT NULL | Nombre visible del cliente. Único entre no eliminadas. |
| `host` | `String(255)` NOT NULL | |
| `port` | `Integer` NOT NULL default 5432 | |
| `database` | `String(120)` NOT NULL | |
| `username` | `String(120)` NOT NULL | |
| `password_encrypted` | `Text` NOT NULL | Token Fernet (D4). Nunca sale del backend. |
| `statement_timeout_ms` | `Integer` NOT NULL default 60000 | |
| `is_default` | `Boolean` NOT NULL default false | Una sola, entre las no eliminadas. |
| `is_active` | `Boolean` NOT NULL default true | |
| `deleted_at` | `UtcDateTime` NULL | Baja lógica. |
| `credentials_unreadable` | `Boolean` NOT NULL default false | Se marca cuando el `decrypt` falla (D4). La base no se usa hasta re-ingresar la contraseña. |
| `last_connection_ok_at` | `UtcDateTime` NULL | Último test exitoso. |
| `created_at` / `updated_at` | `UtcDateTime` NOT NULL | |

Sobre `code`: se valida con `^[A-Z0-9_-]{2,32}$`. Ese charset excluye el
`@` por construcción, así que el `rsplit("@", 1)` del login no puede
volverse ambiguo. Se normaliza a mayúsculas al guardar y al comparar,
igual que ya hace `LoginUseCase` con el `codigo` del ERP.

Índices:

- `(deleted_at, is_active)` para el selector.
- Único parcial sobre `code WHERE deleted_at IS NULL` — es la clave de
  búsqueda del login.
- Único parcial sobre `is_default WHERE deleted_at IS NULL` — una sola
  default.

> **Los tres índices son parciales (`WHERE`).** SQLite los soporta, pero
> hay que verificarlos en los dos caminos de creación de esquema (§6.3).
> Si alguno no se creara, el síntoma no sería un error: sería un `code`
> duplicado que rompe el login de forma silenciosa.

> Nota SQLite: los índices únicos parciales funcionan, pero
> `bootstrap.py` crea el esquema desde el metadata en una BD nueva y
> `alembic upgrade` en las existentes. Hay que verificar el índice
> parcial en **los dos** caminos, y registrar el modelo nuevo en
> `_REGISTERED_MODELS` de `bootstrap.py` y en `alembic/env.py` — sin eso
> `create_all` no crea la tabla.

### 6.2 Columnas nuevas

| Tabla | Columna | Nulabilidad |
|---|---|---|
| `conversations` | `erp_database_id` UUID FK → `erp_databases.id` | NULL solo para filas legadas; NOT NULL para nuevas (a nivel aplicación) |
| `refresh_tokens` | `erp_database_id` UUID | NOT NULL. Los tokens previos se invalidan (§5.7) |
| `audit_query` | `erp_database_id` UUID | NULL para filas legadas |

### 6.3 Migración

Una revisión Alembic que:

1. Crea `erp_databases`.
2. Agrega las columnas de 6.2 como nullable.
3. **No** hace backfill en la migración. El backfill lo hace el seed de
   arranque (D7), que es el único que sabe cuál es la base default —
   sembrarla desde la migración obligaría a leer `.env` desde Alembic.
4. Un paso de seed posterior asigna la default a las conversaciones
   existentes con `erp_database_id IS NULL`.

`downgrade` tiene que ser real: SQLite no soporta `DROP COLUMN` en
versiones viejas, así que el batch mode de Alembic es obligatorio acá.

---

## 7. API

### 7.1 Módulo nuevo `erp_databases`

Triada completa, según `skills/enterprise-backend-fastapi`:

```
app/modules/erp_databases/
├── domain/
│   ├── entities/erp_database.py
│   ├── interfaces/erp_database_repository.py
│   ├── interfaces/credential_cipher.py
│   ├── interfaces/connection_tester.py
│   └── exceptions/
├── application/
│   ├── requests/, responses/, dtos/, mappers/
│   └── use_cases/  (list, create, update, deactivate, activate,
│                    soft_delete, set_default, test_connection)
└── infrastructure/
    ├── http/routes.py, dependencies.py
    ├── persistence/models/, repositories/
    ├── security/fernet_credential_cipher.py
    ├── postgres_connection_tester.py
    └── engine_registry.py
```

### 7.2 Endpoints

Prefijo `/admin/erp-databases`, todos con `AdminUserDep`:

| Método | Ruta | Notas |
|---|---|---|
| `GET` | `""` | Lista. Sin contraseñas. `?include_inactive=bool`. |
| `POST` | `""` | Crea. Test de conexión obligatorio antes de persistir. |
| `GET` | `/{id}` | Detalle. Sin contraseña. |
| `PATCH` | `/{id}` | Edita. Re-testea si cambió algún dato de conexión. |
| `POST` | `/{id}/activate` | |
| `POST` | `/{id}/deactivate` | `409` si es la default. |
| `POST` | `/{id}/set-default` | |
| `DELETE` | `/{id}` | Baja lógica idempotente. `409` si es la default. |
| `POST` | `/test-connection` | Sin persistir. Acepta `id` (re-test de una guardada) o credenciales completas. |

Endpoint para usuarios no admin:

| Método | Ruta | Notas |
|---|---|---|
| `GET` | `/erp-databases/available` | Bases activas donde el usuario autenticado **tiene acceso** (su `codigo` existe y está activo en esa base, D3). Solo `id` y `name`. Alimenta el selector del chat. |

Hay que agregar `"admin"` y `"erp-databases"` a `_API_PREFIXES` en
`app/main.py`, o la SPA se va a comer esos 404.

### 7.3 Cambios en endpoints existentes

- `POST /conversations` acepta `erp_database_id` (ausente = default del
  usuario). Valida que exista, esté activa y que el usuario tenga acceso.
- `GET /conversations` devuelve `erp_database_id` y `erp_database_name`
  por conversación, para que la barra lateral muestre el cliente.
- `POST /chat` valida en `use_case.validate()` que la base de la
  conversación siga activa. Si no: `409` con un `errorCode` nuevo
  (`erp_database_unavailable`) **antes** de abrir el `StreamingResponse`.
  Ese orden ya está resuelto y comentado en
  `chat/infrastructure/http/routes.py:49-52`; hay que respetarlo, porque
  dentro del SSE ya no se puede cambiar el status code.
- `GET /auth/me/bootstrap` devuelve la base de identidad del usuario y
  las disponibles.
- Los endpoints de `usage` que agregan por usuario tienen que scopear por
  `(erp_database_id, user_id)`.
- `POST /auth/login` **no cambia su contrato**: sigue recibiendo `login`
  y `password`. El identificador de cliente viaja dentro de `login`
  (§5.2), y el `rsplit("@", 1)` lo hace el caso de uso. No se agrega un
  campo nuevo al body, para que un cliente viejo siga funcionando sin
  cambios.
- `POST /auth/refresh` valida que el `erp_db` del refresh token siga
  activo. Si la base de identidad se desactivó, el refresh falla y el
  usuario tiene que volver a entrar — no se puede sostener una sesión
  contra una base que ya no se consulta.

### 7.4 Cambios en el flujo del turno

`LLMRunner.stream_turn` recibe `erp_database_id`.
`build_savi_mcp_server(conversation_id, allowed_modules, erp_database_id)`
lo clausura en las tools. Las cuatro tools resuelven su engine del
registry en lugar de llamar a `get_erp_engine()`.

**El número de tools MCP no cambia: siguen siendo 4.** Esto es
deliberado y no negociable — ver
[`mcp_deferred_tools_gotcha.md`](mcp_deferred_tools_gotcha.md). La
selección de base **no** puede ser una tool que el LLM invoque: es
contexto del turno, decidido por el usuario, resuelto antes de armar el
prompt. Si el modelo pudiera elegir la base, podría cruzar datos de dos
clientes en un turno.

El `SYSTEM_PROMPT` tiene que mencionar de qué cliente son los datos de
este turno, para que el agente no diga "tu empresa" refiriéndose al
cliente equivocado.

---

## 8. Frontend

### 8.1 Sección administrativa nueva

Rutas anidadas bajo `/admin`, con un layout propio y navegación lateral
distinta de la del chat:

```
/admin                      → redirect a /admin/bases-datos
/admin/bases-datos          → CRUD de bases (admin)
/admin/bases-datos/:id      → formulario de edición
/admin/consumo              → mueve la vista de /consumo (admin)
```

Guard: `meta.requiresAuth` + `meta.requiresAdmin` (nuevo — el guard de
`router/index.ts` hoy solo maneja `requireModule`, hay que agregar el
chequeo de `is_admin`).

**"Mi consumo" no se mueve a `/admin`.** El panel `MyUsagePanel.vue` es
para cualquier usuario; solo `SystemUsagePanel`, `KpisPanel` y
`TariffSimulator` son de admin. Mover todo dejaría a los usuarios no
admin sin ver su propio consumo. Propuesta: "mi consumo" pasa a
`/perfil` (que ya existe y ya es personal), y `/admin/consumo` queda con
lo global. `/consumo` se mantiene como redirect para no romper enlaces.

### 8.2 Módulo nuevo `frontend/src/modules/admin/`

Siguiendo `skills/enterprise-frontend-architecture`:

```
modules/admin/
├── components/  (ErpDatabaseTable, ErpDatabaseForm,
│                 TestConnectionButton, ConfirmDeactivateDialog)
├── services/erpDatabaseService.ts   (extiende HttpClient)
├── stores/erpDatabaseStore.ts
├── views/  (AdminLayout, ErpDatabasesView, AdminUsageView)
├── types.ts
└── index.ts                          (contrato público del módulo)
```

Formulario: nombre, host, puerto, base, usuario, contraseña, timeout.
El botón "Probar conexión" es independiente y también corre implícito
antes de guardar. Al probar con éxito muestra la razón social leída del
ERP y, si el campo nombre está vacío, la propone.

### 8.3 Pantalla de login

`LoginView.vue` mantiene los dos campos de siempre. El único cambio es
el autocompletado del identificador de cliente (§5.4):

- El campo de usuario acepta `JPEREZ` o `JPEREZ@NORTE`.
- Un `<datalist>` sugiere los `code` que ese equipo ya usó con éxito,
  leídos de `localStorage` vía `lib/storageKeys.ts` (que ya centraliza
  las claves del proyecto).
- Solo se guarda el `code` tras un login exitoso. Nunca el usuario ni la
  contraseña.
- Un texto de ayuda discreto explica el formato la primera vez, cuando
  todavía no hay nada guardado.

El mensaje de error no cambia y **no debe** cambiar: cliente
inexistente, usuario inexistente y contraseña incorrecta comparten
respuesta (§5.3). Si el frontend inventara un "cliente no encontrado",
rompería la mitigación del backend.

### 8.4 Selector de base en el chat

- En `WelcomeScreen.vue` / `Composer.vue`: selector visible **solo
  cuando no hay conversación activa**. Una vez creada, queda fija (D2).
- En una conversación existente: chip de solo lectura con el nombre del
  cliente. No es un control.
- En `Sidebar.vue` / `ConversationItem.vue`: el nombre del cliente por
  conversación. Con varios clientes, los títulos autogenerados se
  parecen entre sí y sin esto la lista se vuelve inutilizable.
- Si la base de la conversación abierta está inactiva o eliminada:
  banner y `Composer` deshabilitado con el motivo. El historial se sigue
  leyendo. Es el mismo patrón de solo-lectura que ya usa `/share/:id`.
- `usePermisosPolling.ts` ya detecta cambios de permisos en caliente vía
  `modules-version`. Conviene extenderlo para detectar que la base de la
  conversación abierta se desactivó, en lugar de descubrirlo al enviar.

---

## 9. Instalador

- `env.template`: agregar `ERP_CREDENTIALS_KEY={{ERP_CREDENTIALS_KEY}}`.
  `savi.iss` la genera al azar, igual que `JWT_SECRET`. Debe ser una
  clave Fernet válida: 32 bytes en base64 urlsafe (44 caracteres).
- `env.template`: agregar `SAVI_ADMIN_LOGINS={{SAVI_ADMIN_LOGINS}}` (D9).
  El asistente lo puede sembrar con el usuario de quien instala.
- **Advertencia en la documentación del instalador**: perder o cambiar
  `ERP_CREDENTIALS_KEY` obliga a re-ingresar la contraseña de cada
  cliente registrado. Es la clave que hay que preservar en una
  reinstalación, junto con la base `savi.db`. `DISTRIBUCION.md` es el
  lugar donde ya vive ese tipo de nota operativa.
- El bloque `ERP_DB_*` no cambia. Se documenta en el propio template que
  ahora es la **semilla de la base default**, y que el resto se
  administra desde la aplicación.
- Recordar la restricción de ASCII del template (Inno Setup no lee UTF-8;
  ya está documentada ahí).
- El asistente debería mencionar que después de instalar se pueden
  agregar más clientes desde la sección de administración.

---

## 10. Riesgos

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | **Fuga de datos entre clientes** si una conversación cambia de base | D2: base inmutable por conversación, FK NOT NULL en filas nuevas |
| R2 | **Colisión de identidad** entre bases (§3.2) | Identidad calificada `(erp_database_id, user_id)` en JWT, `conversations` y `usage` |
| R3 | Escalada de privilegios heredando `is_admin` de la base default | D3: permisos siempre en la base consultada, sin herencia |
| R4 | Agotamiento de conexiones con N clientes | D8: creación diferida, pools chicos, evicción LRU |
| R5 | Contraseña recuperable por quien acceda al equipo | D4, declarado explícitamente. No se promete más de lo que da |
| R6 | Registrar un Postgres que no es un ERP | D5 paso 3: verificación de esquema |
| R7 | Cambio de contraseña sin efecto hasta reiniciar | D8: invalidación explícita del engine al editar |
| R8 | Migración rompe la instalación de escritorio | Modelo registrado en `bootstrap.py` **y** `alembic/env.py`; batch mode; probar los dos caminos (SQLite nueva y SQLite existente) |
| R9 | Enumeración de clientes desde el login | §5.3: mismo error para cliente inexistente y contraseña mala, con costo igualado. Sin endpoint público de listado |
| R10 | Pérdida de `ERP_CREDENTIALS_KEY` deja la app sin arrancar | D4: `InvalidToken` marca `credentials_unreadable` y degrada esa base; el resto de SAVI arranca |
| R11 | `code` duplicado por índice parcial no creado en SQLite | Índice único parcial verificado en los dos caminos de esquema; test que intenta insertar un `code` repetido |
| R12 | La contraseña queda duplicada en claro en `.env` tras el seed | Pregunta abierta §13.6; aviso en el panel de administración mientras `ERP_DB_PASSWORD` tenga valor |

---

## 11. Plan de implementación por fases

Cada fase es entregable y verificable por separado.

**Fase 1 — Tabla, cifrado y registry.** `erp_databases` con su
migración, `CredentialCipher` + impl Fernet, `ERP_CREDENTIALS_KEY`, seed
de arranque (D7) y `ErpEngineRegistry` reemplazando `get_erp_engine()`
en los 7 consumidores de §3.1.

Al terminar, el sistema se comporta **exactamente igual que hoy**, pero
la única base existente ya está registrada en tabla en vez de
hardcodeada. Es la fase con más superficie tocada y cero cambio visible
— ideal para verificar sin ruido.

**Fase 2 — Identidad calificada.** Columnas `erp_database_id`, JWT con
claim `erp_db`, scoping de `conversations` / `refresh_tokens` / `usage`,
y el `rsplit("@")` del login con su hash dummy (§5.3).

Va antes de que exista la segunda base, y esa es la razón de su
posición: es la corrección del defecto de §3.2. Agregar un segundo
cliente sin esto ya produce el cruce de datos.

**Fase 3 — API de administración.** CRUD + test de conexión + `D9`.

**Fase 4 — Resolución de permisos por base.** D3 y
`GET /erp-databases/available`.

**Fase 5 — Turno multi-base.** `erp_database_id` a través de
`ChatTurnUseCase` → runner → tools MCP. Validación de base inactiva
antes de abrir el SSE.

**Fase 6 — Frontend administración.** `/admin`, CRUD, mover consumo.

**Fase 7 — Frontend chat y login.** Selector, chips, estado degradado,
autocompletado de `code`.

**Fase 8 — Instalador.** `ERP_CREDENTIALS_KEY`, `SAVI_ADMIN_LOGINS` y
documentación.

> **Recién al terminar la Fase 4 es seguro registrar un segundo
> cliente.** Antes de eso el aislamiento de identidad y de permisos no
> está completo. Conviene dejarlo explícito en el tablero de trabajo:
> es el tipo de atajo que se toma "solo para probar" y termina con datos
> cruzados en producción.

---

## 12. Testing

El repositorio hoy tiene 15 archivos de test para 7 módulos, y
`conversations`, `data_query` y `free_query` no tienen ninguno. Este
cambio toca aislamiento entre clientes: es el peor lugar posible para
seguir esa tendencia.

Mínimo exigible:

- **Aislamiento de identidad**: usuario con el mismo `idUsuario` en dos
  bases no ve las conversaciones ni el consumo del otro. Es el test que
  cubre R2 y no puede faltar.
- **Sin herencia de permisos**: admin en la base A no obtiene módulos en
  la base B (R3).
- **Inmutabilidad**: no existe camino que cambie el `erp_database_id` de
  una conversación (R1).
- **Cifrado**: ida y vuelta con Fernet; ningún response de la API
  contiene la contraseña, ni en claro ni cifrada; una clave equivocada
  marca `credentials_unreadable` en lugar de propagar la excepción.
- **Login calificado**: `JPEREZ@NORTE` resuelve la base `NORTE` y
  **solo** esa; un `code` inexistente devuelve exactamente el mismo
  error que una contraseña mala; un login sin `@` va a la default.
- **Sin enumeración**: el response de un `code` inexistente es
  indistinguible byte a byte del de una contraseña incorrecta.
- **Test de conexión**: rechaza un Postgres sin el esquema del ERP.
- **Base inactiva**: `POST /chat` devuelve `409` antes de abrir el SSE,
  no un error dentro del stream.
- **Registry**: editar una base dispone su engine; la evicción LRU
  respeta el tope.
- **Migración**: aplica sobre SQLite nueva (vía `create_all` +
  `stamp head`) y sobre SQLite existente (vía `upgrade`), con el índice
  único parcial funcionando en ambos.

---

## 13. Decisiones cerradas y preguntas abiertas

### Cerradas

| # | Pregunta | Resolución |
|---|---|---|
| 1 | ¿Qué base autentica el login? | Login calificado `USUARIO@CODE`, default si no se indica (§5) |
| 2 | ¿Conversaciones simultáneas de clientes distintos? | Sí, sin "cliente activo" de sesión (D10) |
| 3 | ¿Quién administra las bases? | `is_admin` de la base de identidad + `SAVI_ADMIN_LOGINS` como escape (D9) |
| 5 | ¿Nombre por defecto del cliente? | Se propone la razón social del ERP, editable (D5) |

### Abiertas

**4. ¿Cuántos clientes por instalación?**

El diseño de pools de D8 (creación diferida, `pool_size=3`, evicción
LRU) está dimensionado para **decenas**. Los números concretos a definir:

- Tope de engines vivos simultáneos (propuesta inicial: 10).
- Minutos de inactividad antes de disponer un engine (propuesta: 15).

Con cientos de clientes hay que reconsiderar el enfoque — probablemente
conexiones por demanda sin pool persistente. **No bloquea el arranque**:
son dos constantes configurables, ajustables cuando se conozca el
número real de uso.

**6. Migración de la contraseña actual del `.env`.**

El seed de D7 toma `ERP_DB_PASSWORD` en claro del `.env` y la cifra al
insertar la fila default. Queda abierto si después de eso hay que
**vaciar la variable del `.env`** — la contraseña quedaría duplicada,
cifrada en la tabla y en claro en el archivo.

Vaciarla es lo correcto en cuanto a higiene, pero implica que la
aplicación escriba sobre su propio `.env`, lo que rompe la propiedad de
que el `.env` es de solo lectura en runtime. La alternativa es
documentarlo como paso manual post-instalación.

Recomendación: **paso manual documentado**, y que el panel de
administración muestre un aviso mientras `ERP_DB_PASSWORD` siga teniendo
valor. Se resuelve en Fase 8.
