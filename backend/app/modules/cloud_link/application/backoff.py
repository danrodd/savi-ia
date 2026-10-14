"""Espera entre reintentos (§5.6): `min(30 s × 2^n, 30 min)` ± 20 % de jitter.

Con `Retry-After` de Cloud se respeta ese valor (con un techo de una hora, para
que una cabecera descabellada no deje la instancia callada para siempre).
"""

import random

BASE_SECONDS = 30.0
MAX_SECONDS = 30 * 60.0
JITTER_RATIO = 0.2
RETRY_AFTER_CEILING_SECONDS = 3600.0
_MAX_EXPONENT = 10


def backoff_seconds(
    consecutive_failures: int,
    *,
    retry_after_seconds: float | None = None,
    rng: random.Random | None = None,
) -> float:
    """Espera antes del próximo intento. `consecutive_failures` es el número
    de fallos seguidos incluido el actual (el primero espera ~30 s)."""
    if retry_after_seconds is not None:
        return min(max(retry_after_seconds, 1.0), RETRY_AFTER_CEILING_SECONDS)
    exponent = min(max(consecutive_failures - 1, 0), _MAX_EXPONENT)
    base = min(BASE_SECONDS * (2**exponent), MAX_SECONDS)
    generator = rng or random
    jitter = generator.uniform(-JITTER_RATIO, JITTER_RATIO)
    return base * (1.0 + jitter)
