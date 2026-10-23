# Actualización automática de SAVI

**Locator:** `odd/tasks/actualizacion-automatica.md` · Engram `odd/actualizacion-automatica/tasks` (espejo al día, 2026-10-23).
**Rama de trabajo:** `staging`. U0 y U1 se hicieron en `feat/actualizacion-automatica` y ya están en `staging`.
**Spec:** [`docs/plataforma/09-actualizacion-automatica.md`](../../docs/plataforma/09-actualizacion-automatica.md), con las decisiones D1–D5 cerradas el 2026-10-21.
**Servidor de pruebas:** [`deploy/updates/servidor-de-pruebas.md`](../../deploy/updates/servidor-de-pruebas.md), en `https://savi-updates.danrodd.dev/savi`.

## Objetivo

Que SAVI se actualice solo, de forma confiable, en equipos de PYMEs con conexiones inestables y sin soporte técnico cerca:

- la persona acepta;
- SAVI baja la versión, la verifica y la instala;
- SAVI vuelve a abrir con la versión nueva, y si algo falla, vuelve con la anterior y lo dice.

## Principio que ordena el plan

**La primera versión que se instala a mano fija para siempre lo que el actualizador sabe hacer.** Un error en el propio mecanismo no se corrige actualizando: obliga a reinstalar equipo por equipo. Por eso:

- primero se construye todo lo que no se puede arreglar después (Fase 1);
- se compila una sola vez por versión;
- se prueba de verdad (Fase 2);
- recién entonces se sale a producción (Fase 3).

## Reglas de trabajo

- **Commits y push a `staging`:** sin pedir confirmación en cada paso, por pedido del usuario (2026-10-22). Un commit por tarea, con sus tests y sus docs.
- **Siguen necesitando OK explícito:**
  - correr `installer/build.ps1`, que consume muchos recursos;
  - crear o pushear tags (CLAUDE.md §10);
  - cambios en el servidor fuera de `/opt/savi-updates` y `/srv/savi-updates`;
  - pasar a `main`.
- Trabajo inline, sin subagentes, por preferencia del usuario.
- Textos visibles de usted (CLAUDE.md §14), y `test_usted_register.py` tiene que pasar.
- Las claves privadas de firma nunca entran al repositorio ni al servidor.
- **Cierre de cada tarea:**
  - backend: Ruff, formato y Pyright strict;
  - frontend: vue-tsc, Biome y Vitest;
  - los tests del módulo `updates` y de `test_publish_release.py`;
  - la prueba de punta a punta en local, `uv run --project backend python scripts/e2e-updates.py` (20 controles en Windows, sale con 0 si pasan). Cada tarea que cambie el flujo le suma sus controles.
- **Modo de pruebas:** TDD apagado, porque no hay configuración que lo active. Pruebas funcionales con `uv run pytest` y `pnpm vitest`.

## Estado

| Etapa | Estado |
|---|---|
| U0 y U1 (spec 09): manifiesto firmado, chequeo, aviso, descarga verificada, lanzamiento silencioso | Hecho y en `staging`. 11/11 de punta a punta en local. |
| Clave de firma principal | Generada; la pública está en `trust.py` (`59423c8`). |
| Servidor de pruebas | Funcionando y verificado desde afuera (`9623734`). |
| **Fase 1:** núcleo del actualizador | **Fase 1 completa:** B0, B1, B4, B2, B3 y B5 hechos. Falta cerrar con el repaso final y pasar a la Fase 2. |
| Fase 2: prueba real con instaladores compilados | **En curso (2026-10-23):** sin VM, en el equipo de desarrollo. `rc.1` instalada a mano (UAC aceptado al segundo intento; el primero se canceló, código 1223) y configurada con `UPDATE_URL`/`UPDATE_CHANNEL=beta`; SAVI consulta el servidor (404 mientras no haya nada en `beta`). Falta publicar `rc.2` y correr la matriz. |
| Fase 3: producción | Pendiente. |

---

## Fase 1. Núcleo del actualizador (local, sin compilar)

Orden: B0 → B1+B4 → B2 → B3 → B5. B1 y B4 van juntas porque el vigilante de B1 es quien sabe cómo terminó la instalación.

### B0. Versiones candidatas (`-rc.N`) para el canal `beta`

- [x] Hecho (2026-10-23)

**Evidencia:**
- 142 tests pasan (módulo `updates`, versionado, publicación y guarda de usted). Incluye el ciclo completo con un repositorio git descartable: `rc.1` → `rc.2` → final sobre el mismo commit.
- Ruff y formato limpios en lo tocado; Pyright strict con 0 errores.
- La prueba de punta a punta (`scripts/e2e-updates.py`) pasa 16 de 16: se sumaron 5 controles de candidatas.
- **Agregados que no estaban en el diseño:**
  - `describe()` prefiere la tag final cuando el commit tiene la final y una candidata, que es justo el caso de la final sobre `rc.2`.
  - `cmd_create` permite la final sobre un commit que solo tiene candidatas.
  - `promote` no pisa `stable` con una versión más vieja.
  - Las candidatas se numeran por versión base (`next_candidate_tag`).
- Deuda previa en archivos que no se tocaron: Ruff marca 6 avisos (`login.py`, `gemini_probe.py`, `debug_knowledge.py`) y varios archivos sin el formato de Ruff.

**Por qué.** Hoy solo se actualiza sola una versión `vX.Y.Z` exacta (`release.py:21`), y los tags solo se crean en `main` (`version.py:215`). Para probar hacen falta dos versiones, y eso obligaría a sacar dos versiones de producción. Con las candidatas, `beta` recibe `v1.4.0-rc.1`, `-rc.2`… desde `staging`, y `stable` nunca las ve.

**Diseño (decidido):**
- **Formato válido:** `vX.Y.Z` o `vX.Y.Z-rc.N`, con N ≥ 1. Un build de desarrollo, como `v1.4.0-rc.1-3-gabc1234` o `-sucio`, sigue sin actualizarse solo.
- **Orden:** `v1.4.0-rc.1 < v1.4.0-rc.2 < v1.4.0 < v1.4.1-rc.1`. `ReleaseVersion` suma `rc: int | None` y compara por `(major, minor, patch, es_final, rc)`.
- **Defensa en el cliente:** `HttpManifestSource` rechaza un manifiesto con versión rc si el canal es `stable`, con `InvalidManifestError`.
- **`scripts/version.py`:**
  - `--crear --rc` funciona solo en `staging`. Calcula la versión base con la propuesta de siempre, tomando la última versión final, y numera la rc siguiente.
  - `last_tag()` ignora las rc (`--exclude "*-rc.*"`).
  - `--numero` de un build rc devuelve la base `X.Y.Z`, sacada del tag en `HEAD` y no del último tag final, porque es lo que pide Inno en `VersionInfoVersion`.
- **`scripts/publish-release.py`:**
  - el nombre `SAVI-Setup-vX.Y.Z-rc.N.exe` es válido;
  - `build --channel stable` con una rc da error;
  - `promote` con una rc en `beta` da error: "una candidata no pasa a stable; se compila la versión final";
  - `reject_older_than_published` usa el orden nuevo.
- `build.ps1` no cambia: el nombre del instalador ya sale de la versión.

**Archivos:**
- `backend/app/modules/updates/domain/value_objects/release.py`
- `backend/app/modules/updates/infrastructure/http_source.py`
- `scripts/version.py`
- `scripts/publish-release.py`
- los tests de los tres
- `installer/README.md` (#versionado), CLAUDE.md §10 y la spec 09 §5

**Tests:**
- el orden completo con rc;
- `from_running` acepta una rc exacta y rechaza una rc con commits encima;
- `stable` rechaza un manifiesto rc;
- `version.py --crear --rc` fuera de `staging` da error;
- la numeración de las rc;
- `--numero` de una rc;
- `publish-release`: rc en `stable` da error, `promote` de una rc da error, y una rc menor que la publicada da error.

**Listo cuando:** pasan los tests y una simulación local con el script de punta a punta publica `rc.1` y `rc.2` en `beta`, detecta la actualización y no deja que nada rc llegue a `stable`.

### B1. Vigilante de la instalación

- [x] Hecho (2026-10-23), junto con B4.

**Evidencia:**
- **Backend:** 212 tests pasan (`updates`, publicación, versionado y guarda de usted). Pyright strict con 0 errores; Ruff limpio en lo tocado.
- **PowerShell de verdad:** `test_watcher.py` corre el vigilante real con un "instalador" `.cmd` y un "SAVI" HTTP falsos, en una carpeta con espacios y una `ñ`:
  - instalador que sale con 0: queda `finished`, no se toca SAVI;
  - sale con 4: queda `failed` con el código y SAVI se vuelve a abrir;
  - no arranca: `failed` sin código;
  - no termina: `timeout`;
  - SAVI lo abre el instalador unos segundos después: no se abre dos veces;
  - SAVI nunca vuelve tras una instalación buena: se abre.
- **Punta a punta:** `scripts/e2e-updates.py` pasa 20 de 20. Los 4 controles nuevos recorren coordinador → lanzador real → vigilante real → archivo → coordinador: un instalador que Windows no puede abrir deja `failed`, SAVI lo dice en usted ("…SAVI sigue en v1.4.0-rc.2.") y queda en el historial.
- **Frontend:** 328 tests pasan en toda la suite; vue-tsc y Biome limpios.

**Diferencias con el diseño:**
- **Argumentos:** el vigilante recibe los datos como argumentos de `-File` y no con el texto incrustado. Así no hay que escapar comillas, y una ruta con `'` o con `ñ` llega intacta.
- **Respaldo:** si PowerShell no puede arrancar el script (una política de grupo, por ejemplo), SAVI vuelve al lanzamiento directo de antes. Funciona igual, pero sin recuperación.
- **Puertos:** el vigilante busca a SAVI en su puerto y en los 19 siguientes, porque SAVI salta al siguiente si el suyo está ocupado.
- **`--no-browser`:** la bandera ya existía; el caso "SAVI ya estaba abierto" abría el navegador igual, y ahora la respeta. La entrada `[Run]` de `savi.iss` la usa.
- **Frontend:** además del tope de 15 minutos hay un botón **Dejar de esperar**, y si SAVI vuelve con la misma versión se sale de la pantalla de progreso, porque la instalación no se aplicó.
- **Limpieza (B4):** al instalar bien se borra el instalador descargado (unos 160 MB) y se guardan solo los últimos 5 logs de Inno.

**No se pudo probar sin una persona (queda en la Fase 2):**
- El cartel de UAC y su cancelación (`NativeErrorCode 1223`). El resto de la rama de error sí está probado.
- Que `ExitCode` se lea de un proceso elevado. Si no se pudiera, el vigilante lo trata como "terminó" y SAVI decide por la versión que corre.
- El `[Run]` real de Inno Setup, porque no se compila el instalador.

**Por qué.** Hoy SAVI lanza el instalador con `ShellExecuteW` (`launcher.py:49`), que no devuelve el proceso, y se cierra (`/CLOSEAPPLICATIONS`). Si la instalación falla, Inno revierte los archivos, pero la entrada de `[Run]` que vuelve a abrir SAVI solo corre si todo salió bien. Resultado: SAVI queda cerrado y la pantalla "Actualizando…" espera para siempre (`useUpdateStatus.ts:59`).

**Diseño (decidido):**
- **El vigilante es un script de PowerShell**, que viene en todo Windows 10 y 11. El texto vive en una constante de Python (`infrastructure/watcher.py`). En cada intento se escribe en `%LOCALAPPDATA%\SAVI\updates\watch-install.ps1`, fuera de `{app}`, porque la instalación reemplaza `{app}`.
- **El launcher.** `WindowsInstallerLauncher` deja `ShellExecuteW` y arranca el vigilante:
  - con `subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", ...])`;
  - con `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW`, así que sobrevive al cierre de SAVI.
  - El vigilante corre como el usuario, sin elevación, y pide la elevación solo para el instalador.
- **Parámetros del vigilante:**
  - `-Installer` y `-Arguments`: las banderas silenciosas y `/LOG` de este intento;
  - `-Elevate`: si la instalación es por máquina;
  - `-AppExe`: `{app}\SAVI.exe`, sacado de `sys.executable`;
  - `-HealthUrl`: la URL local de SAVI con el puerto real;
  - `-FromVersion` y `-ToVersion`;
  - `-ResultPath`;
  - `-AttemptId`: un UUID por intento.
- **Pasos del vigilante:**
  1. Escribe el resultado con `outcome: "started"`.
  2. Lanza `Start-Process -FilePath $Installer -ArgumentList $Arguments -PassThru`, con `-Verb RunAs` si corresponde, y espera hasta 30 minutos.
  3. Si la persona cancela el UAC, PowerShell tira una `Win32Exception` con `NativeErrorCode 1223`. Eso da `outcome: "cancelled"`; SAVI nunca se cerró.
  4. Con el código de salida de Inno (tabla de abajo): 0 da `installed` y cualquier otro da `failed`. Si se pasa el tiempo, `timeout`.
  5. Espera hasta 120 s a que `/health` responda. Si no responde, abre `SAVI.exe --no-browser`. Así SAVI vuelve siempre: con la versión nueva si salió bien, y con la vieja si Inno revirtió.
  6. Lee la versión que devuelve `/health` y escribe el resultado final: `exit_code`, `finished_at`, `relaunched` y `running_version`.
- **`SAVI.exe --no-browser`.** Bandera nueva en `launcher.py`: no abre el navegador, porque la pestaña que pidió la actualización se recarga sola.
  - La entrada `[Run]` silenciosa de `savi.iss` también la usa.
  - Si SAVI ya está corriendo, una segunda instancia lo detecta por `/health` (`_savi_already_running`) y no hace nada. Que la abran el `[Run]` y el vigilante a la vez no hace daño.
- **El coordinador.** En `INSTALLING`, mientras el backend siga vivo, lee el archivo de resultado cada 2 s con un puerto nuevo, `InstallResultReader`.
  - Si el resultado es `cancelled` o `failed` y SAVI no se cerró, pasa a `FAILED` con el mensaje que corresponda. Es el caso típico del UAC cancelado.
- **El frontend.**
  - `INSTALLING_MAX_MS` es de 15 minutos. Pasado ese tiempo, cambia a: "La actualización está tardando más de lo normal. Si SAVI no vuelve a abrir, ábralo desde el menú Inicio."
  - Al volver, lee el resultado de B4.

**Códigos de salida de Inno Setup que se distinguen** (documentación oficial de Inno, "Setup Exit Codes"):

| Código | Significado | Mensaje para la persona |
|---|---|---|
| 0 | Instalado | — |
| 1 | No pudo iniciar | "No se pudo iniciar la instalación." |
| 2 | Cancelado antes de instalar | "La instalación se canceló." |
| 3, 4 | Error fatal al preparar o al instalar; Inno revierte | "La instalación falló y SAVI volvió a la versión anterior." |
| 5 | Cancelado durante la instalación | "La instalación se canceló." |
| 7, 8 | No puede seguir o necesita reiniciar | "La instalación necesita reiniciar el equipo." / "…no pudo continuar." |
| otro | Desconocido | Mensaje genérico, con el código en el log |

**Archivos:**
- `infrastructure/watcher.py` (nuevo)
- `infrastructure/launcher.py`
- `domain/interfaces/ports.py`: `InstallResultReader`
- `application/coordinator.py`
- `infrastructure/provider.py`
- `backend/app/launcher.py`: `--no-browser`
- `installer/savi.iss`: `Parameters: "--no-browser"` en la entrada silenciosa
- el composable y las utilidades de `frontend/src/modules/updates/`
- la spec 09 §4

**Tests:**
- **Unitarios:** el coordinador ante `cancelled`, `failed` e `installed`; el armado de los argumentos de PowerShell; la tabla de códigos; el tope de tiempo del frontend.
- **Integración (solo en Windows, se saltea en otro sistema):** correr el vigilante real sin elevación, con un "instalador" falso (`cmd /c exit 4`) y un `/health` falso. Comprobar el resultado escrito, el `exit_code` y que relance un `SAVI.exe` falso cuando `/health` no responde.

**Listo cuando:** en este equipo, el vigilante real con un instalador falso que sale con 0, con 4 y con cancelación escribe el resultado correcto y relanza cuando corresponde. El frontend deja de esperar a los 15 minutos.

### B4. Registro del resultado de cada intento

- [x] Hecho (2026-10-23), junto con B1. La evidencia está en B1.

**Diferencia con el diseño:** el aviso "SAVI se actualizó a vX.Y.Z" no trae el enlace "Qué cambió". El estado no guarda las notas de la versión instalada, y guardarlas pedía sumarlas al archivo del vigilante. Si hace falta, se agrega después.

**Por qué.** Después de reiniciar, SAVI no sabe si la actualización salió bien. La persona necesita un aviso claro, y soporte necesita poder diagnosticar por teléfono.

**Diseño (decidido):**
- **Archivo de resultado.** Lo escribe el vigilante en `%LOCALAPPDATA%\SAVI\updates\last-install.json`, con estos campos: `attempt_id`, `from_version`, `to_version`, `started_at`, `finished_at`, `outcome`, `exit_code`, `relaunched`, `running_version` y `log`.
- **Log del instalador.** Uno por intento, en `install-<attempt_id>.log`. Se guardan los últimos 5.
- **Historial.** Al arrancar, el backend lee `last-install.json`. Si ese `attempt_id` no está en `history.jsonl`, calcula el resultado final y lo agrega, con un máximo de 50 entradas:
  - `installed` si la versión que corre es `to_version`;
  - `rolled_back` si salió con 0 pero corre otra versión;
  - el `outcome` del vigilante en los demás casos.
- **API.**
  - `GET /updates/status` suma `last_install`: `attempt_id`, `from_version`, `to_version`, `outcome`, `finished_at` y `message` en usted.
  - `GET /updates/history`, solo para administradores, devuelve el historial completo.
- **Aviso en el frontend**, una sola vez por `attempt_id`, que se recuerda en `localStorage`:
  - `installed`: "SAVI se actualizó a vX.Y.Z." y el enlace "Qué cambió".
  - `failed` o `rolled_back`: "La actualización a vX.Y.Z no se completó. SAVI sigue en vA.B.C." y el botón "Reintentar".
  - `cancelled`: no se avisa después del reinicio, porque ya se avisó en el momento.

**Archivos:**
- `infrastructure/install_history.py` (nuevo)
- `application/responses.py`
- `infrastructure/http/routes.py`
- `provider.py` (conciliación al arrancar)
- `frontend/src/modules/updates/`: tipos, servicio, `UpdateNotice.vue` y las utilidades
- la spec 09 §6

**Tests:**
- la conciliación en cada caso: `installed`, `rolled_back`, `failed`, `cancelled` y repetido;
- el tope de 50 entradas y de 5 logs;
- un archivo corrupto se ignora con un aviso en el log y SAVI arranca igual;
- `/updates/history` exige administrador;
- el aviso del frontend se muestra una sola vez.

**Listo cuando:** se ven en la interfaz los tres resultados de la prueba de B1, después de un reinicio simulado.

### B2. Varias claves de confianza

- [x] Hecho (2026-10-23)

**Evidencia:**
- `UPDATE_PUBLIC_KEYS` con principal y respaldo. La de respaldo está en `claves-savi/savi-updates-respaldo.pem (en la carpeta del usuario)` (generada con `keygen`, nunca leída ni copiada). El usuario confirmó que la guardó fuera de línea (2026-10-23).
- Comprobado con las claves reales: cada `.pem` firma algo que valida exactamente una clave de `trust.py`, y son distintas.
- 317 tests pasan en `updates`, publicación y guarda de usted (el único fallo, `test_logging_survives_migrations`, es previo). Prueba de punta a punta 20/20. Ruff y Pyright limpios.
- Diferencia: una clave mal formada se descarta con un aviso (no rompe el arranque), como pedía el diseño.
- Spec 09 §5 documenta la rotación.

**Por qué.** `trust.py` acepta una sola clave. Si se pierde o se filtra, todas las instalaciones quedan sin poder actualizarse y hay que reinstalarlas a mano. Una clave de respaldo solo sirve si viaja desde la primera versión.

**Diseño (decidido):**
- **En el código:** `UPDATE_PUBLIC_KEYS: tuple[str, ...]` con la principal y la de respaldo. Un manifiesto se acepta si lo valida cualquiera de las dos. El `.sig` sigue siendo una sola firma.
- **La clave de respaldo:**
  - Se genera ahora con `keygen` en `C:\Users\hikig\claves-savi\savi-updates-respaldo.pem`.
  - Se guarda **fuera de línea**, en un USB o en un gestor de contraseñas, y no se usa salvo que se pierda la principal.
- **Rotación** (documentada en la spec 09 §5):
  1. Se publica una versión que trae la clave vieja y la nueva, firmada con la vieja.
  2. La versión siguiente se firma con la nueva.
  3. Si se pierde la principal, se firma con la de respaldo y se rota igual.
- **`build_coordinator`** recibe la lista y se desactiva solo si ninguna clave es válida. `verify` usa la lista de `trust.py` por defecto.

**Archivos:**
- `infrastructure/trust.py`
- `infrastructure/signing.py`
- `infrastructure/provider.py`
- `scripts/publish-release.py`
- los tests
- la spec 09 §5

**Tests:**
- un manifiesto firmado con la principal se acepta;
- firmado con la de respaldo, también;
- firmado con una tercera clave, se rechaza;
- una clave mal formada en la lista no desactiva las demás.

**Listo cuando:** pasan los tests y la clave de respaldo existe, guardada fuera de línea. Que la guardó lo confirma el usuario.

### B3. Descarga que se retoma

- [x] Hecho (2026-10-23)

**Evidencia:**
- 10 tests nuevos con `httpx.MockTransport` (corte y `206`, servidor que ignora el rango, `416`, `Content-Range` equivocado, parcial de otra versión, hash inválido, reintentos agotados, instalador completo ya presente, progreso desde N). 327 tests pasan en total; el único fallo, `test_logging_survives_migrations`, es previo.
- **Contra el servidor real** (`savi-updates.danrodd.dev`, archivo de 40 MB subido como `savi-publish` y borrado después): Caddy contesta `206` con `Content-Range`; una descarga cortada a los 20 004 864 bytes retomó desde ahí y el SHA-256 final coincidió.
- Prueba de punta a punta 20/20. Hubo que ajustar el caso "instalador cambiado": ahora parte de un equipo sin descargas, porque un instalador ya bajado y verificado contra el manifiesto se reutiliza.
- Ruff y Pyright limpios. Spec 09 §4 documenta la retoma.

**Por qué.** El instalador pesa unos 160 MB. Hoy, si la conexión se corta, la descarga se borra y arranca de cero (`http_source.py:68`). En una PYME con internet inestable, esa es la falla más probable.

**Diseño (decidido):**
- **Junto al `.partial`** se guarda `.partial.json`, con `url`, `sha256` y `size`. Si coincide con el manifiesto actual, se retoma; si no, se borra.
- **Limpieza.** Se borra lo que no sea del manifiesto actual, nunca el parcial de la misma versión. Si ya está el archivo completo y verificado, no se descarga de nuevo.
- **Pedido con `Range: bytes=N-`:**
  - `206`: se verifica que `Content-Range` sea `bytes N-(size-1)/size` y se sigue escribiendo al final.
  - `200`: el servidor ignoró el rango; se vacía el parcial y se baja entero.
  - `416`: si el parcial ya tiene el tamaño completo, se pasa a verificar; si no, se borra y se reintenta.
- **Reintentos dentro del mismo intento:** 3, con esperas de 2, 5 y 15 s. Si se agotan, `FAILED` con: "Se perdió la conexión. Intente de nuevo: la descarga sigue desde donde quedó."
- **Integridad.** Si no coincide el SHA-256 o el tamaño, se borran el parcial y su `.json`.
- **Servidor.** Caddy (`file_server`) soporta rangos. `python -m http.server` no, así que la prueba local usa un servidor de prueba propio que sí los soporta.

**Archivos:**
- `infrastructure/http_source.py`
- `application/coordinator.py`: el progreso arranca en N
- los tests

**Tests**, con `httpx.MockTransport`:
- corte a la mitad y reintento con `206`;
- un servidor que ignora el rango y responde `200`;
- `416` con el archivo completo;
- un parcial de otra versión se descarta;
- un hash inválido borra todo;
- se agotan los reintentos;
- el progreso informado arranca en N.

**Listo cuando:** pasan los tests y, contra el servidor de pruebas real con un archivo de prueba grande, un corte forzado retoma con `206`.

### B5. Vista de Actualizaciones en Administración

- [x] Hecho (2026-10-23)

**Evidencia:**
- Backend: `GET /updates/history` ahora devuelve `{channel, server, records}` (3 tests nuevos: 403 sin ser administrador, con historial y sin actualizaciones). 330 tests de backend pasan; el único fallo, `test_logging_survives_migrations`, es previo.
- Frontend: 340 tests pasan en toda la suite (12 nuevos: la vista con historial vacío y con varias entradas, "Buscar ahora", "Actualizar ahora", sin actualizaciones activas, error de lectura, reglas puras y la ruta protegida). vue-tsc limpio; Biome limpio en lo tocado (los errores que quedan son de archivos que no toqué).
- Diferencia: "Actualizar ahora" y "Buscar ahora" avisan al aviso global con el evento `savi:update-status-changed`, para que muestre el avance sin esperar el ciclo de 15 min.
- **No visto en un navegador real:** la vista se probó con tests de componente y no contra un backend con historial. Queda para la Fase 2, donde habrá un historial de verdad.

**Por qué.** El administrador tiene que poder ver en qué está su instalación y forzar una comprobación sin esperar 6 horas, y soporte tiene que poder pedir el historial.

**Diseño (decidido):**
- **Ruta:** `/admin/actualizaciones`, con nombre `admin-updates`. Es hija de `/admin` en `frontend/src/router/index.ts` y entra en el menú de Administración.
- **La vista** vive en el módulo `updates`: `frontend/src/modules/updates/views/UpdatesAdminView.vue`.
- **Contenido:**
  - versión instalada, canal, servidor, última comprobación, versión disponible y notas;
  - el botón "Buscar ahora", que usa `POST /updates/check`, ya existente y solo para administradores;
  - el botón "Actualizar ahora", que es el mismo flujo del aviso;
  - una tabla de historial con fecha, versión de origen y de destino, resultado y detalle.
- **El canal no se cambia desde la interfaz:** queda en el `.env`, porque `beta` es solo para SEO (D5).
- **Backend:** `GET /updates/history` (B4) suma `channel` y `server`. Esos dos datos se muestran solo a administradores.

**Archivos:**
- `frontend/src/modules/updates/` (vista, servicio y tipos)
- `frontend/src/router/index.ts`
- el menú de Administración
- `infrastructure/http/routes.py`

**Tests:**
- la vista con un historial vacío y con varias entradas;
- "Buscar ahora" refresca el estado;
- alguien que no es administrador no entra.

**Listo cuando:** se ve y funciona contra el backend local con un historial simulado.

---

## Fase 2. Prueba real con instaladores compilados

**Requisitos (se deciden al llegar):**
- **Un Windows de prueba aparte.** Se recomienda una máquina virtual con instantánea, para repetir los casos desde cero. No conviene el equipo de desarrollo: comparte `%LOCALAPPDATA%\SAVI` y el puerto 31900 con el SAVI de desarrollo.
- **OK** para crear los tags rc y para compilar.

**Pasos:**
1. Tag `v1.4.0-rc.1` en `staging` (con OK), `build.ps1` (con OK) e instalación a mano en el Windows de prueba.
2. En el `.env` de esa instalación: `UPDATE_URL=https://savi-updates.danrodd.dev/savi` y `UPDATE_CHANNEL=beta`.
3. Tag `v1.4.0-rc.2` y `build.ps1`. Después, `publish-release.py build` + `upload` + `verify` en `beta`.
4. Correr la tabla de casos y anotar la evidencia en este documento.

| # | Caso | Cómo | Resultado esperado |
|---|---|---|---|
| 1 | Camino feliz | Aviso → "Actualizar y reiniciar" → aceptar el UAC | Vuelve a abrir en `rc.2` y la pestaña se recarga sola. Conversaciones y configuración intactas. Aviso "SAVI se actualizó". |

**Evidencia del caso 1 (2026-10-23, equipo de desarrollo, sin VM):** `rc.1` → `rc.2` publicada en `beta` desde Administración → Actualizaciones con "Actualizar ahora" y UAC aceptado. `last-install.json`: `step=finished`, `exit_code=0`, `running_version=v1.4.0-rc.2`. Historial: `installed`. Después del reinicio el coordinador dice `instalada v1.4.0-rc.2, publicada v1.4.0-rc.2 → up_to_date`. La persona vio la actualización terminar bien.

**Hallazgos del caso 1 (para corregir antes de `stable`):**
- Al cerrar el intento, "no se pudo borrar el instalador descargado": el archivo seguía bloqueado en ese instante (se pudo borrar a mano minutos después). Queda un instalador de 160 MB en `%LOCALAPPDATA%\SAVI\updates` hasta la próxima limpieza. Reintentar el borrado más tarde o al próximo arranque.
- El registro de `history.jsonl` quedó con `exit_code: null` aunque `last-install.json` trae `0`. Revisar de dónde lo toma `settle()`.
- Las notas de la versión se veían en Markdown crudo: corregido en `8184bc0`, llega con la próxima candidata.

**Evidencia de `rc.3` (2026-10-23):** `rc.2` → `rc.3` instalada con "Actualizar ahora". Historial `installed`, `last-install.json` con código 0. El instalador descargado ya no queda en `%LOCALAPPDATA%\SAVI\updates` y el log no avisa de ningún fallo de borrado (arreglo `c9d93b2`). El `exit_code: null` del historial es esperado: SAVI cierra el intento antes de que el vigilante escriba su último paso, y la versión que corre es la prueba de la instalación.
| 2 | UAC cancelado | Cancelar el cartel de UAC | SAVI sigue abierto con "Se canceló el permiso…". "Reintentar" funciona. En `last-install.json` queda `cancelled`. Es la primera vez que se prueba el código 1223 con un cartel real. |
| 3 | Corte de red | Desconectar la red de la VM a mitad de la descarga y reconectar | Al reintentar sigue desde donde quedó: en el log de Caddy, pedido con `206`. |
| 4 | Chat en curso | Actualizar con una respuesta del chat en curso | Espera a que termine el turno y recién ahí instala. |
| 5 | Instalador manipulado | Reemplazar el `.exe` en el servidor | Lo rechaza por SHA-256 y no lanza nada. |
| 6 | Navegador remoto | Abrir SAVI desde otro equipo de la red | Ve el aviso, pero no puede aplicar: "Avise a su área de sistemas". |
| 7 | Obligatoria | Volver a publicar `rc.2` con `--min-version v1.4.0-rc.2 --min-version-from now` | Diálogo de bloqueo que no se puede cerrar. |
| 8 | Instalación que falla | Si se consigue forzarla en la VM, por ejemplo con el disco lleno. Si no, queda cubierta por la prueba de integración de B1 | SAVI vuelve con la versión anterior y avisa que no se completó. |
| 9 | Usuario sin permisos de administrador | Iniciar sesión en Windows con una cuenta estándar | El UAC pide credenciales de administrador. Sin ellas, se comporta como el caso 2. |

**Listo cuando:** pasan los casos 1 a 7 y el 9, el 8 está cubierto (en la VM o por la prueba de integración), y la evidencia está anotada acá.

---

## Fase 3. Producción

1. **Decidir el dominio oficial y dónde se aloja**: el servidor de SEO o este de Hetzner. Va **antes** de compilar `v1.4.0`, porque queda grabado en `DEFAULT_UPDATE_URL` de `trust.py`. Las instalaciones de clientes no deben depender de `danrodd.dev`.
2. Desplegar `deploy/updates/` en ese servidor, con `setup.sh`, y verificar como en el servidor de pruebas.
3. Commit de `DEFAULT_UPDATE_URL`.
4. Confirmar que la clave de respaldo está guardada fuera de línea.
5. Pasar `staging` a `main` (con OK), crear el tag `v1.4.0` (con OK) y `build.ps1` (con OK).
6. `publish-release.py build --channel stable` + `upload` + `verify`.
7. Instalar a mano `v1.4.0` en cada cliente. Las v1.3.x no traen el actualizador.
8. Actualizar `docs/estado-y-pendientes.md` y la spec 09: estado "en producción".

---

## Decisiones pendientes

| Decisión | Cuándo hace falta |
|---|---|
| Equipo Windows de prueba: VM o PC aparte | Al empezar la Fase 2 |
| Dominio oficial y servidor de producción | Antes de compilar `v1.4.0` (Fase 3, paso 1) |

## Fuera de alcance (se suma después sin reinstalar)

- **U2:** instalación por usuario, sin UAC. Las instalaciones por máquina siguen siéndolo de todos modos.
- **U3:** salida gradual por porcentaje y reporte de la versión de cada equipo.
- **Firma de código del instalador** (D3).
- **Actualizaciones diferenciales**, que bajan solo lo que cambió.

---

## Historial

### U0 y U1 (2026-10-21)

- [x] **T1. Dominio de `updates`:** versión `vX.Y.Z` y su comparación, manifiesto y su validación, decisión de qué mostrar, rechazo de bajar de versión. 31 tests.
- [x] **T2. Firma y verificación:** Ed25519 del manifiesto, SHA-256 y tamaño del instalador. 12 tests.
- [x] **T3. `scripts/publish-release.py`:** `keygen`, `build`, `promote` y `upload`. 13 tests. Commits `8afe61d` y `9a24234`.
- [x] **T4. Chequeo periódico y endpoints.** Commit `fb3bf8a`.
  - `UpdateCoordinator`, `HttpManifestSource` y `HttpInstallerDownloader`, sin redirecciones y con tope de tamaño;
  - `WindowsInstallerLauncher`;
  - `GET /updates/status`, `POST /updates/apply` (solo desde 127.0.0.1) y `POST /updates/check` (administrador);
  - las variables `UPDATE_URL`, `UPDATE_CHANNEL` y `UPDATE_CHECK_INTERVAL_HOURS`.
- [x] **T5. Instalador:** entrada `[Run]` con `Check: WizardSilent` y `runasoriginaluser`. Commit `2cb93e1`, sin compilar.
- [x] **T6. Frontend:** barra de aviso, plazo, diálogo obligatorio y "Actualizando…". `Dialog.vue` suma `dismissible`. Commit `4ea209f`.
- [x] **T7. Punta a punta en local:** 11/11 controles contra un servidor HTTP real. Commit `a248079`.
  - Agregó `verify` y `DEFAULT_UPDATE_URL`.
  - Encontró y corrigió dos errores: la salida del script no era UTF-8 y el script dejaba publicar una versión anterior.
- Falla conocida, previa a todo esto: `test_logging_survives_migrations.py::test_log_still_works_after_ensure_schema`. La base local está en la revisión de `develop`.
- La descarga quedó en `%LOCALAPPDATA%\SAVI\updates\`, porque se puede escribir sin administrador, y no en `%ProgramData%`.

### Llegada a `staging` y servidor de pruebas

- **2026-10-21:** fast-forward de `staging` a la rama (`a248079`). 101 tests del backend, 315 del frontend y 11/11 de punta a punta.
- **2026-10-22: clave de firma principal.**
  - La privada está en `C:\Users\hikig\claves-savi\savi-updates.pem`, fuera del repositorio.
  - La pública está en `trust.py` (`59423c8`).
  - `DEFAULT_UPDATE_URL` sigue vacío a propósito. Las pruebas usan `UPDATE_URL`, que el instalador conserva al actualizar (`WriteEnvFile`).
- **2026-10-22: `deploy/updates/`** (`5b2125e`).
  - Solo Caddy. Dominio, puertos, interfaz y carpeta por variables, con dos modos: directo o detrás de un proxy.
  - `setup.sh` crea el `.env`, la carpeta y `savi-publish`, y valida.
  - La plantilla se llama `env.template` porque esta sesión no puede escribir `.env*`.
- **2026-10-23: servidor de pruebas en marcha** (`9623734`). Detalle en `deploy/updates/servidor-de-pruebas.md`.
  - Hetzner, Rocky 10.2, `savi-updates.danrodd.dev`, en modo directo.
  - `shortness` apagado.
  - El firewall "solo Cloudflare" cortaba la entrada y también la salida de los contenedores. Se corrigió y se deshabilitó.
  - Se quitó `ACME_EMAIL`. `setup.sh` etiqueta la carpeta para SELinux.
  - Verificado desde afuera: certificado válido, 404, 405 y 308 donde corresponde, y una subida real como `savi-publish`.
