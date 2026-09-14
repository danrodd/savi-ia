"""Excepciones del módulo. Se mapean a HTTP en `shared/exceptions`."""
from __future__ import annotations

# Import directo de `.base`: el paquete `shared.exceptions` carga los
# handlers HTTP, que importan excepciones de los módulos.
from app.shared.exceptions.base import NotFoundError, ValidationError


class LlmProviderNotFoundError(NotFoundError):
    """El proveedor pedido no está en el catálogo. → 404."""


class LlmProviderNotImplementedError(ValidationError):
    """El proveedor está declarado pero esta versión no lo soporta. → 422."""
