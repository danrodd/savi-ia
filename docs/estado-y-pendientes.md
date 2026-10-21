# Estado del proyecto y pendientes

**Actualizado:** 2026-10-20. Este archivo hay que actualizarlo cada vez que cambie el estado: se publica una versión, se cierra un pendiente o se toma una decisión.

## Ramas

| Rama | Commit | Qué es |
|---|---|---|
| `main` | `b9b6a0e` | **Producción.** Tags `v1.3.0`, `v1.3.1` y `v1.3.2`. |
| `staging` | `b9b6a0e` | Rama de preparación de producción. Hoy coincide con `main`. |
| `develop` | `bdd1ee6` | SAVI Cloud, la UI compartida (`packages/ui`) y las mejoras de la consola. **No va a producción todavía.** Desde el 2026-10-20 incluye todo `staging` (merge `d0251d3`). |

**Flujo:**

1. Los cambios nuevos se hacen en `staging`.
2. Se prueban.
3. `main` avanza hasta `staging` (fast-forward).
4. Se crea el tag con `scripts/version.py --crear`, que exige estar en `main`.

De `develop` no se lleva nada a producción sin una decisión explícita. Hasta ahora solo se trajeron, por cherry-pick, tres arreglos del frontend de SAVI sin relación con Cloud: `2cb7d5a`, `d0f1c12` y el `theme-init.js` de `562dd4b`.

> Después de traer código de `develop` hay que correr `backend/tests/unit/test_usted_register.py`: así se coló un "Probá de nuevo" en la v1.3.1, que se corrigió en la v1.3.2.

## Versión en producción: v1.3.2

Tag `v1.3.2` en `b9b6a0e`, publicado en `origin` el 2026-10-20. **El instalador todavía no está compilado**: falta correr `.\installer\build.ps1` desde `main`. La compilación es pesada, así que conviene hacerla con el equipo libre.

La v1.3.2 solo cambia textos respecto de la v1.3.1:

- "Probá de nuevo…" pasa a "Intente de nuevo…".
- "Volver a configurar" pasa a "Modificar la configuración" en el backend, el launcher, el instalador y el manual 3.
- Suma la documentación del incidente y la spec 09.

Antes del tag pasaron `test_usted_register.py` y `test_settings_hardening.py`. La suite completa no se corrió.

### v1.3.1

Instalador: `installer/output/SAVI-Setup-v1.3.1.exe` (162 MB, no se versiona).

- **Trato de usted.** Español colombiano formal en la interfaz, el asistente (`system_prompt.py`), los mensajes del backend, el instalador y los manuales.
  - Regla en `CLAUDE.md`, sección 14.
  - El test guardián `test_usted_register.py` detecta voseo, pero no tuteo.
- **Instalador: "Modificar la configuración".** Las páginas traen los datos del `.env` actual, así se cambia solo lo necesario, por ejemplo el nombre de la base de SAVI. Conserva `ERP_CREDENTIALS_KEY` y `SAVI_ADMIN_LOGINS`.
- **Pantalla en blanco por el registro de Windows.** El frontend se sirve con tipos fijos (`_SPA_MEDIA_TYPES` en `backend/app/main.py`). Detalle en [docs/incidentes](incidentes/2026-10-16-pantalla-en-blanco-y-credencial-ilegible.md).
- **Frontend:**
  - Vuelve al login cuando la sesión guardada venció.
  - Muestra un error legible si el servidor no responde JSON.
  - Aplica el modo oscuro antes del primer pintado.

## SAVI Cloud (solo en `develop`)

- **Consola rehecha** con `@savi/ui` (spec [08](plataforma/08-ui-compartida-consola.md), disponible en `develop`), con contraste accesible verificado con axe.
- **Cuatro fases de mejoras de UX:**

| Commit | Contenido |
|---|---|
| `1e29e34` | Paginación de clientes, pagos con confirmación, endpoint de personas del cliente y alertas legibles |
| `c64e281` | Contadores en pestañas, insignia de alertas y filtros guardados en la URL |
| `0a730d4` | Puesta en marcha del cliente, vinculación paso a paso y estados vacíos con acción |
| `0edcff4` | Seis pestañas (las rutas viejas redirigen), tarjetas en móvil, alertas en lote e indicadores alineados |

## Pendientes, por prioridad

1. **Login que falla con contraseñas que tienen puntos.** Pasa en el ERP `tecnologicas_sas`.
   - Lo que hace SAVI: busca en `Seguridad.Usuario` por `UPPER(codigo)`, calcula el MD5 en UTF-8 de la contraseña y lo compara con `clave`; exige además `estado = true`. No recorta ni transforma la contraseña.
   - Ya se descartó la codificación, porque el punto es ASCII.
   - **SAVI quedó descartado (2026-10-20).** En la copia local de `farmacias_similares` se creó por SQL `PRUEBASAVI` / `prueba.123` (id 69, sin administrador, con `md5()`). `POST /auth/login` responde 200, también con el usuario en minúsculas, y 401 con la clave sin punto. El frontend manda la contraseña sin tocarla (`LoginView.vue`). Las 64 claves de esa base son MD5 en hex minúscula de 32 caracteres.
   - Esa prueba no dice cómo guarda la clave el ERP, porque el hash lo calculó SAVI. El problema está en lo que Sisfec escribe en `clave` cuando la contraseña lleva puntos.
   - Hipótesis sin verificar: el separador decimal en Colombia es la coma, y si la clave se tipeó con el punto del teclado numérico, el control del ERP podría haber guardado una `,`.
   - Siguiente paso, **bloqueado hasta tener acceso a Sisfec contra `tecnologicas_sas`**: crear desde la pantalla de usuarios del ERP `PRUEBASAVI` / `prueba.123`, escribiendo el punto con la tecla normal, y comparar su `clave` con `md5('prueba.123')` y con sus variantes. Nunca se leen contraseñas reales.
   - Lo que resulte va en la v1.3.3.
   - Para borrar el usuario de prueba local: `DELETE FROM "Seguridad"."Usuario" WHERE codigo = 'PRUEBASAVI';`
2. **Suite completa del backend sobre `staging`** (unos 9 minutos). La última corrida se cortó al 60 % por falta de memoria, sin fallos hasta ahí. Hay que correrla con los servidores de desarrollo apagados.
   - Dos tests de migración fallan en desarrollo porque la base local está en la revisión `f1a6c3d8e2b4` de `develop`. No es un bug.
3. **Compilar el instalador de la v1.3.2** desde `main`, con el equipo libre.
4. ~~Llevar `staging` a `develop` y pasar Cloud a usted.~~ **Hecho el 2026-10-20.**
   - Merge `d0251d3`. Hubo 5 conflictos, todos de textos o del README del instalador.
   - `0faf81e` pasa a usted, con voseo y tuteo corregidos:
     - la consola de Cloud (`cloud/`);
     - `packages/ui`;
     - la verificación en dos pasos;
     - la vinculación con Cloud;
     - la página de Cloud del instalador.
   - `bdd1ee6`: el test guardián también revisa `cloud/backend/app`, `cloud/frontend/src` y `packages/ui/src`, y suma formas que se le escapaban.
   - El test sigue sin detectar el tuteo, así que esa revisión es manual.
   - Verificado:
     - **Backend:** pyright strict sin errores y 676 tests unitarios de los módulos tocados.
     - **Frontend:** 338 tests de SAVI, 212 de Cloud y 51 de `packages/ui`.
     - **Backend de Cloud:** 163 tests.
     - No se corrió la suite completa.
   - Deuda heredada de `develop`, sin tocar: 9 avisos de Ruff y unos 120 archivos sin el formato de Ruff.
5. **Actualización automática** ([spec 09](plataforma/09-actualizacion-automatica.md)). Es un requisito antes del SaaS.
   - **Decisiones D1–D5 cerradas el 2026-10-21** (sección 10 de la spec):
     - **D1:** en el servidor Linux de SEO, como un dominio más del Caddy de SAVI Master.
     - **D2:** instalador de dos modos y sin servicio `SAVIUpdate`.
     - **D3:** sin certificado de firma por ahora.
     - **D4:** el plazo se decide en cada versión, 72 h por defecto.
     - **D5:** `UPDATE_CHANNEL`, con `beta` solo para SEO.
   - **U0 y U1 hechos en `feat/actualizacion-automatica`** (2026-10-21), sin mergear todavía a `staging`. Seguimiento en `odd/tasks/actualizacion-automatica.md`.
     - Backend: módulo `updates`, con firma Ed25519, SHA-256, el plazo de `min_version_from`, chequeo cada 6 h y los endpoints `/updates/*`.
     - Frontend: barra de aviso, bloqueo y progreso.
     - `scripts/publish-release.py`, con `keygen`, `build`, `promote`, `upload` y `verify`.
     - Instalador: SAVI vuelve a abrir solo después de una instalación silenciosa.
     - Probado de punta a punta contra un servidor HTTP local. No se compiló el instalador.
   - Para desplegar falta el acceso SSH con llave al servidor, que tiene que conseguir el usuario. Los pasos están en la spec 09, sección 7, "Puesta en marcha".
   - Falta incorporar a la spec una fase previa propuesta. El modo por usuario de D2 cubre en parte el instalador sin administrador:
     - Claude con clave de API directo por la API. Hoy todo Claude pasa por `claude-agent-sdk`/`claude.exe`.
     - Instalador por usuario sin administrador por defecto (`PrivilegesRequired=lowest` + diálogo).
     - Claude Code opcional, instalable desde Administración → Proveedores de IA.
     - Git, Node.js y el CLI solo existen para Claude Code.
6. **Cloud:**
   - M1.5: Docker en un servidor Linux real con dominio.
   - M5-B: gateway, diferido.
   - Migrar pantallas de SAVI a los componentes de `@savi/ui`.
7. **Menores:**
   - Las capturas de los manuales muestran la interfaz anterior.
   - Avisos de Biome preexistentes en `permisos` y `chat`.
   - `frontend/pnpm-lock.yaml` está versionado.
8. **Antes de tener clientes:** revisión legal (P8) y las decisiones D1–D6 de [07-savi-master.md](plataforma/07-savi-master.md), que solo existe en `develop`.

## Referencias rápidas

- **Ingreso:** con el usuario del ERP (`codigo`). `USUARIO@CODIGO` solo hace falta para bases adicionales.
- **Administrador de la instalación:**
  - Con una sola base: el administrador del ERP.
  - Con varias bases: quien figure en `SAVI_ADMIN_LOGINS` o el administrador de la base por defecto.
- **Logs del equipo:**
  - `%LOCALAPPDATA%\SAVI\savi.log`.
  - Diagnóstico de la instalación: `C:\ProgramData\SAVI\diagnostico-instalacion.txt`.
  - Más detalle en [installer/README.md](../installer/README.md#diagnóstico).
- **Varias instalaciones con la misma base de SAVI:** necesitan la misma `ERP_CREDENTIALS_KEY`, o cada una su propia base.
