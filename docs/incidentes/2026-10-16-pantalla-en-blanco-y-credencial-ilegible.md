# Incidente 2026-10-16: pantalla en blanco y credencial ilegible en una instalación

**Estado:** resuelto en **v1.3.1**.
**Alcance:** un equipo de una usuaria. Los demás equipos funcionaban con la misma versión.

## Qué se vio

Al instalar la versión que ya usaba la usuaria (`v1.2.0-22-g500e16b`) aparecieron dos problemas:

1. **SAVI abría el navegador en blanco**, en Chrome y en Firefox.
2. **El diagnóstico marcaba el proveedor de IA (OpenAI) como ilegible**, en cada arranque y desde el 9 de octubre:

   ```
   Credencial ilegible para el proveedor de IA 'openai': ERP_CREDENTIALS_KEY no coincide.
   ```

Eran dos problemas independientes con causas distintas.

## Causa 1: pantalla en blanco

El log del servidor mostraba `GET /`, `theme-init.js` y los `/assets/*.js` respondidos con 200. Sin embargo, la consola del navegador rechazaba todos los scripts:

```
Refused to execute script from 'http://127.0.0.1:31900/theme-init.js' because its MIME type ('text/plain') is not executable
```

- `FileResponse` (Starlette) deduce el `Content-Type` con `mimetypes.guess_type`.
- En Windows, `mimetypes` lee el registro: `HKEY_CLASSES_ROOT\.js` → `Content Type`.
- En ese equipo, algún programa había dejado ese valor en `text/plain`.
- SAVI envía `X-Content-Type-Options: nosniff`, así que el navegador no ejecuta un script declarado como texto.

**Por qué solo ese equipo:** el dato roto está en el registro de ese Windows. El código de SAVI es el mismo en todos.

**Primera hipótesis descartada:** se pensó en una sesión vieja guardada en el navegador (arreglo `d0f1c12`). La consola mostró que no era eso. El arreglo igual se incluyó en v1.3.0 porque corrige otro caso real.

## Causa 2: credencial ilegible

- Las claves de los proveedores de IA y las contraseñas de las bases del ERP se guardan cifradas en la **base de SAVI**.
- La llave de cifrado (`ERP_CREDENTIALS_KEY`) está en el `.env` de **cada equipo**, y el instalador genera una nueva en cada instalación.
- Dos instalaciones apuntaban a la **misma base de SAVI** en PostgreSQL, cada una con su llave. Lo que cifró la primera no lo podía leer la segunda.

## Qué se hizo

| Versión | Cambio |
|---|---|
| v1.3.0 | El instalador ofrece **Modificar la configuración**, con los datos del `.env` actual precargados. Así se puede cambiar solo el nombre de la base de SAVI sin conocer las credenciales de PostgreSQL. Antes había que cargar todo de nuevo. |
| v1.3.0 | Al reconfigurar se conserva `SAVI_ADMIN_LOGINS` (antes se borraba). |
| v1.3.1 | El frontend se sirve con tipos fijos (`_SPA_MEDIA_TYPES` en `backend/app/main.py`), sin consultar el registro de Windows. Lo cubre el test `backend/tests/unit/test_spa_media_types.py`, que simula el registro roto. |

En el equipo de la usuaria se instaló v1.3.1 y SAVI cargó correctamente.

## Si vuelve a pasar

Síntomas, comprobación y solución, incluso para versiones anteriores sin reinstalar: [`installer/README.md` → Diagnóstico](../../installer/README.md#diagnóstico).

## Lecciones

- **Pedir la consola del navegador desde el principio** cuando la pantalla queda en blanco. El log del servidor mostraba todo en 200 y no alcanzaba para diagnosticar.
- **No depender de configuración global del sistema** para algo que SAVI controla. El tipo de sus propios archivos es un dato fijo.
- **Una base de SAVI por instalación**, salvo que se comparta la llave a propósito. Compartir la base exige copiar `ERP_CREDENTIALS_KEY` en todos los equipos.
