"""Ventana deslizante en memoria para limitar pedidos.

Por qué propia y no `slowapi`: son sesenta líneas para algo que necesita
exactamente dos cosas (contar por clave y bloquear por un rato), y agregar una
dependencia para eso tiene su propio costo. El estado vive en el proceso, que
es el modelo actual de SAVI (un solo worker de uvicorn). Cuando llegue SAVI
Servidor con varios procesos se reemplaza el store, no la lógica: `RateLimiter`
es la interfaz que el resto del código usa.

No usa `time.time()` sino `time.monotonic()`: un ajuste de hora del sistema
(NTP, cambio manual) no tiene por qué regalar ni negar pedidos.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    """Cuántos pedidos se permiten y en cuánto tiempo."""

    limit: int
    window_seconds: float

    def __post_init__(self) -> None:
        if self.limit < 1 or self.window_seconds <= 0:
            raise ValueError("Una política necesita límite >= 1 y ventana > 0.")


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    # Segundos hasta que el pedido rechazado sería aceptado. Va al header
    # `Retry-After` para que el cliente no reintente a ciegas.
    retry_after_seconds: int = 0


class SlidingWindowRateLimiter:
    """Cuenta pedidos por clave dentro de una ventana móvil.

    Thread-safe: uvicorn atiende el loop en un hilo, pero las dependencias
    síncronas de FastAPI corren en el threadpool, así que dos pedidos pueden
    tocar esto a la vez.
    """

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._blocked_until: dict[str, float] = {}
        self._failures: dict[str, int] = {}
        self._lock = threading.Lock()
        # Inyectable para testear sin dormir de verdad.
        self._now: Callable[[], float] = clock or time.monotonic

    # ── Conteo por ventana ────────────────────────────────────────────────

    def check(self, key: str, policy: RateLimitPolicy) -> RateLimitDecision:
        """Registra el pedido y dice si pasa. Un pedido rechazado **no**
        cuenta para la ventana: si contara, quien insiste se auto-extiende el
        bloqueo para siempre y nunca vuelve a entrar."""
        now = self._now()
        with self._lock:
            blocked = self._blocked_until.get(key)
            if blocked is not None:
                if now < blocked:
                    return RateLimitDecision(False, _ceil_seconds(blocked - now))
                del self._blocked_until[key]

            hits = self._hits.setdefault(key, deque())
            cutoff = now - policy.window_seconds
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= policy.limit:
                libre_en = hits[0] + policy.window_seconds - now
                return RateLimitDecision(False, _ceil_seconds(libre_en))

            hits.append(now)
            return RateLimitDecision(True)

    # ── Bloqueo por fallos consecutivos ───────────────────────────────────

    def record_failure(self, key: str, *, max_failures: int, block_seconds: float) -> None:
        """Suma un fallo y bloquea la clave al llegar al tope.

        Para el login: la ventana sola no frena un ataque lento y constante,
        y las contraseñas del ERP son MD5 sin sal."""
        with self._lock:
            count = self._failures.get(key, 0) + 1
            if count >= max_failures:
                self._failures.pop(key, None)
                self._blocked_until[key] = self._now() + block_seconds
            else:
                self._failures[key] = count

    def record_success(self, key: str) -> None:
        """Un acierto limpia el contador y el bloqueo: quien se equivocó dos
        veces y después entró bien no arrastra penalización."""
        with self._lock:
            self._failures.pop(key, None)
            self._blocked_until.pop(key, None)

    def is_blocked(self, key: str) -> RateLimitDecision:
        with self._lock:
            blocked = self._blocked_until.get(key)
            now = self._now()
            if blocked is None or now >= blocked:
                return RateLimitDecision(True)
            return RateLimitDecision(False, _ceil_seconds(blocked - now))

    # ── Mantenimiento ─────────────────────────────────────────────────────

    def purge(self, older_than_seconds: float) -> int:
        """Descarta claves sin actividad reciente.

        Sin esto el diccionario crece con cada IP o login distinto que
        aparezca: un atacante rotando logins se lleva la memoria del proceso.
        Devuelve cuántas claves se limpiaron."""
        now = self._now()
        removed = 0
        with self._lock:
            for key in list(self._hits):
                hits = self._hits[key]
                while hits and hits[0] <= now - older_than_seconds:
                    hits.popleft()
                if not hits and key not in self._blocked_until and key not in self._failures:
                    del self._hits[key]
                    removed += 1
            for key, until in list(self._blocked_until.items()):
                if now >= until:
                    del self._blocked_until[key]
        return removed

    def reset(self) -> None:
        """Solo para tests y para el arranque."""
        with self._lock:
            self._hits.clear()
            self._blocked_until.clear()
            self._failures.clear()


def _ceil_seconds(seconds: float) -> int:
    """Siempre hacia arriba y mínimo 1: un `Retry-After: 0` invita a
    reintentar en el acto y a volver a ser rechazado."""
    return max(1, int(seconds) + (1 if seconds % 1 else 0))
