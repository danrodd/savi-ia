# Landing de SAVI

> Parte de: [PRD — Plataforma SAVI](00-prd.md).
> Estado: **implementada** (2026-09-28) en `frontend/src/modules/landing/`,
> ruta `/inicio`. Se activa con `VITE_LANDING_ENABLED=true`; "Solicitar
> demo" necesita `VITE_LANDING_CONTACT_EMAIL` (sin él, el formulario avisa y
> no envía).
> Skills a leer antes de codear: `vue-best-practices`,
> `vue-router-best-practices`, `enterprise-frontend-architecture`.

## Para qué

Una página sencilla y moderna que presente SAVI como plataforma y sea el
punto de partida comercial de lo que viene (SAVI Cloud, registro de
clientes, créditos). Hoy no hay ninguna cara pública del producto.

## Decisiones

| Tema | Decisión | Por qué |
|---|---|---|
| Dónde vive | **En este frontend** (`frontend/`), como una ruta pública más | Decisión del equipo: un solo proyecto por ahora. Astro aparte sería lo ideal para SEO y costo, y queda como opción cuando la landing crezca. |
| Ruta | Pública, sin sesión, con su propio layout y cargada bajo demanda | No debe arrastrar el código del chat ni pedir login. |
| Visible en instalaciones de clientes | Detrás de una variable de build (`VITE_LANDING_ENABLED`), apagada por defecto | El mismo frontend se instala en el servidor de cada empresa: ahí la landing no tiene sentido. |
| Llamado a la acción | **"Solicitar demo"**, sin precios | Los planes dependen de qué es un crédito y su precio (PRD, P5). |
| Textos de "cómo funciona" | Modelo híbrido (SAVI en la red de la empresa, Cloud para métricas y créditos) | Es lo que describe el PRD; si se decide SaaS puro (§15), se reescribe esa sección. |

## Secciones

1. **Portada**: qué es SAVI en una frase, imagen del chat real y "Solicitar demo".
2. **Qué hace**: preguntas reales respondidas con datos del ERP ("¿cuánto
   facturamos en marzo?", "¿qué clientes están en mora?"), documentos y el
   sitio web de la empresa con citas.
3. **Cómo funciona**: SAVI al lado del ERP, en la red de la empresa; SAVI Cloud
   para administrar y medir.
4. **Seguridad y privacidad**: los datos del ERP no salen de la empresa,
   permisos del ERP respetados, consentimiento antes de enviar documentos a
   la IA. Es el argumento fuerte del modelo híbrido.
5. **Para quién**: los verticales del ERP (agro, automotriz, restaurante,
   farmacia, salud, bomberos, microcrédito).
6. **Modelos de IA**: clave propia (Claude, OpenAI, Gemini) o créditos
   gestionados por SEO (próximamente).
7. **Solicitar demo**: formulario corto. Destino a definir (correo o, más
   adelante, SAVI Cloud).
8. **Pie**: SEO Group, contacto.

## Implementación

- La portada muestra un chat de ejemplo armado en HTML con datos inventados,
  no una captura: las capturas reales traen nombres y cifras de clientes.
- "Solicitar demo" valida los campos y abre el correo con todo completo
  (`mailto:`). Cuando exista SAVI Cloud, pasa a un endpoint.
- Solo promete lo validado: nada de preguntas de inventario (no está
  modelado en la capa semántica), y SAVI Cloud y los créditos van como
  "Próximamente".

## Pendiente

- Correo de destino de las solicitudes de demo.
- Dominio: depende de P3 del PRD.
