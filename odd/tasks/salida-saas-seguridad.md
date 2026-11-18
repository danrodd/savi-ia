# Salida del SaaS: doble factor, avisos y costo de la demo

## Objetivo

Cerrar lo que se puede hacer sin el servidor antes de abrir el Master a internet:

- un doble factor que se entienda a la primera;
- avisos de las alertas, para que alguien se entere sin abrir la consola;
- un tope de costo para la demo pública.

## Por qué

En la revisión del 2026-11-18 aparecieron tres problemas:

- **El doble factor tiene dos implementaciones distintas.** En Cloud es una columna larga que no entra en la pantalla. En SAVI es un campo de texto suelto con un botón.
- **Nadie se entera de una alerta.** El notificador de alertas es un `NoopAlertNotifier`, así que solo se ven en la consola.
- **La demo abierta puede gastar en IA sin freno.** Permite 200 turnos por hora por persona.

## Alcance

Rama `develop`. El usuario autorizó el trabajo el 2026-11-18. Las instalaciones de los clientes no se tocan.

## Restricciones

- El backend del doble factor no cambia. Los códigos de recuperación quedan para después.
- Los textos visibles van de usted.
- El componente compartido vive en `@savi/ui` y lo usan SAVI y Cloud.

## Tareas

- [x] **S1. `TwoFactorPanel` en `@savi/ui`.** Tiene dos modos:
  - **Configuración:** tres pasos cortos, un QR compacto, la clave agrupada en bloques de 4 que se despliega con "¿No puede escanear?", y casillas que se envían solas.
  - **Verificación:** las casillas, un indicador de cuánto falta para que el código cambie y una ayuda para quien perdió el celular.
- [x] **S2. Cloud:** el ingreso usa `TwoFactorPanel`.
- [x] **S3. SAVI:** `MfaPanel` usa `TwoFactorPanel`.
- [x] **S4. Tope de la demo.** No requiere código. Hay que documentar en `deploy/master/DEPLOYMENT.md` cómo hacerlo:
  - vincular el Master a Cloud;
  - poner el tope por persona y por proveedor;
  - bajar los límites del chat.
- [ ] **S5. Avisos de alertas.** Depende de una decisión: el canal de aviso.

## Verificación

- `packages/ui`: `vitest`, `vue-tsc` y Biome.
- Cloud frontend y SAVI frontend: `vitest`, `vue-tsc` y Biome.
- Capturas de antes y después.

## Ruta y TDD

- **Ruta:** todo inline, por preferencia del usuario.
- **TDD:** no está configurado. Las pruebas van junto con cada cambio.

## Progreso

- **S1–S3, f82aea9.** `TwoFactorPanel` en `@savi/ui`, usado en Cloud y en SAVI.
  - Pruebas: 56 en `packages/ui`, 235 en Cloud y 395 en SAVI, con `vue-tsc` sin errores.
  - Se probó en el navegador con un usuario nuevo de la Cloud local:
    - cambio de contraseña;
    - QR y clave plegada;
    - código generado desde la clave;
    - entrada a la consola;
    - verificación en un ingreso posterior.
  - En Cloud, la configuración entra en una sola pantalla: la marca se achica y la tarjeta es más ancha.
- **4b2206a.** Tres pruebas de Cloud que montan el router pasaban los 5 s en la suite completa (solas tardan menos de 1 s), porque la carga en frío de las vistas creció. Se fijó un `testTimeout` de 15 s.
  - Nota de proceso: f82aea9 se hizo con esas tres pruebas fallando, porque el commit se encadenó a la prueba en el mismo comando. Se corrigió en el commit siguiente.
- **S4, 5702107.** Se agregó la sección §6.1 a `DEPLOYMENT.md`, y el compose ahora acepta `SAVI_RATE_LIMIT_CHAT_PER_MINUTE` y `SAVI_RATE_LIMIT_CHAT_PER_HOUR`.

## Próximo paso

S5: definir el canal de aviso de las alertas.
