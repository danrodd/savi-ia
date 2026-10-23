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
   - *Servidor PostgreSQL* (por defecto y recomendado): varios usuarios,
     historial compartido y con respaldo. Ver *"Credencial ilegible"* en
     Diagnóstico antes de apuntar dos instalaciones a la misma base.
   - *Archivo local*: SQLite, solo para pruebas o un único usuario.
4. **Autenticación de Claude y puerto** — el puerto viene precargado en
   **31900** y casi nunca hay que cambiarlo (ver *Puerto local* abajo).
   Normalmente se dejan los dos
   campos de credencial **vacíos** y la autenticación se resuelve al
   final, en el navegador. Ver [Autenticación contra Claude](#autenticación-contra-claude).

Al terminar descarga e instala los prerrequisitos faltantes, genera el
archivo `.env`, crea los accesos directos y ofrece iniciar sesión con la
cuenta de Claude del cliente.

Si el equipo ya tiene SAVI, antes de estos pasos aparece **Configuración
existente**: *Conservar la configuración actual* (actualiza sin preguntar
nada) o *Modificar la configuración*. Al modificar, las páginas traen los
valores del `.env` actual —servidores, puertos, usuarios, contraseñas y
tokens—, así que se cambia solo lo necesario (por ejemplo, el nombre de la
base de SAVI) sin conocer de nuevo las credenciales. Se conservan
`ERP_CREDENTIALS_KEY` y `SAVI_ADMIN_LOGINS`; el `.env` anterior queda como
`.env.anterior`.

## Puerto local

El asistente precarga **31900** y deja el campo editable. No es 8000 a
propósito: es de los puertos más disputados que existe, y una colisión
hacía fallar el arranque en el equipo del cliente. 31900 está en el rango
de puertos de usuario, lejos de los servicios comunes, y **por debajo de
49152** — desde ahí arranca el rango dinámico de Windows y el sistema
puede entregar esos puertos a conexiones de salida, lo que produciría
fallos intermitentes y sin patrón.

Si aun así el puerto está tomado, el launcher **prueba los 20
siguientes** y usa el primero libre en vez de abortar. No hace falta que
nadie sepa el número: el acceso directo lanza el launcher, que abre el
navegador en la URL correcta.

> Consecuencia a tener presente: el puerto efectivo puede no ser el
> configurado. Un marcador del navegador guardado a mano puede quedar
> apuntando al puerto viejo. El acceso directo siempre acierta.

El acceso directo *Diagnosticar SAVI* informa qué puerto está libre, si
SAVI ya está corriendo, y a cuál va a caer si el configurado está tomado.

## Versionado

**La versión es el tag de git. No existe en ningún otro lado.** No hay
un número escrito en `_version.py`, `pyproject.toml` ni `package.json`
que haya que acordarse de subir: un número escrito en dos lugares
termina desincronizado, y la aplicación afirma ser una versión que no es.

### De dónde sale

`scripts/version.py` (raíz del monorepo) es la única fuente. Usa
`git describe --tags --always --dirty`:

| Muestra | Significa |
|---|---|
| `v1.4.0` | exactamente esa versión publicada |
| `v1.4.0-14-gbf8eee7` | 14 commits después de `v1.4.0`, en el commit `bf8eee7` |
| `fa9e698` | todavía no hay ningún tag |
| `…-sucio` | construido con cambios sin commitear |

Sin git (y sin build) la aplicación dice `0.0.0-dev`, nunca un número
que parezca real.

### Cómo llega a la aplicación

`build.ps1` la resuelve **una vez** y de ahí sale todo:

```
scripts/version.py
      └── build.ps1
            ├── frontend  → VITE_APP_VERSION, incrustada en el bundle
            ├── backend   → genera app/_build_version.py antes de PyInstaller
            │               (el equipo del cliente no tiene .git) y lo borra al terminar
            └── Inno Setup → /DAppVersion (texto) y /DAppVersionNumber (X.Y.Z,
                             que exige el recurso de versión del .exe)
```

`build.ps1` **se niega a construir con cambios sin commitear**: un
instalador que se entrega tiene que corresponder a un commit exacto.
Para una prueba local: `.\installer\build.ps1 -AllowDirty`.

En desarrollo no hace falta nada: el backend y Vite calculan la versión
con git al arrancar.

### Dónde se ve

| Superficie | Cómo |
|---|---|
| API | `GET /version` → `{version, commit, compilado, entorno}`, sin autenticación |
| API | `GET /health` y el log de arranque: `SAVI v1.4.0 arrancando` |
| Launcher | Reporte de "Diagnosticar SAVI" |
| Interfaz | Pie del sidebar del chat (dentro del cajón en móvil), pie del menú de Administración y la pantalla de login |

Es lo primero que hay que pedirle a un cliente que reporta un problema.

### Crear una versión

```powershell
python scripts/version.py --proponer      # calcula la siguiente y muestra las notas
python scripts/version.py --crear         # crea el tag anotado calculado
python scripts/version.py --crear v2.0.0  # o el número que decida una persona
git push origin v1.5.0
```

Para probar una versión antes de publicarla se usan **candidatas**
(`-rc.N`), que se crean en `staging`:

```powershell
python scripts/version.py --crear --rc    # v1.5.0-rc.1, luego rc.2…
git push origin v1.5.0-rc.1
```

Una candidata se compila y se publica solo en el canal `beta` (ver la
[spec 09](../docs/plataforma/09-actualizacion-automatica.md)): `stable` la
rechaza. El orden es `v1.5.0-rc.1 < v1.5.0-rc.2 < v1.5.0 < v1.5.1-rc.1`, así que
una instalación con la candidata se actualiza a la siguiente y a la final.
La final se crea en `main`, sobre el mismo commit que se probó como
candidata, y compila otro instalador: la candidata no se "promueve".

El salto sale de los conventional commits desde el último tag:

| En los commits | Salto |
|---|---|
| `tipo!:` o `BREAKING CHANGE:` | mayor (antes de 1.0.0: menor) |
| `feat:` | menor |
| `fix:` / `perf:` | parche |
| solo `docs`, `chore`, `ci`, `test`, `style`, `refactor` | ninguno: se niega a versionar |

La primera versión no se calcula —no hay tag previo desde el cual
medir—: se crea con un número explícito.

`--crear` exige estar en `main` (con `--rc`, en `staging`), con el árbol
limpio y en un commit que no tenga ya un tag. Las candidatas no cuentan como
"último tag": el salto se mide desde la última versión final. **No hace push**: publicar el tag es una acción
explícita.

### Notas de versión

Las genera el script desde los conventional commits, agrupadas por tipo,
y quedan en el mensaje del tag anotado: `git show v1.4.0`. No hay
`CHANGELOG.md` a propósito: uno mantenido a mano se desactualiza; uno
generado del historial no puede.

### Flujo

Los tags viven solo en `main`. El orden es **merge → tag → build**:
taguear antes del merge apunta a un árbol que no se publica, y construir
antes del tag deja el instalador con la distancia (`-3-gabc1234`) en
lugar del número limpio.

## Actualizaciones

No hay servidor ni botón de "buscar actualizaciones": **el mecanismo de
actualización es el mismo instalador**. Se sube la versión (ver arriba),
se compila con `build.ps1`, y el cliente corre el nuevo
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

### Pantalla en blanco: los scripts llegan como `text/plain`

**Síntoma:** SAVI arranca (el log muestra `GET /` y los `/assets/*.js`
con 200) pero el navegador queda en blanco. La consola (`F12`) dice:

```
Refused to execute script from '.../theme-init.js' because its MIME type ('text/plain') is not executable
Failed to load module script: ... the server responded with a MIME type of "text/plain"
```

**Causa:** `FileResponse` deduce el tipo con `mimetypes`, que en Windows
lee `HKEY_CLASSES_ROOT\.js` → `Content Type`. Algunos programas (editores,
entornos de desarrollo, instaladores) lo dejan en `text/plain`. Con
`X-Content-Type-Options: nosniff`, Chrome y Firefox se niegan a ejecutar
el script. Depende del equipo, no de la versión de SAVI: por eso los
demás equipos funcionan.

**Desde v1.3.1** el build se sirve con tipos fijos (`_SPA_MEDIA_TYPES` en
`backend/app/main.py`) y ya no depende del registro; lo cubre
`tests/unit/test_spa_media_types.py`. En versiones anteriores, se
comprueba con `reg query "HKCR\.js" /v "Content Type"` y se corrige en
PowerShell como administrador, sin reinstalar:

```
reg add "HKCR\.js" /v "Content Type" /t REG_SZ /d "text/javascript" /f
reg add "HKCR\.css" /v "Content Type" /t REG_SZ /d "text/css" /f
```

Después, reiniciar SAVI desde la bandeja y recargar con `Ctrl+F5`.

### "Credencial ilegible: ERP_CREDENTIALS_KEY no coincide"

**Síntoma:** el diagnóstico marca `[FALLA] Proveedor de IA: ... La
credencial falta o no se puede leer` y el log repite `Credencial
ilegible para el proveedor de IA ...: ERP_CREDENTIALS_KEY no coincide`
(o lo mismo para una base del ERP).

**Causa:** las claves de proveedores y las contraseñas de las bases se
guardan **cifradas en la base de SAVI**, pero la llave
(`ERP_CREDENTIALS_KEY`) vive en el `.env` de **cada equipo** y el
instalador genera una por instalación. Si dos instalaciones apuntan a la
misma base de SAVI en PostgreSQL, lo que cifró una no lo puede leer la
otra.

**Solución**, una de dos:

- **Base propia por instalación:** *Modificar la configuración* y cambiar
  solo el nombre de la base en *PostgreSQL de SAVI*. SAVI la crea si no
  existe (el usuario necesita permiso para crear bases). Arranca vacía:
  hay que cargar de nuevo la clave del proveedor de IA.
- **Base compartida:** copiar `ERP_CREDENTIALS_KEY` del `.env` del primer
  equipo al de los demás y reiniciar SAVI. No recargar la clave desde el
  segundo equipo: quedaría cifrada con su llave y fallaría en el primero.

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

- **Modelo de embeddings int8.** El bundle lleva
  `Xenova/multilingual-e5-small` (`onnx/model_quantized.onnx`, 118 MB)
  y no el fp32 de `intfloat` (465 MB, 65 % del bundle). Calidad medida
  contra fp32: coseno medio 0,9965 y solapamiento top-5 0,90. Se baja con
  `cd backend && uv run download-embedding-model` (lo hace `build.ps1`);
  `savi.spec` empaqueta solo ese `.onnx` más tokenizer/config y aborta si
  falta. El archivo se puede cambiar con `COMPANY_DOCS_EMBEDDING_MODEL_FILE`.
  Los documentos ya indexados con fp32 se reindexan solos tras actualizar.
- **Exclusiones del bundle**: `hf_xet` (solo sirve para descargar; el
  modelo se carga con `local_files_only`). `babel` se queda: lo importa
  `courlan` (importar desde la web). tcl/tk se queda por el splash.
- **Tamaños** (v1.2.x, antes → después): bundle 689 MB → 345 MB;
  instalador 310 MB → 170 MB.

## Pendiente

- Firma de código (Authenticode). Sin firmar, Windows SmartScreen
  muestra una advertencia en cada instalación.
