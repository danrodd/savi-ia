# Landing de SAVI

> Parte de: [PRD — Plataforma SAVI](00-prd.md).
> Estado: **acordada, sin empezar** (2026-09-28). Va después de las pruebas
> del conocimiento con Claude y Gemini y antes de responder las preguntas
> abiertas del PRD.
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

## Pendiente de definir al implementarla

- Dónde llegan las solicitudes de demo.
- Capturas del producto a usar (las de la pantalla de Conocimiento y del chat
  ya existen como referencia).
- Dominio: depende de P3 del PRD.
