# Batería — Importar conocimiento desde la web

> Parte de: [Conocimiento de la empresa](00-prd.md) ·
> [Fase 5](05-fase-importar-desde-web.md).
> Fecha: 2026-09-28. Script: `backend/scripts/bateria_web_ciclo_vida.py`.
> Proveedor: OpenAI, `gpt-6-luna`.

## Resultado

| Bloque | Resultado | Qué prueba |
|---|---|---|
| **SSRF** | **17/17** | localhost, metadatos de nube, IP privada, loopback no permitido, puerto de la base, `file://`, usuario en la URL, IPv6 local (vista previa y alta) y una redirección del sitio hacia la red interna: todo 422 |
| **Acceso** | **1/1** | Un usuario no administrador recibe 403 al listar y al crear |
| **Alta** | **7/7** | Vista previa con secciones del sitemap; respeta `robots.txt`; descarta el carrito; excluye la sección elegida; guarda el pie una vez |
| **Chat** | **4/4** | Precio con cita y link; no conoce lo excluido por `robots.txt`; responde el teléfono del pie |
| **Cambio de precio** | **4/4** | Solo esa página cambia (versión 2 del mismo documento); precio nuevo en conversación nueva y abierta |
| **Página borrada** | **5/5** | Primer 404: queda con error y responde lo último bueno; segundo: se da de baja, se borra el documento y deja de citarse |
| **Permisos** | **4/4** | Página solo para cartera en una base: la ve cartera ahí, no otro módulo ni otra base; abrir los permisos se propaga |
| **Baja** | **2/2** | Borrar el sitio elimina sus páginas y deja de responder |

**44/44** con las correcciones. Las dos primeras corridas dieron 40/43 y
42/44: así aparecieron los tres defectos de §3. Otras tres fallas eran del
propio script (§4).

~13 preguntas al chat por corrida; el resto se comprueba contra la API.

## 1. Cómo se prueba

El script levanta en `http://127.0.0.1/` una ferretería inventada ("El
Tornillo") y la modifica en vivo entre lecturas:

- `robots.txt` que prohíbe `/privado/` y apunta a un índice de sitemaps con
  dos secciones: páginas (portada, precios, garantía, envíos, costos
  internos, carrito) y blog.
- Menú en `<header>` y datos de contacto en `<footer>`, como WordPress,
  Next, Nuxt y Astro.
- `/salir` redirige a `169.254.169.254` para probar la guarda en cada salto.
- `/credito`, una página suelta para la prueba de permisos.

Como la guarda SSRF bloquea la red interna, el backend se arranca con
`127.0.0.1` permitido. El resto de direcciones internas (`localhost`,
`127.0.0.2`, `::1`, `192.168.x`) sigue bloqueado, y eso es lo que prueba el
bloque SSRF:

    COMPANY_WEB_ALLOWED_PRIVATE_HOSTS='["127.0.0.1"]' uv run dev
    uv run python scripts/bateria_web_ciclo_vida.py

Usuarios de QA de la [batería de permisos](bateria-permisos-bases.md#1-usuarios):
`SAVIQA` (admin), `QAINV` y `QACXC` (no admin).

## 2. Lo que confirma

- **La versión vieja responde hasta que la nueva está lista**: después de
  cambiar el precio, la conversación que ya estaba abierta responde el
  nuevo sin reiniciar nada.
- **Un error pasajero no borra conocimiento**: con el primer 404 SAVI sigue
  respondiendo la garantía; recién con el segundo la da de baja.
- **Los permisos de la fuente se propagan a sus páginas** en la siguiente
  pregunta, igual que en un documento subido.
- **Lo que `robots.txt` prohíbe nunca entra**: el "margen interno" de
  `/privado/costos` no aparece en ninguna respuesta.

## 3. Defectos encontrados y corregidos

Cada uno con un test que falla sin la corrección.

1. **Se perdía el pie de página en sitios semánticos.** El extractor
   descarta `<header>`/`<footer>` de la página con la plantilla, y la
   limpieza por repetición solo rescataba el pie en temas armados con
   `div` (por eso no se vio con Sur Andina). En WordPress, Next, Nuxt o
   Astro se perdían la dirección, el teléfono y los horarios. Ahora el
   extractor guarda el pie aparte (sin su menú) y el rastreo lo suma a la
   comparación de plantilla: queda una vez en "Información general del
   sitio".
2. **La información general exigía 25 palabras**, como una página de
   contenido. Un pie con razón social, dirección y teléfono ronda las 15 y
   se descartaba igual. Tiene su propio mínimo (6).
3. **La primera vez que una página faltaba quedaba como "Sin cambios"**,
   con el aviso solo en el detalle. Ahora queda como error, con el motivo
   ("respondió que ya no existe" o "ya no aparece en el sitio") y el aviso
   de que se da de baja si sigue así.

## 4. Fallas del script, no del producto

- La portada de prueba tenía menos de 25 palabras y se descartaba como
  "sin texto útil", que es lo esperado.
- Se esperaba la cita del pie en `#informacion-general`. El fragmento no
  existe en el sitio real: a propósito la cita lleva a la portada, donde el
  visitante ve ese pie. Se comprueba por el título de la fuente.

## 5. Qué no cubre

- Sitios que necesitan navegador (contenido que solo aparece con
  JavaScript): la fase solo avisa; el navegador opcional está pendiente.
- La ventana nocturna de los refrescos automáticos: tiene tests unitarios;
  la batería usa refresco manual.
- PDF enlazados desde el sitio: cubiertos en la prueba real con Sur Andina
  (su política de tratamiento de datos en PDF se importó como una página
  más).
