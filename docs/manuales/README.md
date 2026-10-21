# Manuales de usuario de SAVI

Cuatro manuales en español (HTML autocontenido y PDF) con capturas reales anotadas: `01-manual-de-uso` (personal que usa SAVI), `02-configurar-proveedores-ia`, `03-configurar-bases-de-datos` y `04-importar-conocimiento` (administradores).
Las capturas están en `imagenes/`. El PDF es el entregable portable; los HTML referencian `imagenes/` con rutas relativas.
Para regenerar, con SAVI corriendo (frontend `http://localhost:5173`, backend `http://127.0.0.1:8000`): corra `node build/capturar.cjs uso`, `usochat`, `usoextra`, `calificar`, `proveedores`, `bases`, `conocimiento`, `sitios` y `vista` para las capturas (`limpiar` borra las conversaciones creadas y `borrardemo` el documento de ejemplo) y `node build/generar-pdf.cjs` para los HTML y PDF desde `build/contenido/*.html` y `build/manual.css`.
