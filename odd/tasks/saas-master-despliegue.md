# SaaS: SAVI Master desplegado

## Objetivo

Tener SAVI y la consola de SAVI Cloud corriendo en internet. Con eso SEO puede:

- administrar a los clientes;
- ver el uso que le dan;
- mostrar una demo sin instalar nada.

## Por qué ahora

La demo con Imporllantas quedó corregida y validada por soporte con la `v1.5.0-rc.1`. Gran parte del SaaS ya está construida en `develop`, pero nunca se desplegó:

- la consola de Cloud;
- la vinculación y las métricas;
- las políticas de IA, bases y configuración;
- el doble factor;
- el stack `deploy/master`.

`develop` y `staging` venían separados desde el 2026-10-20.

## Alcance

1. Integrar `staging` en `develop`, sin perder lo de ninguna rama.
2. Cerrar la `v1.5.0` estable. Necesita OK: `main`, tag, build y publicación en `stable`.
3. Desplegar el Master (M1.5 de la spec 07) en el servidor de pruebas. Necesita autorización remota.
4. Crear una base de demo con datos ficticios, para no exponer datos de clientes.
5. Vincular las instalaciones internas de SEO a Cloud. Los clientes reales esperan la revisión legal (P8).
6. Después: el gateway de créditos (M5).

## Restricciones

- Para `develop`, `main`, los tags, el build y el servidor se necesita el OK explícito del usuario.
- En la demo pública no van datos reales de clientes.
- Todo texto visible va de usted.

## Tareas

- [x] **T1. Integrar `staging` en `develop`.** Ruta: inline, por preferencia del usuario de no usar subagentes.
  - [x] Conflictos resueltos en 7 archivos:
    - `bootstrap.py` y `main.py`: se suman los routers, los modelos y el ciclo de vida de Cloud y de las actualizaciones.
    - `App.vue`, `AdminLayout.vue` y `Dialog.vue`, donde se combinan `showClose` y `dismissible`.
    - El test de rutas de migración.
    - `package-lock.json`.
  - [x] Migración de unión `08f236755fc9`, que junta `f1a6c3d8e2b4` (Cloud y MFA) con `f6a1c4e8d2b3` (documentos).
  - [x] Los imports de `@/components/ui/*` de los archivos nuevos de `staging` pasan a `@savi/ui`.
  - [x] Se agrega `empresa` a la lista blanca de tipos de conocimiento de Cloud. Lo detectó el test guardián.
  - [x] Vuelve `xlsx` a `frontend/package.json`. Lo había quitado `9bcaf29`, pero la exportación a Excel del feedback del piloto lo usa. También hay que corregirlo en `staging`.
  - [x] Los tests de `company_knowledge` que trajo `staging` (`test_upload_limit`, `test_web_http`, `test_http_and_download`) también sobreescriben `require_unlocked_company_admin`, el guard de `develop` que suma el bloqueo de configuración de Cloud. Sin eso, las escrituras respondían 401.
  - [x] Verificación:
    - backend: 1832 pasados, 10 saltados, Pyright sin errores; los 5 avisos de Ruff ya estaban en `develop`;
    - frontend: 394 tests y vue-tsc ✅;
    - `packages/ui`: 51 ✅;
    - Cloud frontend: 212 ✅;
    - Cloud backend: 372 ✅.
  - [ ] Commit del merge.
- [ ] **T2. `v1.5.0` estable.**
- [ ] **T3. Desplegar el Master.**
- [ ] **T4. Base de demo ficticia.**
- [ ] **T5. Vincular las instalaciones internas.**

## Decisiones abiertas

- **D4:** el dominio oficial. Para probar alcanza con `danrodd.dev`.
- **P8:** la revisión legal antes de recibir métricas de clientes reales.

## Próximo paso

T2: `v1.5.0` estable, con el OK del usuario. Antes hay que llevar a `staging` la corrección de `xlsx`.
