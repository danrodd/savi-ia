"""Clave pública de SEO para verificar los manifiestos de actualización.

Ed25519, 32 bytes en base64. La genera `scripts/publish-release.py keygen`,
que deja la privada fuera del repositorio. Va escrita en el código y no en el
`.env` a propósito: quien pudiera cambiarla podría hacer pasar por buena una
versión ajena.

Vacía, SAVI no chequea actualizaciones y lo dice en el log.
"""

UPDATE_PUBLIC_KEY = ""
