# 09 — Actualización automática de SAVI

**Estado:** pendiente, requisito antes de lanzar SEO SaaS.
**Depende de:** nada de SAVI Cloud. Cloud puede sumarse después (fase U4), pero no es requisito.
**Fecha:** 2026-10-16.

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
| **Linux + Caddy (recomendada)** | Es el mismo stack del despliegue de SAVI Master y Cloud (`deploy/`). HTTPS automático, barato, y se controla el acceso (por ejemplo, un token por cliente más adelante). | Hay que mantener un servidor (el mismo de M1.5). |
| Almacenamiento de objetos (Cloudflare R2, S3) con CDN | Cero mantenimiento, rápido en cualquier país, centavos al mes. | Es otro proveedor y otra cuenta. Controlar acceso por cliente es más incómodo. |
| GitHub Releases | Gratis y ya está integrado con los tags. | El repositorio es privado: descargar exige un token dentro de cada instalación. **Descartada.** |
| IIS en Windows Server | Sirve si el cliente lo exige. | No aporta nada sobre servir archivos estáticos y es más caro de operar. |

**Manifiesto** (`stable.json`):

```json
{
  "version": "v1.4.0",
  "published_at": "2026-11-02T15:00:00Z",
  "url": "https://updates.<dominio-seo>/savi/releases/SAVI-Setup-v1.4.0.exe",
  "sha256": "9f2c…",
  "size": 170082699,
  "min_version": "v1.3.1",
  "notes": "Corrige la pantalla en blanco… (texto corto para el usuario, de usted)"
}
```

- `min_version`: toda instalación por debajo **debe** actualizar. Su pantalla se bloquea hasta hacerlo. Es la palanca para cambios críticos o de esquema.
- Entre `min_version` y `version`, la actualización es **recomendada**: aparece un aviso que se puede posponer.

## 4. Flujo en el equipo

```
SAVI (backend)                                   Servidor de actualizaciones
  │  al arrancar y cada 6 h ─── GET stable.json + .sig ───▶
  │  verifica la firma y compara con __version__
  │
  ├─ igual o mayor → nada
  ├─ menor, ≥ min_version → aviso "Hay una versión nueva" (posponible)
  └─ menor que min_version → pantalla bloqueante "Debe actualizar"
                │
     usuario pulsa "Actualizar y reiniciar"
                │
  descarga el .exe a %ProgramData%\SAVI\updates\ ─── GET releases/… ──▶
  verifica SHA-256 y la firma Authenticode
  lanza el instalador en silencio y termina
                │
  instalador: cierra SAVI, reemplaza archivos, conserva .env, relanza SAVI
                │
  frontend: muestra "Actualizando…", espera /health con la versión nueva y recarga
```

**Modo de instalación silenciosa:**

```
SAVI-Setup-v1.4.0.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /LOG="%ProgramData%\SAVI\updates\install.log"
```

Al ser una actualización, el asistente no muestra páginas: conserva `.env`, `ERP_CREDENTIALS_KEY` y los datos.

### El permiso de administrador

Es la diferencia de fondo con Zed. Hay dos caminos:

| | U1: con UAC | U2: servicio de actualización |
|---|---|---|
| Cómo | SAVI lanza el instalador pidiendo elevación (`runas`). Windows muestra el cartel de UAC. | El instalador registra un servicio de Windows `SAVIUpdate` que corre como `LocalSystem`. SAVI le pide "instalar este archivo" y el servicio lo ejecuta, sin UAC. |
| A favor | Simple: casi no hay código nuevo. | Experiencia tipo Zed. Funciona **aunque la usuaria no sea administradora**, que es lo normal en empresas. Es lo que hacen Chrome y Edge. |
| En contra | Si quien usa SAVI no tiene permisos de administrador, **no puede actualizar**, y entonces la actualización obligatoria se vuelve un bloqueo. | Más código y más superficie de ataque. El servicio **solo** debe ejecutar instaladores firmados por SEO y cuyo SHA-256 coincida con el manifiesto firmado. |

**Recomendación:** U1 para salir rápido y validar el circuito con SEO interno. U2 antes de los clientes, porque en sus equipos casi nadie es administrador.

## 5. Seguridad (no negociable)

Un sistema de autoactualización es un canal para ejecutar código en todos los equipos: si se compromete, se compromete toda la flota.

1. **HTTPS** siempre, sin excepción para "redes internas".
2. **Manifiesto firmado** con una clave Ed25519. La clave pública va dentro de SAVI y la privada fuera del servidor, en el equipo de publicación o en un secreto. Así, aunque alguien tome el servidor, no puede publicar una versión.
3. **SHA-256** del instalador en el manifiesto, verificado antes de ejecutar.
4. **Firma de código Authenticode** del `.exe`, que el servicio U2 exige además del hash. También evita el cartel de SmartScreen. Requiere comprar un certificado de firma de código: costo anual, a decidir (D3).
5. **Nunca bajar de versión** aunque el manifiesto lo diga. Se rechaza `version < __version__`.
6. Todo intento queda en `savi.log`: chequeo, descarga, verificación, lanzamiento y resultado.

## 6. Experiencia de usuario (textos de usted)

- **Aviso recomendado:** una barra superior que dice "Hay una versión nueva de SAVI (v1.4.0)". Tiene dos botones, **Actualizar y reiniciar** y **Más tarde**, y un enlace "Qué cambió" que muestra `notes`. "Más tarde" lo oculta por 24 h.
- **Obligatoria:** un diálogo sin cerrar: "Esta versión de SAVI ya no es compatible. Debe actualizar para seguir usándola." Un único botón: **Actualizar ahora**.
- **Durante la actualización:** una pantalla con progreso de descarga y luego "Reiniciando SAVI…". Cuando `/health` responde con la versión nueva, recarga sola.
- **Si falla:** un mensaje claro y el botón **Reintentar**. SAVI sigue funcionando con la versión actual, salvo que sea obligatoria.
- **Conversación en curso:** no actualizar a mitad de un turno. El botón espera a que terminen los turnos activos (ver `turn_registry`).
- **Quién la ve:** el aviso lo ve cualquiera, pero en U1 solo un administrador puede aceptar el UAC. En U2, cualquiera.

## 7. Publicación (lado SEO)

`scripts/publish-release.py` (nuevo):

1. Toma el `.exe` que generó `installer/build.ps1` para un tag `vX.Y.Z` y rechaza los builds "sucio".
2. Lo firma con Authenticode, cuando exista el certificado.
3. Calcula el SHA-256 y arma el manifiesto con `notes` (tomadas del tag anotado) y `min_version`. `min_version` se mantiene igual salvo que se indique `--min-version`.
4. Firma el manifiesto con Ed25519.
5. Sube el `.exe` y después el manifiesto, en ese orden. Si se subiera primero el manifiesto, apuntaría a un archivo que todavía no existe.
6. Permite publicar primero a `beta.json` y después promover a `stable.json`.

Publicar sigue siendo una decisión humana, igual que crear el tag: el script no corre solo en CI.

## 8. Fases

| Fase | Contenido | Criterio de hecho |
|---|---|---|
| **U0 Servidor y publicación** | Carpeta estática con HTTPS (Caddy). `publish-release.py` con manifiesto, SHA-256 y firma Ed25519. | `stable.json` publicado y verificable desde un equipo de prueba. |
| **U1 Aviso y actualización con UAC** | Módulo `updates` en el backend (chequeo, verificación, descarga, lanzamiento). Barra de aviso y diálogo obligatorio en el frontend. Entrada `[Run]` que relanza SAVI en modo silencioso. Bloqueo por `min_version`. | Un equipo con v1.4.0 pasa a v1.4.1 con un clic y un UAC, sin perder la configuración ni las conversaciones. Tests: comparación de versiones, firma inválida rechazada, hash inválido rechazado, intento de bajar de versión rechazado. |
| **U2 Servicio sin UAC** | Servicio `SAVIUpdate` (LocalSystem) registrado por el instalador. Canal local seguro con SAVI (named pipe con ACL). Exige Authenticode más el hash del manifiesto. | Una cuenta sin permisos de administrador actualiza sola. Un `.exe` sin firma o con otro hash se rechaza. |
| **U3 Despliegue controlado** | Canal `beta`. Despliegue por porcentaje (un hash del id de instalación decide si le toca). Reporte de la versión instalada por equipo, aunque sea solo en el log. | Una versión llega primero al 10 % y se puede frenar quitándola del manifiesto. |
| **U4 (opcional) Con SAVI Cloud** | Cloud ya recibe la versión de cada instancia por el heartbeat. Puede mostrar quién está atrasado y fijar `min_version` por cliente. | La consola muestra la versión de la flota. No es requisito de U0 a U3. |

## 9. Fuera de alcance

- **Actualizaciones diferenciales (deltas):** 160 MB por versión es aceptable. Los deltas agregan mucha complejidad y su ventaja es chica.
- **Actualizar solo el frontend:** todo viaja en un único `.exe` de PyInstaller. Separarlo complica el versionado sin un beneficio real hoy.
- **Bajar de versión:** las migraciones son solo hacia adelante.

## 10. Decisiones abiertas

- **D1. Dónde se aloja:** el servidor Linux de SAVI Master (M1.5) o almacenamiento de objetos (R2/S3). Se recomienda el servidor Linux si se arma pronto; si no, R2.
- **D2. Cuándo pasar a U2:** antes de los clientes o desde el inicio. Depende de si el personal de SEO tiene permisos de administrador.
- **D3. Certificado de firma de código:** comprarlo (estándar o EV) y quién custodia la clave.
- **D4. Ventana de actualización obligatoria:** inmediata, o con un plazo por ejemplo de 72 h antes de bloquear.
- **D5. Canal por cliente:** si algunos clientes van en `beta`.
