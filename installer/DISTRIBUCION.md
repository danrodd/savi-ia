# Distribución de escritorio de SAVI

SAVI se distribuye como un instalador único de Windows para computadores
normales: sin Docker, sin servidor de bases de datos, sin línea de
comandos para el usuario final. Este documento explica el estado del
trabajo, las decisiones tomadas y lo que falta. Para el procedimiento de
compilación, ver [`README.md`](README.md).

---

## Estado actual

| Fase | Alcance | Estado |
|---|---|---|
| **1. Prerrequisitos bajo demanda** | El instalador detecta y descarga lo que falte | Implementada y compilada |
| **2. Empaquetar el stack completo** | Todo dentro del instalador, sin descargas | Pendiente (ver [hallazgo clave](#el-sdk-ya-trae-el-cli-adentro)) |
| **3. Migrar a `anthropic` directo** | Eliminar la dependencia del CLI | Pendiente |

**Artefacto**: `installer/output/SAVI-Setup-0.1.0.exe` — 28 MB.

### Qué está verificado y qué no

| Verificado | Cómo |
|---|---|
| El ejecutable empaquetado arranca | Ejecución real de `SAVI.exe` |
| Crea el esquema SQLite y sella Alembic en `head` | Inspección de `savi.db` tras el arranque |
| Sirve la SPA y el API desde el mismo origen | `curl` contra `/`, `/consumo`, `/openapi.json`, `/assets/*` |
| El bundle incluye alembic, frontend, knowledge y tzdata | Listado del directorio `_internal` |
| La detección de prerrequisitos | Banco de pruebas en Inno que aborta sin instalar |
| El script del instalador compila | `ISCC.exe savi.iss` |

| **No** verificado | Por qué |
|---|---|
| Ejecutar el instalador de punta a punta | Instalaría SAVI en Program Files y modificaría el PATH del sistema; requiere autorización |
| Navegación del asistente y generación del `.env` | Solo se ejercita ejecutando el instalador |
| La rama de descarga de prerrequisitos | Este equipo ya los tiene; hace falta una máquina limpia o una VM |
| Si `CLAUDE_CODE_GIT_BASH_PATH` sigue siendo necesario | `claude.exe --version` no ejercita un turno real con tools |

---

## El problema de fondo

Empaquetar SAVI no es solo empaquetar Python. El módulo `chat` usa
`claude-agent-sdk`, que **lanza el binario `claude` como subproceso**.
Ese binario no es una librería de Python: PyInstaller no lo recoge solo.

Orden de búsqueda del SDK
(`claude_agent_sdk/_internal/transport/subprocess_cli.py:81`):

1. Un CLI empaquetado dentro del propio paquete (`_bundled/claude.exe`).
2. `shutil.which("claude")` — el PATH.
3. Seis rutas conocidas de npm, yarn y del instalador nativo.

> **Claude Desktop no sirve.** Es una aplicación de chat para usuario
> final; no deja ningún binario `claude` que el SDK pueda lanzar. Si un
> equipo lo tiene instalado, es irrelevante para SAVI.

### El SDK ya trae el CLI adentro

El paquete `claude-agent-sdk` instalado incluye `claude.exe` (234 MB) en
`_bundled/`. Se verificó que es autónomo: ejecutado con el PATH reducido
a `system32` únicamente, sin Node ni Git, responde `2.1.150 (Claude
Code)`.

**Consecuencia para la fase 2**: no hace falta empaquetar Node.js
portable. Basta con agregar ese archivo a los `datas` del `.spec` y
eliminar del instalador la detección y descarga de Node y del CLI. El
instalador pasaría de 28 MB a unos 260 MB y quedaría con un solo
prerrequisito externo (git-bash) en lugar de tres.

PyInstaller **no** lo incluye hoy: es un archivo de datos, no un módulo.
Por eso la instalación actual depende del CLI del sistema.

---

## Cambios en el backend

Todos preservan el comportamiento sobre PostgreSQL: el DDL generado es
idéntico y las instalaciones existentes no requieren migración.

| Área | Decisión | Archivo |
|---|---|---|
| Tipos de columna | `UuidType`, `JsonType`, `UtcDateTime` reemplazan a `sqlalchemy.dialects.postgresql` | `app/infrastructure/database/types.py` |
| Selección de motor | `AGENT_DB_ENGINE` (`sqlite` \| `postgresql`); las credenciales de PG se validan solo en ese modo | `app/infrastructure/config/settings.py` |
| Conexión SQLite | `PRAGMA foreign_keys=ON`, `journal_mode=WAL`, `synchronous=NORMAL` | `app/infrastructure/database/pool.py` |
| Esquema inicial | `create_all` + `alembic stamp head` sobre BD nueva; `upgrade head` sobre BD existente | `app/infrastructure/database/bootstrap.py` |
| Rutas de recursos | `resource_dir()` y `data_dir()`, válidas en desarrollo y empaquetado | `app/paths.py` |
| Frontend | FastAPI sirve el build de Vue desde el mismo origen | `app/main.py` |
| Punto de entrada | Bootstrap, log en disco, diagnóstico, apertura del navegador | `app/launcher.py` |

### Trampas que motivaron esas decisiones

Cada una produce un fallo silencioso, no un error de compilación.

| Trampa | Síntoma si se ignora |
|---|---|
| SQLite descarta el `tzinfo` sin avisar | `expires_at` vuelve *naive*; comparar contra `datetime.now(UTC)` lanza `TypeError` en el refresh de tokens |
| SQLite trae las foreign keys **apagadas** | Los `ondelete="CASCADE"` no se aplican; quedan mensajes huérfanos |
| Sin WAL, los writers que sobreviven a la cancelación compiten con las lecturas | `database is locked` a mitad de un turno |
| Windows no trae base de datos de zonas horarias | `ZoneInfoNotFoundError` en cualquier equipo cliente; obliga a la dependencia `tzdata` |
| El repositorio de `usage` usaba `func.timezone()` y `percentile_cont()` | Ambas son exclusivas de PostgreSQL; el módulo completo falla en SQLite |

Las migraciones existentes **no** se reproducen sobre SQLite porque
varias usan construcciones de PostgreSQL: la inicial declara
`server_default=sa.text('now()')` y `a43047be72dd` referencia
`postgresql.JSONB`. Para migraciones futuras, `render_as_batch` ya está
activo cuando el dialecto es SQLite.

---

## Qué hace el instalador

### Pasos del asistente

1. **Requisitos del sistema** — detecta el CLI de Claude, Node.js y
   Git for Windows, y muestra cuáles faltan.
2. **Base de datos del ERP** — obligatoria. SAVI la abre en modo solo
   lectura forzado.
3. **Base de datos de SAVI** — archivo local (por defecto) o servidor
   PostgreSQL.
4. **Clave de API y puerto** — clave de Anthropic y puerto local.

Al finalizar instala los prerrequisitos faltantes, genera el `.env` y
crea los accesos directos.

### Decisiones de seguridad

| Decisión | Razón |
|---|---|
| `APP_HOST=127.0.0.1` | Con `0.0.0.0` el equipo publicaría en toda la red un agente con acceso de lectura al ERP |
| `JWT_SECRET` generado con el RNG criptográfico de .NET | El generador pseudoaleatorio de Inno no es apto para una clave de firma |
| `ERP_CREDENTIALS_KEY` (clave Fernet) generada con el mismo RNG | Cifra las contraseñas de conexión de las bases del ERP; base64 **url-safe**, no estándar, porque Fernet valida el alfabeto |
| El `.env` queda en Program Files | Legible por el usuario, escribible solo por administradores |
| `AGENT_DB_PATH` se deja vacío en el `.env` | Se resuelve en tiempo de ejecución contra el `%LOCALAPPDATA%` de quien **usa** la aplicación, no de quien la instaló |

Ese último punto importa en empresas: si el área de sistemas instala con
una cuenta de administrador, su `%LOCALAPPDATA%` no es el del usuario
final.

> **Clave a preservar en una reinstalación.** `ERP_CREDENTIALS_KEY`
> descifra las contraseñas de conexión de todas las bases de clientes
> registradas desde la aplicación. Si se reinstala con una clave nueva
> —o se restaura un `.env` de otro backup—, esas contraseñas quedan
> ilegibles y hay que volver a cargarlas una por una desde la sección de
> Administración. La aplicación **no** se rompe (las bases quedan marcadas
> "credenciales ilegibles" y el resto funciona), pero es trabajo
> manual evitable. Al respaldar un equipo, guardar juntos `savi.db` **y**
> el `.env` — o al menos el valor de `ERP_CREDENTIALS_KEY`.

### Multi-BD del ERP

El instalador sigue pidiendo **una** BD del ERP. Esa conexión se siembra
como la base **por defecto** la primera vez que arranca SAVI; de ahí en
más, las demás bases de clientes se agregan desde la aplicación
(Administración → Bases de datos), sin reinstalar ni reiniciar.

- La contraseña del `.env` se cifra en `savi.db` al sembrar. Queda
  duplicada (cifrada en la BD, en claro en el `.env`); por higiene se
  puede vaciar `ERP_DB_PASSWORD` del `.env` una vez confirmado el primer
  arranque exitoso. La aplicación avisa mientras siga teniendo valor.
- `SAVI_ADMIN_LOGINS` queda vacío: un administrador del ERP ya tiene la
  sección de Administración por su flag. Se completa a mano solo para dar
  acceso a un agente de soporte que **no** es admin en el ERP.

### Ubicación de cada componente

| Componente | Ruta | Razón |
|---|---|---|
| Aplicación | `C:\Program Files\SAVI\` | Solo lectura para el usuario |
| Configuración | `C:\Program Files\SAVI\.env` | Escribible solo por administradores |
| Base SQLite | `%LOCALAPPDATA%\SAVI\savi.db` | Program Files no es escribible sin privilegios |
| Log | `%LOCALAPPDATA%\SAVI\savi.log` | Primer lugar donde mirar ante un fallo |
| CLI de Claude | `C:\ProgramData\npm\` | Prefijo común: visible para todas las cuentas del equipo |

---

## Hallazgos de Inno Setup

Cinco defectos reales encontrados al compilar y probar. Se documentan
porque ninguno es evidente y todos costarían tiempo redescubrirlos.

| # | Hallazgo | Corrección |
|---|---|---|
| 1 | Un comentario `{ ... }` termina en la **primera** llave de cierre. Una constante de Inno escrita adentro corta el comentario y lo que sigue se compila como código | Los bloques que mencionan constantes usan `//` |
| 2 | `HKLM\SOFTWARE\GitForWindows` existe solo en la vista de **64 bits**; un instalador de 32 bits lee redirigido a `Wow6432Node` | `RegQueryStringValue(HKLM64, ...)` y búsqueda en las dos carpetas de Program Files |
| 3 | Las claves `InstallPath` del registro traen barra final | `RemoveBackslashUnlessRoot()` antes de concatenar |
| 4 | `LoadStringFromFile` espera `AnsiString`, no `String`. No existe ningún cargador UTF-8 | API de arrays; `env.template` se mantiene en **ASCII puro** |
| 5 | `Val()` no existe en Pascal Script; `Label` es palabra reservada | `StrToIntDef()`; el parámetro se llama `Which` |

> **Sobre el punto 4**: los valores que escribe el usuario en el
> asistente sí se guardan en UTF-8 — provienen de la interfaz, no del
> archivo. El `.env` se escribe con `SaveStringsToUTF8FileWithoutBOM`
> porque `pydantic-settings` lo lee como UTF-8 y un BOM convertiría la
> primera clave en `\ufeffAPP_NAME`.

### Falso negativo corregido en la detección del CLI

La detección original solo buscaba `claude.cmd` en rutas de npm. El
instalador **nativo** del CLI deja el binario en
`%USERPROFILE%\.local\bin\claude.exe`, así que un equipo con el CLI
funcionando correctamente recibía una descarga e instalación de Node y
npm innecesarias (~80 MB).

La detección ahora replica el orden de `_find_cli` del SDK. Y como
Node.js solo se usa para instalar el CLI con `npm install -g`, la
condición pasó a ser:

```pascal
NeedsNode := NeedsCli and (NodeExePath() = '');
```

Node.js **no es un requisito de SAVI**.

---

## Bloqueos abiertos

- [x] **Catálogo de conocimiento.** Generado desde
      `sisfec_knowledge_base_v2.json` (kb 2.0.0) y versionado: 10 módulos,
      101 formularios, 4 flujos y 29 FAQs. Los módulos `Inicio` y
      `Seguridad` se omiten a propósito (ver `scripts/bootstrap_knowledge.py`).
      Para regenerarlo:
      `uv run python -m scripts.bootstrap_knowledge --source <sisfec_knowledge_base_v2.json> --target app/modules/knowledge/data`
      — el script escribe CRLF en Windows; normalizar a LF antes de
      commitear (`.gitattributes` fija `eol=lf`).
- [ ] **Probar el instalador de punta a punta**, idealmente en una
      máquina limpia.
- [x] **`installer/assets/savi.ico`** — presente.
- [ ] **Firma de código (Authenticode).** Sin firmar, SmartScreen
      advierte en cada instalación.
- [x] **`frontend/package-lock.json`** — versionado.

---

## Cómo verificar

```powershell
# Compilar todo
.\installer\build.ps1

# Diagnóstico: valida el .env y prueba las dos conexiones
SAVI.exe --check-config

# Arranque sin abrir el navegador (pruebas, ejecución desatendida)
SAVI.exe --no-browser
```

```powershell
# Suite del backend, incluidos los tests de portabilidad
cd backend
uv run pytest -q
uv run ruff check app tests
uv run pyright app
```

Los tests que cubren esta línea de trabajo están en
`backend/tests/unit/infrastructure/`:

| Archivo | Cubre |
|---|---|
| `test_sqlite_compat.py` | Tipos portables, `tzinfo`, cascadas de FK, agregados de `usage` |
| `test_spa_serving.py` | Fallback de vue-router, 404 JSON del API, path traversal |

---

## Próximo paso

Decidir entre:

1. **Ejecutar el instalador** en este equipo o en una VM, para cerrar la
   verificación pendiente.
2. **Avanzar a la fase 2** con el alcance reducido que habilita el
   hallazgo del CLI empaquetado: agregar `_bundled/claude.exe` al
   `.spec` y podar Node del instalador.
3. **Conseguir el catálogo de conocimiento**, que es el único bloqueo
   que impide distribuir algo útil.
