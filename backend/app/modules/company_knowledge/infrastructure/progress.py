"""Avance del documento que se está procesando ahora mismo.

En memoria y no en la base a propósito:

- El avance solo significa algo **mientras** el documento se procesa, y eso
  pasa en este proceso (el worker de ingesta es de un solo hilo, igual que el
  índice vive en memoria). Si SAVI se reinicia, el documento vuelve a la cola
  y el avance viejo no sirve para nada.
- Persistirlo costaría un `UPDATE` por lote de fragmentos y una migración,
  para un dato efímero que nadie consulta después.

Es thread-safe porque lo escribe el hilo del executor de ingesta y lo lee el
event loop al responder el listado.

Vive acá y no dentro de `processing/` a propósito: ese paquete exporta el
worker, que importa los casos de uso, que a su vez necesitan este registro.
Ponerlo adentro cerraba el ciclo de imports.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Progress:
    done: int
    total: int

    @property
    def percent(self) -> int:
        if self.total <= 0:
            return 0
        return min(100, round(self.done * 100 / self.total))


class ProgressRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_document: dict[UUID, Progress] = {}

    def start(self, document_id: UUID, total: int) -> None:
        with self._lock:
            self._by_document[document_id] = Progress(0, total)

    def advance(self, document_id: UUID, done: int) -> None:
        with self._lock:
            actual = self._by_document.get(document_id)
            if actual is not None:
                self._by_document[document_id] = Progress(done, actual.total)

    def finish(self, document_id: UUID) -> None:
        with self._lock:
            self._by_document.pop(document_id, None)

    def get(self, document_id: UUID) -> Progress | None:
        with self._lock:
            return self._by_document.get(document_id)

    def clear(self) -> None:
        with self._lock:
            self._by_document.clear()


# Uno por proceso, como el índice y el worker.
_registry = ProgressRegistry()


def get_progress_registry() -> ProgressRegistry:
    return _registry
