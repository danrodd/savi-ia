"""Excepciones del compilador semántico.

Todas heredan de SemanticQueryError. El use case las captura y devuelve un
mensaje accionable al LLM (que SAVI traduce a lenguaje de usuario), nunca
un stack trace ni detalle técnico de la BD.
"""
from __future__ import annotations


class SemanticQueryError(Exception):
    """Base. El `message` es seguro de mostrar (no expone schema)."""


class UnknownEntityError(SemanticQueryError):
    def __init__(self, entidad: str, disponibles: list[str]) -> None:
        super().__init__(
            f"No conozco la entidad '{entidad}'. "
            f"Disponibles: {', '.join(disponibles)}."
        )


class UnknownFieldError(SemanticQueryError):
    def __init__(self, kind: str, name: str, entidad: str, disponibles: list[str]) -> None:
        super().__init__(
            f"'{name}' no es un(a) {kind} válido(a) para '{entidad}'. "
            f"Disponibles: {', '.join(disponibles) if disponibles else '(ninguno)'}."
        )


class InvalidQueryError(SemanticQueryError):
    """Modo mal usado: agregado sin métricas, detalle sin campos, etc."""


class FilterOpNotAllowedError(SemanticQueryError):
    def __init__(self, campo: str, op: str, permitidos: list[str]) -> None:
        super().__init__(
            f"El operador '{op}' no está permitido para el filtro '{campo}'. "
            f"Permitidos: {', '.join(permitidos)}."
        )
