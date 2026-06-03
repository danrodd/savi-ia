"""Puerto al plan contratado en `SEO.Modulo`.

La tabla `SEO.Modulo` es un espejo de los módulos que el cliente
contrató, sincronizado desde el portal externo SEO. Puede tener
varias filas históricas; la vigente es la de mayor `idModulo`
(decisión confirmada con el equipo del ERP).

El repositorio devuelve un dict con los flags booleanos por columna.
La capa de aplicación los traduce a códigos de módulo via
`MODULE_TO_SEO_FLAG`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class SeoPlanRepository(ABC):
    @abstractmethod
    async def get_active_plan(self) -> dict[str, bool]:
        """Devuelve los flags de la fila vigente de `SEO.Modulo`.

        Si no existe ninguna fila, retorna dict vacío — el caso de uso
        decide cómo manejarlo (cliente sin plan = sin módulos verticales).
        Las claves coinciden con los nombres de columna del ERP, no se
        traducen acá."""
