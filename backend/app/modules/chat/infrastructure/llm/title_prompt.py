"""Prompt y limpieza del auto-título, compartidos entre proveedores.

Uso en dos fases:
- Fase 1: al recibir el primer turno (sólo `user_msg`) — título provisional.
- Fase 2: tras el turno completo (`user_msg` + `assistant_msg`) — refinado.
"""

TITLE_SYSTEM_PROMPT = (
    "Eres un generador de títulos para una conversación con un asistente "
    "del ERP de SEO Group. Responde ÚNICAMENTE con un título muy corto "
    "(máximo 5 palabras, en español neutro de Colombia, sin comillas, "
    "sin punto final, sin emojis) que resuma la consulta del usuario. "
    "No saludes. No expliques. Solo el título."
)

_MAX_TITLE_LEN = 80
_ASSISTANT_PREVIEW_CHARS = 600


def build_title_prompt(user_msg: str, assistant_msg: str = "") -> str:
    if assistant_msg.strip():
        return (
            f"Usuario: {user_msg.strip()}\n\n"
            f"Asistente: {assistant_msg[:_ASSISTANT_PREVIEW_CHARS].strip()}\n\n"
            "Título:"
        )
    return f"Usuario: {user_msg.strip()}\n\nTítulo:"


def clean_title(raw: str) -> str | None:
    """Título limpio, o `None` si quedó vacío."""
    title = raw.strip().strip('"').strip("'").strip(".").strip()
    return title[:_MAX_TITLE_LEN] or None
