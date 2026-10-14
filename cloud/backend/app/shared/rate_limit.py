"""Limitador de tasa en memoria, de ventana deslizante.

Alcanza para una sola réplica (la del despliegue actual). Con varias réplicas hay que moverlo
a un almacén compartido: cada proceso llevaría su propio conteo.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable

_SWEEP_THRESHOLD = 10_000


class SlidingWindowLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str) -> int | None:
        """Registra un intento. `None` si pasa; si no, segundos a esperar (para `Retry-After`)."""
        now = self._clock()
        if len(self._hits) > _SWEEP_THRESHOLD:
            self._sweep(now)
        window = self._hits.setdefault(key, deque())
        while window and window[0] <= now - self._window:
            window.popleft()
        if len(window) >= self._limit:
            return max(1, math.ceil(window[0] + self._window - now))
        window.append(now)
        return None

    def _sweep(self, now: float) -> None:
        cutoff = now - self._window
        for key in [k for k, w in self._hits.items() if not w or w[-1] <= cutoff]:
            del self._hits[key]
