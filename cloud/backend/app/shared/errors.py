"""Base de los errores de dominio: llevan un `code` estable para la API y el CLI."""

from __future__ import annotations


class DomainError(Exception):
    code: str = "domain_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
