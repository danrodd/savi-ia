"""Puerto de prueba de conexión contra una BD candidata del ERP."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.modules.erp_databases.domain.entities import ErpDatabase


@dataclass(frozen=True, slots=True)
class ConnectionTestResult:
    ok: bool
    # Mensaje para mostrarle al usuario. En el caso de fallo dice qué
    # revisar, no el stacktrace.
    detail: str
    # Razón social leída de `Empresa.Empresa`, para que la UI la proponga
    # como nombre y quien configura confirme que apuntó al cliente
    # correcto. `None` si no se pudo leer.
    razon_social: str | None = None
    # Tablas del esquema del ERP que faltaron, si el problema fue ese.
    missing_tables: tuple[str, ...] = ()


class ConnectionTester(ABC):
    @abstractmethod
    async def test(self, database: ErpDatabase) -> ConnectionTestResult:
        """Prueba la conexión SIN persistir nada.

        No levanta por fallo de conexión: devuelve un resultado con
        `ok=False`. Un host mal escrito es un dato mal cargado, no una
        excepción del sistema.
        """
