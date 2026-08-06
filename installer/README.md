# Instalador de escritorio de SAVI

Genera un único `SAVI-Setup-<version>.exe` que instala SAVI en un
computador Windows normal: sin Docker, sin servidor, sin línea de
comandos para el usuario final.

> Este archivo es el **procedimiento**. El estado del trabajo, las
> decisiones y los bloqueos abiertos están en
> [`DISTRIBUCION.md`](DISTRIBUCION.md).

## Qué produce

```
installer/output/SAVI-Setup-0.1.0.exe
```

Ese `.exe` lleva adentro el backend empaquetado (Python + FastAPI +
dependencias), el frontend Vue compilado y el catálogo de conocimiento.
Descarga e instala los prerrequisitos que falten en el equipo destino.

## Requisitos para compilar

| Herramienta | Para qué | Dónde |
|---|---|---|
| `uv` | Dependencias y empaquetado del backend | https://docs.astral.sh/uv/ |
| Node.js 22+ | Build del frontend | https://nodejs.org/ |
| Inno Setup 6.1+ | Compilar el instalador | https://jrsoftware.org/isdl.php |

Además hace falta el catálogo de conocimiento en
`backend/app/modules/knowledge/data/`. El build aborta si falta y
advierte si está vacío.

## Compilar

```powershell
.\installer\build.ps1
```

Encadena los cuatro pasos: frontend → staging → PyInstaller → Inno Setup.

Opciones útiles al iterar:

```powershell
.\installer\build.ps1 -SkipFrontend    # reutiliza el build de Vue
.\installer\build.ps1 -SkipInstaller   # se detiene después de PyInstaller
```

## Qué hace el asistente de instalación

1. **Requisitos del sistema** — detecta qué falta y lo muestra.
   - **CLI de Claude Code**: se busca igual que lo busca el SDK — primero
     en el PATH, después en las rutas conocidas de npm, yarn y del
     instalador nativo (`%USERPROFILE%\.local\bin\claude.exe`). Buscar
     solo en las rutas de npm daba un falso negativo en equipos con el
     CLI puesto de forma nativa.
   - **Node.js**: no es requisito de SAVI. Solo se instala si hace falta
     para poner el CLI con `npm install -g`. Si el CLI ya está, no se
     baja.
   - **Git for Windows**: por su `bash.exe`, que necesita el SDK.

   Las claves del registro se leen con `HKLM64` y se miran las dos
   carpetas de Program Files, para que la detección no dependa de la
   arquitectura con la que corra el instalador.
2. **Base de datos del ERP** — servidor, puerto, base, usuario y
   contraseña. Obligatoria: es la fuente de datos que SAVI interpreta.
   SAVI la abre en modo solo lectura forzado.
3. **Base de datos de SAVI** — dónde vive el historial de conversaciones:
   - *Archivo local* (por defecto): SQLite, sin nada que administrar.
   - *Servidor PostgreSQL*: para compartir el historial entre equipos.
4. **Autenticación de Claude y puerto** — normalmente se dejan los dos
   campos de credencial **vacíos** y la autenticación se resuelve al
   final, en el navegador. Ver [Autenticación contra Claude](#autenticación-contra-claude).

Al terminar descarga e instala los prerrequisitos faltantes, genera el
archivo `.env`, crea los accesos directos y ofrece iniciar sesión con la
cuenta de Claude del cliente.

## Actualizaciones

No hay servidor ni botón de "buscar actualizaciones": **el mecanismo de
actualización es el mismo instalador**. Se sube `AppVersion` en
`savi.iss`, se compila, y el cliente corre el nuevo
`SAVI-Setup-<version>.exe`.

Inno reconoce la instalación previa por el `AppId` fijo y actualiza en el
lugar: reemplaza los archivos, mantiene los accesos directos y no duplica
la entrada en *Programas y características*.

Qué se conserva, y por qué no hace falta preguntar nada:

| Qué | Cómo sobrevive |
|---|---|
| Configuración (`.env`) | El instalador lo escribe solo si no existe. Si ya está, las cuatro páginas del asistente se saltean |
| Sesiones abiertas | Al no reescribir el `.env`, el `JWT_SECRET` no se regenera |
| Conversaciones y mensajes | La base vive en `%LOCALAPPDATA%\SAVI\`, fuera de Program Files |
| Esquema de la base | `bootstrap.py` corre `upgrade head` sobre una base existente |

La actualización queda en tres clics: *Siguiente* → *Instalar* →
*Finalizar*. La página de confirmación avisa explícitamente que la
configuración se conserva.

> **Regla de release, no negociable**: una variable nueva en
> `env.template` **no llega** a las instalaciones ya existentes — su
> `.env` no se reescribe. Toda variable que se agregue tiene que tener
> default en `Settings`, o la actualización rompe el arranque en el
> equipo del cliente. Si un cambio realmente exige configuración nueva,
> hay que pedirla en el asistente y hacer un merge del `.env`, que hoy no
> está implementado.

## Dónde queda cada cosa

| Qué | Dónde | Por qué |
|---|---|---|
| Aplicación | `C:\Program Files\SAVI\` | Solo lectura para el usuario |
| Configuración | `C:\Program Files\SAVI\.env` | Escribible solo por administradores |
| Base SQLite | `%LOCALAPPDATA%\SAVI\savi.db` | Program Files no es escribible sin privilegios |
| Log | `%LOCALAPPDATA%\SAVI\savi.log` | Primer lugar donde mirar ante un fallo |
| Logs rotados | `%LOCALAPPDATA%\SAVI\savi.log.1` … `.3` | Historia previa; `.1` es el más reciente |
| CLI de Claude | `C:\ProgramData\npm\` | Prefijo común: lo ven todas las cuentas del equipo |

La ruta de la base SQLite se resuelve **en tiempo de ejecución**, no en la
instalación: si IT instala con una cuenta de administrador, su
`%LOCALAPPDATA%` no es el del usuario que después usa SAVI.

## Autenticación contra Claude

SAVI usa la suscripción de Claude (Pro o Max) **del cliente**. Hay tres
caminos, y el asistente los soporta a los tres:

| Camino | Cuándo | Dónde queda la credencial |
|---|---|---|
| **Iniciar sesión** (recomendado) | El cliente tiene su cuenta y usa SAVI en su propia sesión de Windows | Perfil de Windows del usuario que hizo el login |
| **Token** (`claude setup-token`) | Servidores, o cuando SAVI corre con una cuenta de Windows distinta de la que instaló | `CLAUDE_CODE_OAUTH_TOKEN` en el `.env` |
| **Clave de API** | SEO Group provee la credencial | `ANTHROPIC_API_KEY` en el `.env` |

El primero es el que evita todo copiar y pegar: al terminar la
instalación, el asistente ofrece la casilla *"Iniciar sesión con la
cuenta de Claude"*, se abre el navegador, el cliente entra y listo. El
mismo flujo queda como acceso directo **Iniciar sesión en Claude** para
cuando la sesión se venza o el cliente cambie de cuenta:

```
SAVI.exe --login
```

Ese comando intenta primero `claude auth login` y, si eso no alcanza,
ofrece generar un token con `claude setup-token` y lo escribe solo en el
`.env`.

> **Por qué el token existe además del login**: `claude auth login` deja
> las credenciales en el perfil de Windows de **quien hizo el login**. Si
> IT instala elevado con una cuenta de administrador y el cliente después
> usa SAVI con la suya, esa sesión no se encuentra. En un servidor o bajo
> un servicio, lo mismo. El token vive en el `.env`, junto a la
> aplicación, así que sobrevive al cambio de cuenta.

Escribir el `.env` requiere privilegios de administrador (vive en Program
Files). Si el camino del token falla por permisos, el propio comando
avisa que hay que reabrirlo con *clic derecho → Ejecutar como
administrador*.

## Diagnóstico

El instalador crea un acceso directo **Diagnosticar SAVI**, que valida el
`.env` y prueba las dos conexiones:

```
SAVI.exe --check-config
```

Es lo primero que hay que pedirle a alguien que reporta que la
aplicación no abre.

### "No pudo cerrar de forma automática todas las aplicaciones"

Si aparece durante una actualización, es que SAVI estaba corriendo. El
Restart Manager de Windows cierra aplicaciones mandándoles un `WM_CLOSE`,
y `SAVI.exe` corre uvicorn sin ventana ni bucle de mensajes, así que no
lo escucha — **Reintentar no destraba nada**.

Por eso el `[Setup]` usa `CloseApplications=force`: el instalador termina
el proceso él mismo en vez de pedirlo. Si aun así aparece el cartel:

```
taskkill /IM SAVI.exe /F
```

y después *Reintentar*. **Nunca elijas "Ignorar el error y continuar"**:
deja el ejecutable viejo en su lugar, así que la instalación dice ser la
versión nueva y corre código viejo — el peor de los dos mundos para
diagnosticar después.

### El log

Todo lo que pasa queda en `%LOCALAPPDATA%\SAVI\savi.log`, incluidas las
peticiones HTTP y los errores del servidor. Un 500 aparece con las dos
líneas que hacen falta para diagnosticarlo — la excepción con su stack y
el request que la disparó:

```
2026-08-05 22:23:29 ERROR uvicorn.error: Exception in ASGI application
Traceback (most recent call last):
  ...
RuntimeError: <la causa real>
2026-08-05 22:23:29 INFO  uvicorn.access: 127.0.0.1 - "POST /auth/login HTTP/1.1" 500
```

Eso funciona porque uvicorn se lanza con `log_config=None`: no instala
handlers propios, así que sus loggers propagan al root que configura
`launcher._configure_logging()`. **Pasarle un `log_config` a
`uvicorn.run()` rompería esto** y dejaría a soporte sin la única pista
que tiene; hay un test que lo cubre
(`tests/unit/infrastructure/test_log_rotation.py`).

Rota a los 5 MB y guarda 3 respaldos (`savi.log.1` … `.3`), o sea ~20 MB
como techo. Para pedirle el log a un cliente, que mande los cuatro
archivos: un problema intermitente puede haber quedado en un respaldo.

Los logs son **locales a cada equipo** — no hay nada que los centralice.

Otros modos:

```
SAVI.exe --login          # inicia sesión con la cuenta de Claude del cliente
SAVI.exe --no-browser     # arranca sin abrir el navegador
```

## Decisiones de empaquetado

- **PyInstaller en modo `onedir`, no `onefile`.** `onefile` descomprime
  ~200 MB a un temporal en cada arranque, dispara falsos positivos de
  antivirus, y borra el directorio del bundle al salir — lo que complica
  el subproceso `claude` que lanza el módulo `chat`. El "un solo `.exe`"
  que ve el usuario es el instalador, no el binario.
- **El frontend se sirve desde el backend**, mismo origen. El build se
  hace con `VITE_API_BASE_URL=/`; los dos consumidores del frontend
  recortan la barra final, así que las llamadas quedan relativas.
- **`APP_HOST=127.0.0.1`.** Con `0.0.0.0` el equipo publicaría en toda la
  red un agente con acceso de lectura al ERP.
- **`JWT_SECRET` se genera con el RNG criptográfico de .NET** durante la
  instalación. El generador pseudoaleatorio de Inno no sirve para una
  clave de firma.

## Pendiente

- Firma de código (Authenticode). Sin firmar, Windows SmartScreen
  muestra una advertencia en cada instalación.
