# UX de Cloud: fase 1, base visual y textos

## Objetivo

Que la consola de SAVI Cloud y las páginas de SAVI que van a internet se vean con la misma calidad que el chat de SAVI. Esta fase no cambia la estructura de las pantallas.

## Por qué

La revisión del 2026-11-18 encontró 33 puntos (https://claude.ai/artifact/W37zhfJpXZ2JipayHNHsWA). La fase 1 toma los que cambian la impresión general con poco riesgo. También incluye dos arreglos que deben estar listos antes de abrir el Master a internet.

## Alcance

Rama `develop`, que es donde vive Cloud. El usuario autorizó la fase 1 el 2026-11-18. Las instalaciones de los clientes no se tocan: corren `main` o `staging`, que no traen Cloud.

## Tareas

- [x] **F1.1 Identidad (T1, S3).** Logo de SAVI en la barra lateral y en la cabecera móvil de Cloud, y en Administración de SAVI.
- [x] **F1.2 Color semántico (T2).** El rojo de marca deja de usarse para:
  - los enlaces de datos, como el código del cliente en Instancias;
  - los pasos pendientes de la Puesta en marcha;
  - las barras de los gráficos.
- [x] **F1.3 Nombres de negocio (T4, N2, U1, D5).** En lugar de los valores técnicos:
  - modo y base del agente;
  - proveedor y modelo;
  - herramientas;
  - acciones de auditoría;
  - "heartbeat";
  - el autor `cloud-admin`.
- [x] **F1.4 Instancias (I2).** "Nunca se conectó" en lugar de "Sin conexión". I1 se descartó: la fila sí abre el detalle, con clic y con teclado. El error estuvo en la revisión.
- [x] **F1.5 Textos del Master (S1, S2).**
  - Pasar a usted el texto de Administración → SAVI Cloud.
  - Que el formulario de demo de la landing no aparezca roto cuando no tiene correo de destino. La imagen del Master compila sin landing (`VITE_LANDING_ENABLED=false`, una decisión documentada en el Dockerfile), así que en el Master no se veía. Igual, sin destino se muestra una indicación para el visitante.

## Decisión

- **Correcciones a la revisión.** I1 y A1 eran incorrectos: la fila abre el detalle, y la alerta de instalación sin conexión cuenta desde la vinculación. I3 es de configuración: hay que poner `CLOUD_LATEST_VERSION` y `CLOUD_LATEST_VERSION_PUBLISHED_AT` al desplegar el Master. El informe se republicó corregido.

- **T3, etiquetas en mayúsculas: queda fuera de esta fase.** Es el lenguaje del paquete compartido `@savi/ui`, y SAVI también lo usa en el ingreso y en Administración. Cambiarlo solo en Cloud las separa; se revisa junto con SAVI.

## Verificación

- Cloud frontend: `vue-tsc` y `vitest`.
- SAVI frontend: `vue-tsc` y `vitest`.
- `packages/ui`: sus pruebas, si se toca.
- Backend: `test_usted_register.py`.
- Capturas de antes y después.

## Progreso

Hecho el 2026-11-18. Las rutas se trabajaron inline, por preferencia del usuario.

- **Cloud frontend:** 217 pruebas (antes 212), `vue-tsc` y Biome sin errores.
  - Pruebas nuevas: estado "Nunca se conectó", nombres de negocio, filtro y celda de auditoría.
- **SAVI frontend:** 394 pruebas y `vue-tsc` sin errores.
  - Biome deja un aviso en `ErpDatabaseTable.vue`, que ya estaba antes y no se tocó.
- **`test_usted_register.py`:** 12 pruebas pasan. El test no detecta tuteo, así que "Acá ves" se corrigió a mano.
- **Capturas de después** (en local):
  - el logo de SAVI;
  - enlaces neutros con subrayado;
  - "Nunca se conectó";
  - auditoría con las acciones por su nombre;
  - Servidor y PostgreSQL;
  - los pasos pendientes sin rojo.

## Próximo paso

Fase 2: el Resumen con "Requiere atención", y las listas de clientes e instancias con datos de negocio.
