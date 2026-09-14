"""Traducción de errores del proveedor a mensajes accionables en el chat."""

# Señales de que el problema es la credencial y no la pregunta.
#
# Sin "401" suelto a propósito: aparece en mensajes que no tienen nada que
# ver ("el planner estima ~401.000 filas") y sugerir renovar la credencial
# ahí manda a la persona a perder el tiempo en el lugar equivocado. Los
# mensajes de credencial reales siempre traen alguna de estas palabras.
_AUTH_ERROR_MARKERS = (
    "oauth",
    "authenticate",
    "authentication",
    "unauthorized",
    "api key",
    "api-key",
)


def is_credential_error(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _AUTH_ERROR_MARKERS)


def user_facing_error(message: str, *, credential_remedy: str) -> str:
    """Agrega el camino de salida cuando el error es de credencial.

    El mensaje del proveedor ("401 OAuth access token has expired")
    describe el problema pero no qué hacer, y quien lo lee sólo quería
    preguntar por una factura. Cada proveedor aporta su propio remedio.
    """
    if is_credential_error(message):
        return f"{message}\n\n{credential_remedy}"
    return message
