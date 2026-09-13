"""Registry de engines del ERP: uno por base de cliente registrada.

Reemplaza al singleton `get_erp_engine()` de `infrastructure/database/pool.py`.

Tres decisiones de diseño, y el porqué de cada una:

- **Creación diferida.** El engine de una base se crea en su primer uso,
  no al arrancar. Con 30 clientes registrados, abrir 30 pools al inicio
  significaría 30 conexiones ociosas contra 30 bases de producción de
  clientes antes de que nadie pregunte nada.

- **Evicción LRU con tope.** Un agente de soporte usa unos pocos
  clientes por jornada, no todos. El tope acota el consumo sin importar
  cuántas bases haya registradas.

- **Invalidación explícita.** Editar o desactivar una base dispone su
  engine de inmediato. Sin esto, cambiar una contraseña no tendría
  efecto hasta reiniciar el proceso — el tipo de bug que se diagnostica
  mal durante horas.

El engine mantiene lo que ya garantizaba el pool anterior:
`default_transaction_read_only=on` y `statement_timeout`. **La BD del
ERP es de solo lectura, siempre.**
"""
from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.modules.erp_databases.domain.entities import ErpDatabase

logger = logging.getLogger(__name__)

# Cuántos engines se mantienen vivos a la vez. Un agente alterna entre
# pocos clientes por jornada; los demás se disponen y se recrean si
# vuelven a hacer falta (cuesta una conexión nueva, no un error).
DEFAULT_MAX_ENGINES = 10

# Pool chico por base: antes era 5+2 para una sola base, ahora es 3+2
# multiplicado por los engines vivos. Con el tope de arriba: 10 × 5 = 50
# conexiones en el peor caso, contra las 7 de antes.
_POOL_SIZE = 3
_MAX_OVERFLOW = 2

# Recicla conexiones para que un firewall o un `idle_session_timeout` del
# lado del cliente no deje conexiones muertas en el pool.
_POOL_RECYCLE_S = 1800


class ErpEngineRegistry:
    def __init__(self, *, max_engines: int = DEFAULT_MAX_ENGINES) -> None:
        self._engines: OrderedDict[UUID, AsyncEngine] = OrderedDict()
        self._max_engines = max_engines
        # Serializa la creación: sin esto, dos turnos concurrentes contra
        # una base todavía no abierta crearían dos engines y uno quedaría
        # huérfano con su pool abierto.
        self._lock = asyncio.Lock()

    async def get(self, database: ErpDatabase) -> AsyncEngine:
        """Devuelve el engine de esa base, creándolo si hace falta.

        El caller ya debe haber verificado `database.is_usable`: este
        método no valida estado, solo administra conexiones.
        """
        async with self._lock:
            existing = self._engines.get(database.id)
            if existing is not None:
                # Marca como recién usado para el LRU.
                self._engines.move_to_end(database.id)
                return existing

            engine = self._create(database)
            self._engines[database.id] = engine
            await self._evict_if_needed()
            return engine

    async def invalidate(self, database_id: UUID) -> None:
        """Dispone el engine de una base. Idempotente.

        Obligatorio tras editar credenciales, desactivar o eliminar.
        """
        async with self._lock:
            engine = self._engines.pop(database_id, None)
        if engine is not None:
            await engine.dispose()
            logger.info("Engine del ERP invalidado para la base %s", database_id)

    async def dispose_all(self) -> None:
        """Cierra todos los engines. Se llama en el shutdown de la app."""
        async with self._lock:
            engines = list(self._engines.values())
            self._engines.clear()
        for engine in engines:
            await engine.dispose()

    # ── Interno ──────────────────────────────────────────────────────

    def _create(self, database: ErpDatabase) -> AsyncEngine:
        logger.info(
            "Abriendo engine del ERP para '%s' (%s@%s:%s/%s)",
            database.code,
            database.username,
            database.host,
            database.port,
            database.database,
        )
        return create_async_engine(
            database.url,
            # `echo=False` fijo, nunca `settings.app_debug`: el echo de
            # SQLAlchemy imprime los parámetros de cada sentencia, y por
            # acá pasan datos del ERP del cliente.
            echo=False,
            pool_pre_ping=True,
            pool_size=_POOL_SIZE,
            max_overflow=_MAX_OVERFLOW,
            pool_recycle=_POOL_RECYCLE_S,
            connect_args={
                "server_settings": {
                    "default_transaction_read_only": "on",
                    "statement_timeout": str(database.statement_timeout_ms),
                },
            },
        )

    async def _evict_if_needed(self) -> None:
        """Saca los menos usados hasta respetar el tope.

        El `dispose()` se despacha como tarea: espera a que las
        conexiones en uso se devuelvan al pool, y bloquear el lock
        mientras tanto frenaría todos los turnos en curso.
        """
        while len(self._engines) > self._max_engines:
            evicted_id, evicted = self._engines.popitem(last=False)
            logger.info(
                "Evicción LRU del engine %s (tope: %d)",
                evicted_id,
                self._max_engines,
            )
            _background_dispose(evicted)


def _background_dispose(engine: AsyncEngine) -> None:
    task = asyncio.create_task(engine.dispose())
    # Guardar la referencia evita que el GC recolecte la tarea a mitad de
    # ejecución, y el callback registra el fallo en vez de dejar una
    # excepción sin recuperar en el event loop.
    _PENDING_DISPOSALS.add(task)
    task.add_done_callback(_PENDING_DISPOSALS.discard)


_PENDING_DISPOSALS: set[asyncio.Task[None]] = set()


# ── Provider de proceso ──────────────────────────────────────────────
# Mismo patrón que `knowledge/infrastructure/catalog_provider.py`: una
# instancia por proceso, inicializada en el lifespan.

_registry: ErpEngineRegistry | None = None


def init_engine_registry(*, max_engines: int = DEFAULT_MAX_ENGINES) -> None:
    global _registry
    _registry = ErpEngineRegistry(max_engines=max_engines)


def get_engine_registry() -> ErpEngineRegistry:
    if _registry is None:
        raise RuntimeError(
            "ErpEngineRegistry no inicializado. Llamá a "
            "init_engine_registry() en el arranque."
        )
    return _registry


async def close_engine_registry() -> None:
    global _registry
    if _registry is not None:
        await _registry.dispose_all()
        _registry = None
