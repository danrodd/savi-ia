# Estado del proyecto y pendientes

**Actualizado:** 2026-10-20. Este archivo hay que actualizarlo cada vez que cambie el estado: se publica una versión, se cierra un pendiente o se toma una decisión.

## Ramas

| Rama | Commit | Qué es |
|---|---|---|
| `main` | `57de402` | **Producción.** Tags `v1.3.0` y `v1.3.1`. |
| `staging` | `57de402` | Rama de preparación de producción. Hoy coincide con `main`. |
| `develop` | `0edcff4` | SAVI Cloud, la UI compartida (`packages/ui`) y las mejoras de la consola. **No va a producción todavía.** |

**Flujo:**

1. Los cambios nuevos se hacen en `staging`.
2. Se prueban.
3. `main` avanza hasta `staging` (fast-forward).
4. Se crea el tag con `scripts/version.py --crear`, que exige estar en `main`.

De `develop` no se lleva nada a producción sin una decisión explícita. Hasta ahora solo se trajeron, por cherry-pick, tres arreglos del frontend de SAVI sin relación con Cloud: `2cb7d5a`, `d0f1c12` y el `theme-init.js` de `562dd4b`.

> Después de traer código de `develop` hay que correr `backend/tests/unit/test_usted_register.py`: así se coló un "Probá de nuevo" en la v1.3.1.

## Versión en producción: v1.3.1

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

En `main` después del tag, todavía sin versión publicada:

- Documentación del incidente.
- La opción "Modificar la configuración" con ese nombre también en los mensajes y en el manual 3.
- El aviso "Intente de nuevo…", corregido desde "Probá de nuevo…".
- La spec 09.

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
   - Siguiente paso: crear en ese ERP un usuario de prueba (`PRUEBASAVI`, contraseña `prueba.123`) y comparar su `clave` con el MD5 local. Nunca se leen contraseñas reales.
2. **Suite completa del backend sobre `staging`** (unos 9 minutos). La última corrida se cortó al 60 % por falta de memoria, sin fallos hasta ahí. Hay que correrla con los servidores de desarrollo apagados.
   - Dos tests de migración fallan en desarrollo porque la base local está en la revisión `f1a6c3d8e2b4` de `develop`. No es un bug.
3. **v1.3.2:** el arreglo del voseo y lo que resulte del punto 1.
4. **Llevar `staging` a `develop`** (11 commits; se esperan conflictos en textos) y pasar a usted la consola de Cloud y su documentación. Hoy tiene voseo viejo y "tú".
5. **Actualización automática** ([spec 09](plataforma/09-actualizacion-automatica.md)). Es un requisito antes del SaaS.
   - Decisiones abiertas D1–D5: dónde se aloja, cuándo pasar al servicio sin UAC, el certificado de firma de código, el plazo de la actualización obligatoria y el canal por cliente.
   - Falta incorporar a la spec una fase previa propuesta:
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
