"""Datos de confianza de las actualizaciones: la clave pública y el servidor oficial.

**Claves públicas** de SEO para verificar los manifiestos: Ed25519, 32 bytes en
base64. Las genera `scripts/publish-release.py keygen`, que deja la privada
fuera del repositorio. Son dos: la principal, con la que se firma, y una de
respaldo que se guarda fuera de línea. Un manifiesto vale si lo firma
cualquiera de las dos; así, si se pierde la principal, se puede seguir
publicando sin reinstalar a mano (ver la spec 09, §5).
Van escritas en el código y no en el `.env` a propósito:
quien pudiera cambiarlas podría hacer pasar por buena una versión ajena.

**Servidor oficial**: la carpeta servida por HTTPS con `<canal>.json`. Va acá
para que las instalaciones existentes la usen sin tocar su `.env`.
`UPDATE_URL` en el `.env` la reemplaza, por ejemplo, para probar en local.

Con cualquiera de los dos vacío, SAVI no chequea actualizaciones y lo dice en
el log.
"""

UPDATE_PUBLIC_KEYS: tuple[str, ...] = (
    "z7FYJ/jvNWNHThAYpEywlwZJUFXG0IVIiZepWnLHzrM=",  # principal
    "RlZiz5hGbxuZiuXG8+JFnuc/6vJZ236bkUEaqff6PIw=",  # respaldo, fuera de línea
)
DEFAULT_UPDATE_URL = "https://savi-updates.danrodd.dev/savi"
