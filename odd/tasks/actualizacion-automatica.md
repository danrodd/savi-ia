# Actualización automática de SAVI (U0 + U1)

**Locator:** `odd/tasks/actualizacion-automatica.md` · Engram `odd/actualizacion-automatica/tasks` (espejo pendiente: Engram no está disponible en esta sesión).
**Rama:** `feat/actualizacion-automatica` (desde `staging` en `b7e59d1`).
**Spec:** [`docs/plataforma/09-actualizacion-automatica.md`](../../docs/plataforma/09-actualizacion-automatica.md), decisiones D1–D5 cerradas el 2026-10-21.

## Objetivo

Dejar escrito y probado en local todo U0 y U1, de modo que al final solo falte desplegar el bloque de Caddy en el servidor Linux y probar contra él.

## Restricciones

- No correr `installer/build.ps1` (la compilación consume demasiados recursos). Los cambios de `savi.iss` se revisan, no se compilan.
- Sin acceso al servidor Linux hasta que el usuario lo autorice con destino, usuario y llave.
- Commits solo con OK explícito del usuario (CLAUDE.md §12). Sin push sin OK.
- Trabajo inline, sin subagentes (preferencia del usuario).
- Textos visibles de usted (CLAUDE.md §14). El test `test_usted_register.py` tiene que pasar.
- La clave privada Ed25519 nunca entra al repositorio.

## Modo de pruebas

TDD: apagado (no hay configuración que lo active). Pruebas funcionales con `uv run pytest` (backend) y `pnpm vitest` (frontend), más Ruff y Pyright strict.

## Tareas

- [x] **T1. Dominio de `updates`** (inline): versión `vX.Y.Z` y su comparación; manifiesto y su validación; decisión (`none`, `recommended`, `required_pending`, `required_blocked`); rechazo de bajar de versión. Tests unitarios.
- [x] **T2. Firma y verificación** (inline): verificación Ed25519 del manifiesto y SHA-256 del instalador en infraestructura. Clave pública incrustada; si está vacía, el chequeo queda desactivado con un aviso en el log. Tests con un par de claves generado en el test.
- [x] **T3. `scripts/publish-release.py`** (inline): `keygen`, armado del manifiesto con `min_version_from` (72 h por defecto, `now`), firma, `--out` local para pruebas y subida por SSH (`.exe` primero, manifiesto con nombre temporal y renombre). Tests del armado y la firma.
- [x] **T4. Chequeo periódico y endpoints** (inline): `UPDATE_URL` y `UPDATE_CHANNEL` en Settings; chequeo al arrancar y cada 6 h; `GET /updates/status`; `POST /updates/apply` (descarga, verificación, espera de turnos, lanzamiento silencioso). Modo servidor: aplicar solo desde `127.0.0.1`. Tests.
- [ ] **T5. Instalador** (inline): entrada `[Run]` que relanza SAVI en modo silencioso. Sin compilar.
- [ ] **T6. Frontend** (inline): barra de aviso, plazo, diálogo obligatorio y pantalla "Actualizando…" que espera `/health`. Tests.
- [ ] **T7. Prueba de punta a punta en local**: manifiesto firmado servido con `python -m http.server`, SAVI en desarrollo detecta, verifica y rechaza manipulaciones. Documentar los pasos de despliegue que quedan para el servidor.

## Criterios de aceptación

- Una instalación detecta una versión nueva desde un manifiesto firmado y muestra el aviso correcto según `min_version` y `min_version_from`.
- Firma inválida, hash inválido y versión menor se rechazan y quedan en `savi.log`.
- En desarrollo (versión que no es un tag exacto) el chequeo no se activa.
- Ruff, Pyright strict y los tests del backend y del frontend pasan.

## Progreso

- 2026-10-21: rama creada, exploración hecha. Ruta: todo inline por preferencia del usuario (sin subagentes).
- T1: `app/modules/updates/domain/` (versión, manifiesto, `decide`). 31 tests.
- T2: `infrastructure/signing.py` (Ed25519 + SHA-256 y tamaño). 12 tests; 43 en `tests/unit/modules/updates`.
- T3: `scripts/publish-release.py` (`keygen`, `build`, `promote`, `upload`). Valida y verifica con el código del backend. 13 tests en `tests/unit/infrastructure/test_publish_release.py`.
- Commits T1–T3: `8afe61d` (dominio y firma), `9a24234` (script de publicación).
- T4: `UpdateCoordinator` (aplicación); `HttpManifestSource` y `HttpInstallerDownloader` (httpx, sin redirecciones, tope de tamaño); `WindowsInstallerLauncher` (ShellExecute con `runas` si SAVI está en Program Files); `provider.py` (chequeo al arrancar y cada `UPDATE_CHECK_INTERVAL_HOURS`); rutas `GET /updates/status`, `POST /updates/apply` (solo desde 127.0.0.1) y `POST /updates/check` (admin). Settings `UPDATE_URL`, `UPDATE_CHANNEL` y `UPDATE_CHECK_INTERVAL_HOURS`. La clave pública queda vacía en `trust.py` hasta correr `keygen`.
- Verificación T4: 74 tests en `tests/unit/modules/updates`, 99 sumando publicación y registro de usted. Ruff, formato y Pyright strict sin errores.
- Falla conocida, previa a esta rama: `test_logging_survives_migrations.py::test_log_still_works_after_ensure_schema` también falla en la base (BD local en la revisión de `develop`).
- La descarga queda en `%LOCALAPPDATA%\SAVI\updates\` (`data_dir()`), no en `%ProgramData%` como decía la spec, porque es escribible sin administrador. Ajustar la spec en T7.
- `.env.example` no se tocó (sin permiso de lectura en esta sesión): documentar las variables en T7.
