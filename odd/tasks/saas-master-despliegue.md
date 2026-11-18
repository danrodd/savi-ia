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
  - [x] Commit del merge: `0536233`, más `754cbc7`, que trae `c6bb6eb`, el arreglo de `xlsx` en `staging`.
- [ ] **T2. `v1.5.0` estable.**
  - [x] `main` avanzó hasta `staging` (`c6bb6eb`) sin crear un merge; tag `v1.5.0` publicado.
  - [x] Instalador `SAVI-Setup-v1.5.0.exe` (164 MB, SHA-256 `f9595a69…aa28`).
  - [x] Manifiestos firmados de `beta` y `stable`, con notas para el usuario y la misma versión mínima que la rc.1.
  - [ ] Subida y verificación: bloqueadas. El 2026-11-18 el servidor `178.105.211.179` no respondía ni por SSH (22) ni por HTTPS (443), aunque este equipo sí tenía internet. Los archivos listos para subir están en `installer/output/updates/`.
- [ ] **T3. Desplegar el Master.**
- [ ] **T4. Base de demo ficticia.** El usuario eligió una empresa inventada desde cero y no anonimizar una copia de Imporllantas, porque una demo pública no debe llevar ni el catálogo de un cliente. Ruta: inline.
  - [x] T4.1 Generador reproducible en `scripts/demo-erp/` con semilla fija:
    - estructura del ERP sin datos;
    - catálogos públicos o de SEO: municipios, formularios del ERP, tarifas de IVA;
    - datos sintéticos de una distribuidora de llantas.
  - [x] T4.2 Tablas pobladas:
    - empresa, centro de costo y almacenes;
    - grupos y productos;
    - terceros: clientes, proveedores y vendedores;
    - facturas de venta y de compra con su detalle, de 24 meses;
    - saldos de inventario por mes;
    - cartera por cobrar y por pagar;
    - usuarios con perfiles distintos y sus permisos.
  - [ ] T4.3 Validación con SAVI en local: las preguntas de la demo (ventas por vendedor, productos sin movimiento, clientes de una referencia con celular, cartera, informe PDF con gráficos).
  - [ ] T4.4 Volcado restaurable para el Master y la guía para cargarlo.
  - Fuera de alcance: contabilidad, nómina y los demás módulos quedan vacíos.
  - Evidencia de T4.1 y T4.2 (2026-11-18), generando desde `imporllantas`:
    - 151 productos, 467 terceros, 5439 facturas de venta, 217 de compra, 6960 saldos y 196 documentos de cartera con saldo.
    - Ventas por 15.016 millones.
    - Dos corridas dieron cifras idénticas.
    - Las facturas cuadran contra su detalle, y el inventario cumple inicial + entradas − salidas = actual.
    - Revisión de fugas en el volcado: el NIT, el correo y los teléfonos de la empresa de origen no aparecen. La única palabra de su razón social que aparece es un nombre de departamento del catálogo del DANE. Los apellidos que coinciden salen de municipios, de nombres inventados o de los comentarios de los programadores de SEO en las funciones.
- [ ] **T5. Vincular las instalaciones internas.**

## Decisiones abiertas

- **D4:** el dominio oficial. Para probar alcanza con `danrodd.dev`.
- **P8:** la revisión legal antes de recibir métricas de clientes reales.

## Próximo paso

Revisar el servidor en la consola de Hetzner. Cuando vuelva, subir `stable` y `beta` y verificar los dos canales.
