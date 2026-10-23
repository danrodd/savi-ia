"""Datos de confianza de las actualizaciones: la clave pública y el servidor oficial.

**Clave pública** de SEO para verificar los manifiestos: Ed25519, 32 bytes en
base64. La genera `scripts/publish-release.py keygen`, que deja la privada
fuera del repositorio. Va escrita en el código y no en el `.env` a propósito:
quien pudiera cambiarla podría hacer pasar por buena una versión ajena.

**Servidor oficial**: la carpeta servida por HTTPS con `<canal>.json`. Va acá
para que las instalaciones existentes la usen sin tocar su `.env`.
`UPDATE_URL` en el `.env` la reemplaza, por ejemplo, para probar en local.

Con cualquiera de los dos vacío, SAVI no chequea actualizaciones y lo dice en
el log.
"""

UPDATE_PUBLIC_KEY = "z7FYJ/jvNWNHThAYpEywlwZJUFXG0IVIiZepWnLHzrM="
DEFAULT_UPDATE_URL = ""
