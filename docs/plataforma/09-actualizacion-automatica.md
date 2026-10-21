# 09 — Actualización automática de SAVI

**Estado:** U0 y U1 implementados y probados en local en la rama `feat/actualizacion-automatica`. Falta desplegar en el servidor (sección 7, "Puesta en marcha"). Requisito antes de lanzar SEO SaaS.
**Depende de:** nada de SAVI Cloud. Cloud puede sumarse después (fase U4), pero no es requisito.
**Fecha:** 2026-10-16. Decisiones D1–D5 cerradas el 2026-10-21 (sección 10).

## 1. Problema

Hoy cada versión se instala a mano en cada equipo: hay que llevar el `.exe` de 160 MB, correr el asistente completo y elegir opciones. Con más clientes esto no escala, y además deja equipos en versiones viejas. Eso es peligroso cuando varias instalaciones comparten una base: una versión nueva puede migrar el esquema y romper a las viejas.

**Objetivo:** que SAVI avise sola cuando hay una versión nueva, que se actualice con un botón, al estilo de Zed o VS Code (descarga, reinicio y listo), y que pueda **obligar** a actualizar cuando una versión es crítica.

## 2. Cómo es SAVI hoy (lo que condiciona el diseño)

| Hecho | Dónde | Consecuencia |
|---|---|---|
| Se instala en `C:\Program Files\SAVI` con `PrivilegesRequired=admin` | `installer/savi.iss` | Reemplazar archivos exige permisos de administrador (UAC). Zed no tiene este problema porque se instala por usuario en `%LOCALAPPDATA%`. |
| Una actualización con `.env` existente no pregunta nada | `ShouldSkipPage` en `savi.iss` | El mismo instalador ya sirve en modo silencioso (`/VERYSILENT`) sin rehacer la configuración. |
| `CloseApplications=force` | `savi.iss` | El instalador cierra `SAVI.exe` solo. |
| "Iniciar SAVI ahora" lleva `skipifsilent` | `[Run]` en `savi.iss` | En modo silencioso **no** relanza SAVI: hay que agregar una entrada que sí lo haga. |
| La versión es el tag de git y viaja en `_version.py` | `scripts/version.py` | El backend ya sabe qué versión corre: alcanza con compararla con la publicada. |
| Las migraciones son solo hacia adelante | Alembic | No se ofrece bajar de versión. Un "rollback" es publicar una versión nueva que corrija. |

## 3. Decisión: servidor de actualizaciones

**No hace falta una aplicación en el servidor:** alcanza con archivos estáticos por HTTPS. No se necesita IIS ni un backend propio.

```
https://updates.<dominio-seo>/savi/
├── stable.json                  # manifiesto del canal estable
├── stable.json.sig              # firma del manifiesto
├── beta.json                    # (opcional) canal de pruebas
└── releases/
    └── SAVI-Setup-v1.4.0.exe
```

| Opción | A favor | En contra |
|---|---|---|
| **Linux + Caddy (elegida, D1)** | Es el mismo stack del despliegue de SAVI Master y Cloud (`deploy/`). HTTPS automático, barato, y se controla el acceso (por ejemplo, un token por cliente más adelante). | Hay que mantener un servidor (el mismo de M1.5). |
| Almacenamiento de objetos (Cloudflare R2, S3) con CDN | Cero mantenimiento, rápido en cualquier país, centavos al mes. | Es otro proveedor y otra cuenta. Controlar acceso por cliente es más incómodo. |
| GitHub Releases | Gratis y ya está integrado con los tags. | El repositorio es privado: descargar exige un token dentro de cada instalación. **Descartada.** |
| IIS en Windows Server | Sirve si el cliente lo exige. | No aporta nada sobre servir archivos estáticos y es más caro de operar. |

**Cómo se despliega (D1).** SEO ya tiene un servidor Linux, al que se entra por SSH con llave. Las actualizaciones son un dominio más en el mismo Caddy de SAVI Master (`deploy/master/Caddyfile`, en `develop`), sin aplicación detrás:

1. Un registro DNS `A` para `updates.<dominio-seo>` apunta al servidor. Caddy obtiene y renueva el certificado de Let's Encrypt.
2. Un bloque nuevo en el `Caddyfile` sirve la carpeta como archivos estáticos:
   ```
   {$UPDATES_DOMAIN} {
       import seguridad
       root * /srv/updates
       file_server
       @manifiesto path *.json *.sig
       header @manifiesto Cache-Control "no-cache"
       header /savi/releases/* Cache-Control "public, max-age=31536000, immutable"
   }
   ```
   En `docker-compose.yml`, la carpeta se monta de solo lectura: `./updates:/srv/updates:ro`. El manifiesto no se cachea, para que los equipos vean la versión nueva enseguida. Los instaladores no cambian nunca, así que se cachean para siempre.
3. Se publica con un usuario `savi-publish` y una llave SSH propia, que solo puede escribir en esa carpeta. Así, si la llave se filtra, no da acceso de administrador al servidor.

**Manifiesto** (`stable.json`):

```json
{
  "version": "v1.4.0",
  "published_at": "2026-11-02T15:00:00Z",
  "url": "https://updates.<dominio-seo>/savi/releases/SAVI-Setup-v1.4.0.exe",
  "sha256": "9f2c…",
  "size": 170082699,
  "min_version": "v1.3.1",
  "min_version_from": "2026-11-05T15:00:00Z",
  "notes": "Corrige la pantalla en blanco… (texto corto para el usuario, de usted)"
}
```

- `min_version`: toda instalación por debajo **debe** actualizar. Es la palanca para cambios críticos o de esquema.
- `min_version_from` (D4): desde cuándo se exige `min_version`. Antes de esa fecha, el aviso dice "Debe actualizar antes del 5 de noviembre" y SAVI sigue funcionando. Desde esa fecha, la pantalla se bloquea. El plazo se decide en cada versión: por defecto 72 h, y para un arreglo de seguridad se publica con la fecha actual, de modo que el bloqueo es inmediato.
- Entre `min_version` y `version`, la actualización es **recomendada**: aparece un aviso que se puede posponer.

## 4. Flujo en el equipo

```
SAVI (backend)                                   Servidor de actualizaciones
  │  al arrancar y cada 6 h ─── GET <canal>.json + .sig ───▶
  │  verifica la firma y compara con __version__
  │
  ├─ igual o mayor → nada
  ├─ menor, ≥ min_version → aviso "Hay una versión nueva" (posponible)
  ├─ menor que min_version, antes de min_version_from → aviso con la fecha límite
  └─ menor que min_version, desde min_version_from → pantalla bloqueante "Debe actualizar"
                │
     usuario pulsa "Actualizar y reiniciar"
                │
  descarga el .exe a %LOCALAPPDATA%\SAVI\updates\ ─── GET releases/… ──▶
  verifica SHA-256 y la firma Authenticode
  lanza el instalador en silencio y termina
                │
  instalador: cierra SAVI, reemplaza archivos, conserva .env, relanza SAVI
                │
  frontend: muestra "Actualizando…", espera /health con la versión nueva y recarga
```

**Modo de instalación silenciosa:**

```
SAVI-Setup-v1.4.0.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /LOG="%LOCALAPPDATA%\SAVI\updates\install.log"
```

Al ser una actualización, el asistente no muestra páginas: conserva `.env`, `ERP_CREDENTIALS_KEY` y los datos.

### El permiso de administrador

Es la diferencia de fondo con Zed. Se evaluaron dos caminos: lanzar el instalador con elevación (`runas`, con el cartel de UAC) o registrar un servicio de Windows `SAVIUpdate` como `LocalSystem` que instale sin UAC, al estilo de Chrome y Edge.

**Decisión (D2): instalador de dos modos y sin servicio.** Inno Setup lo permite con `PrivilegesRequired=lowest` y `PrivilegesRequiredOverridesAllowed=dialog`. SAVI se usa de dos maneras, y cada una tiene su modo:

| Caso | Instalación | Actualización |
|---|---|---|
| **PYME: SAVI en cada equipo** (la mayoría, modo por defecto) | Por usuario, en `%LOCALAPPDATA%`, sin administrador | Un clic, sin UAC. |
| **Empresa grande: SAVI en un servidor**, al que entran por la red | Por máquina, en Program Files, como hasta la v1.3.x | La hace el área de sistemas desde el servidor, aceptando el UAC. |

- **Modo servidor.** Quien entra por el navegador desde otro equipo no puede aceptar un UAC que aparece en el servidor. Por eso el botón **Actualizar** solo se ofrece cuando la sesión es local al servidor (`127.0.0.1`). Desde otro equipo, el aviso dice "Avise a su área de sistemas".
- **Instalaciones existentes.** Las v1.3.x son por máquina y siguen así: Inno Setup conserva el modo anterior al actualizar (`UsePreviousPrivileges`).
- **Claude Code.** Hoy escribe en `ProgramData` y en el PATH del sistema. En el modo por usuario pasa a rutas del usuario, o se vuelve opcional (ver la fase previa en `docs/estado-y-pendientes.md`).
- **Por qué no el servicio.** Con el modo por usuario, el caso normal no necesita administrador. El servicio sumaba el código más riesgoso de esta spec: un proceso `LocalSystem` que ejecuta instaladores y un canal local con permisos que proteger.

## 5. Seguridad (no negociable)

Un sistema de autoactualización es un canal para ejecutar código en todos los equipos: si se compromete, se compromete toda la flota.

1. **HTTPS** siempre, sin excepción para "redes internas".
2. **Manifiesto firmado** con una clave Ed25519. La clave pública va dentro de SAVI y la privada fuera del servidor, en el equipo de publicación o en un secreto. Así, aunque alguien tome el servidor, no puede publicar una versión.
3. **SHA-256** del instalador en el manifiesto, verificado antes de ejecutar.
4. **Firma de código Authenticode:** por ahora no (D3). La seguridad de la actualización no depende de ella: el SHA-256 y la firma Ed25519 del manifiesto impiden instalar un `.exe` ajeno. Sin firma, la primera instalación muestra el aviso de SmartScreen, como hasta la v1.3.x, y el UAC del modo servidor dice "Editor: desconocido". La descarga que hace SAVI no lleva la marca de "descargado de internet", así que en principio la actualización no dispara SmartScreen; hay que confirmarlo en U1.
5. **Nunca bajar de versión** aunque el manifiesto lo diga. Se rechaza `version < __version__`.
6. Todo intento queda en `savi.log`: chequeo, descarga, verificación, lanzamiento y resultado.

## 6. Experiencia de usuario (textos de usted)

- **Aviso recomendado:** una barra superior que dice "Hay una versión nueva de SAVI (v1.4.0)". Tiene dos botones, **Actualizar y reiniciar** y **Más tarde**, y un enlace "Qué cambió" que muestra `notes`. "Más tarde" lo oculta por 24 h.
- **Obligatoria, dentro del plazo:** la misma barra, con la fecha: "Debe actualizar SAVI antes del 5 de noviembre." No se puede ocultar por más de 24 h.
- **Obligatoria, vencido el plazo:** un diálogo sin cerrar: "Esta versión de SAVI ya no es compatible. Debe actualizar para seguir usándola." Un único botón: **Actualizar ahora**. En el modo servidor, desde otro equipo, el diálogo dice "Avise a su área de sistemas" y no tiene botón.
- **Durante la actualización:** una pantalla con progreso de descarga y luego "Reiniciando SAVI…". Cuando `/health` responde con la versión nueva, recarga sola.
- **Si falla:** un mensaje claro y el botón **Reintentar**. SAVI sigue funcionando con la versión actual, salvo que sea obligatoria.
- **Conversación en curso:** no actualizar a mitad de un turno. El botón espera a que terminen los turnos activos (ver `turn_registry`).
- **Quién la ve:** el aviso lo ve cualquiera. En el modo por usuario, cualquiera puede actualizar. En el modo servidor, solo desde el propio servidor y con permisos de administrador.

## 7. Publicación (lado SEO)

`scripts/publish-release.py` (nuevo):

1. Toma el `.exe` que generó `installer/build.ps1` para un tag `vX.Y.Z` y rechaza los builds "sucio".
2. Lo firma con Authenticode si algún día hay certificado (D3). Hoy, no.
3. Calcula el SHA-256 y arma el manifiesto con `notes` (tomadas del tag anotado) y `min_version`. `min_version` se mantiene igual salvo que se indique `--min-version`. Cuando cambia, `min_version_from` toma por defecto 72 h desde la publicación. `--min-version-from now` lo vuelve inmediato.
4. Firma el manifiesto con Ed25519 en el equipo de publicación. La clave privada nunca va al servidor.
5. Sube por SSH, con el usuario `savi-publish`, el `.exe` y después el manifiesto, en ese orden. Si se subiera primero el manifiesto, apuntaría a un archivo que todavía no existe. El manifiesto se sube con otro nombre y se renombra al final, para que ningún equipo lea un archivo a medio escribir.
6. Permite publicar primero a `beta.json` y después promover a `stable.json`.

Publicar sigue siendo una decisión humana, igual que crear el tag: el script no corre solo en CI. Además:

- **Un canal nunca retrocede:** el script se niega a publicar una versión menor que la que el canal ya tiene. Volver a publicar la misma versión, por ejemplo para corregir las notas, sí se permite.
- **`verify`** hace lo mismo que una instalación, con el mismo código del backend: lee el manifiesto publicado, verifica la firma, descarga el instalador y verifica el SHA-256.

### Puesta en marcha (una sola vez)

U0 y U1 están escritos y probados en local. En el servidor solo queda desplegar y probar:

1. **Clave.** En el equipo de publicación, fuera del repositorio:
   `uv run --project backend python scripts/publish-release.py keygen --out <ruta-segura>/savi-updates.pem`.
   La clave privada se respalda en un lugar seguro: si se pierde, las instalaciones no aceptan más versiones hasta reinstalar a mano una que traiga la clave nueva.
2. **Datos de confianza.** Se pegan la clave pública y la URL oficial (`https://updates.<dominio-seo>/savi`) en `backend/app/modules/updates/infrastructure/trust.py`, y se commitean.
3. **DNS.** Un registro `A` para `updates.<dominio-seo>` que apunte al servidor.
4. **Caddy.** El bloque `{$UPDATES_DOMAIN}` de la sección 3, en `deploy/master/Caddyfile`, que hoy existe solo en `develop`. Además, `UPDATES_DOMAIN` en el `.env` del despliegue y el volumen `./updates:/srv/updates:ro` en `docker-compose.yml`.
5. **Usuario de publicación.** `savi-publish` en el servidor, con su llave SSH, y permiso de escritura solo sobre la carpeta `updates/`.
6. **Primera versión con actualización automática.** Se compila el instalador del tag y se instala **a mano** en cada equipo. Las v1.3.x no traen el módulo `updates`, así que no pueden enterarse solas.
7. **Prueba.** Se publica en `beta`, con `build`, `upload` y `verify`. Un equipo de SEO con `UPDATE_CHANNEL=beta` en el `.env` tiene que mostrar el aviso, actualizar con un clic y volver a abrir con la versión nueva. Si funciona, se pasa a estable con `promote` y `upload --channel stable`.

**Probar en local, sin servidor.** Se arma la carpeta con `build --base-url http://127.0.0.1:8765`, se sirve con `python -m http.server 8765 --bind 127.0.0.1 --directory installer/output/updates` y se pone `UPDATE_URL=http://127.0.0.1:8765` en el `.env`. Solo `127.0.0.1` y `localhost` admiten HTTP sin TLS.

**Variables del `.env` de SAVI:**

| Variable | Por defecto | Para qué |
|---|---|---|
| `UPDATE_URL` | vacío, que usa la URL oficial de `trust.py` | Cambiar el servidor, por ejemplo para probar en local. |
| `UPDATE_CHANNEL` | `stable` | `beta` solo en equipos de SEO (D5). |
| `UPDATE_CHECK_INTERVAL_HOURS` | `6` | Cada cuánto se lee el manifiesto. |

## 8. Fases

| Fase | Contenido | Criterio de hecho |
|---|---|---|
| **U0 Servidor y publicación** | Bloque `{$UPDATES_DOMAIN}` en el Caddy de SAVI Master. `publish-release.py` con manifiesto, SHA-256, firma Ed25519 y subida por SSH. | `stable.json` publicado y verificable desde un equipo de prueba. |
| **U1 Aviso y actualización** | Módulo `updates` en el backend (chequeo, verificación, descarga, lanzamiento). Canal `UPDATE_CHANNEL` en el `.env`. Barra de aviso, plazo y diálogo obligatorio en el frontend. Entrada `[Run]` que relanza SAVI en modo silencioso. Bloqueo por `min_version` y `min_version_from`. En esta fase, las instalaciones siguen siendo por máquina y actualizan con UAC. | Un equipo con v1.4.0 pasa a v1.4.1 con un clic y un UAC, sin perder la configuración ni las conversaciones. Tests: comparación de versiones, plazo antes y después de la fecha, firma inválida rechazada, hash inválido rechazado, intento de bajar de versión rechazado. |
| **U2 Instalador de dos modos** | `PrivilegesRequired=lowest` con diálogo para elegir el modo. Rutas de usuario para los datos y para Claude Code. Botón de actualizar solo local en el modo servidor. | Una cuenta sin permisos de administrador instala y actualiza sola. Una instalación v1.3.x por máquina actualiza sin cambiar de modo. |
| **U3 Despliegue controlado** | Despliegue por porcentaje (un hash del id de instalación decide si le toca). Reporte de la versión instalada por equipo, aunque sea solo en el log. | Una versión llega primero al 10 % y se puede frenar quitándola del manifiesto. |
| **U4 (opcional) Con SAVI Cloud** | Cloud ya recibe la versión de cada instancia por el heartbeat. Puede mostrar quién está atrasado y fijar `min_version` por cliente. | La consola muestra la versión de la flota. No es requisito de U0 a U3. |

## 9. Fuera de alcance

- **Actualizaciones diferenciales (deltas):** 160 MB por versión es aceptable. Los deltas agregan mucha complejidad y su ventaja es chica.
- **Actualizar solo el frontend:** todo viaja en un único `.exe` de PyInstaller. Separarlo complica el versionado sin un beneficio real hoy.
- **Bajar de versión:** las migraciones son solo hacia adelante.

## 10. Decisiones (cerradas el 2026-10-21)

- **D1. Dónde se aloja:** en el servidor Linux de SEO, como un dominio más del Caddy de SAVI Master (sección 3). Se descartó R2 porque el servidor ya existe. Falta el acceso SSH para desplegar.
- **D2. Permisos de administrador:** instalador de dos modos, por usuario por defecto y por máquina para servidores. **No se construye el servicio `SAVIUpdate`** (sección 4).
- **D3. Certificado de firma de código:** no se compra por ahora. Se compra si un cliente lo exige o su política bloquea ejecutables sin firma, si aparecen falsos positivos de antivirus o si los avisos de SmartScreen cuestan ventas. En ese caso:
  - **Tipo:** un OV con la clave en un HSM en la nube del proveedor, a nombre de SEO Group, con MFA y acceso para dos personas.
  - **EV, descartado:** desde 2024 Microsoft lo trata igual que a un OV ante SmartScreen.
  - **Azure Artifact Signing, descartado:** no se ofrece a organizaciones de Colombia (dato a confirmar en una fuente oficial).
- **D4. Plazo de la actualización obligatoria:** se decide en cada versión con `min_version_from`. Por defecto son 72 h; para un arreglo de seguridad el bloqueo es inmediato.
- **D5. Canal:** `UPDATE_CHANNEL` en el `.env`, con `stable` por defecto, desde U1. En `beta` va solo SEO interno. La asignación por cliente desde la consola de Cloud queda para U4.
