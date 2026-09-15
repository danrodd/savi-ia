"""Ventana deslizante del rate limit.

Con reloj inyectado: dormir de verdad haría una suite lenta y con fallos
intermitentes en máquinas cargadas.
"""

from __future__ import annotations

import pytest

from app.shared.rate_limit import RateLimitPolicy, SlidingWindowRateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def limiter(clock: FakeClock) -> SlidingWindowRateLimiter:
    return SlidingWindowRateLimiter(clock=clock)


POLICY = RateLimitPolicy(limit=3, window_seconds=60)


def test_allows_up_to_the_limit(limiter: SlidingWindowRateLimiter) -> None:
    for _ in range(3):
        assert limiter.check("a", POLICY).allowed


def test_blocks_over_the_limit(limiter: SlidingWindowRateLimiter) -> None:
    for _ in range(3):
        limiter.check("a", POLICY)

    decision = limiter.check("a", POLICY)

    assert not decision.allowed
    assert decision.retry_after_seconds == 60


def test_keys_are_independent(limiter: SlidingWindowRateLimiter) -> None:
    """Una IP saturada no puede dejar afuera a otra."""
    for _ in range(3):
        limiter.check("a", POLICY)

    assert limiter.check("b", POLICY).allowed


def test_window_slides(limiter: SlidingWindowRateLimiter, clock: FakeClock) -> None:
    for _ in range(3):
        limiter.check("a", POLICY)
    assert not limiter.check("a", POLICY).allowed

    clock.advance(61)

    assert limiter.check("a", POLICY).allowed


def test_rejected_requests_do_not_extend_the_window(
    limiter: SlidingWindowRateLimiter, clock: FakeClock
) -> None:
    """Si un rechazo contara, quien insiste se autobloquea para siempre."""
    for _ in range(3):
        limiter.check("a", POLICY)
    clock.advance(30)
    for _ in range(10):
        limiter.check("a", POLICY)  # todos rechazados

    clock.advance(31)  # pasaron 61 s desde los 3 aceptados

    assert limiter.check("a", POLICY).allowed


def test_retry_after_is_never_zero(limiter: SlidingWindowRateLimiter, clock: FakeClock) -> None:
    """Un `Retry-After: 0` invita a reintentar en el acto y volver a fallar."""
    for _ in range(3):
        limiter.check("a", POLICY)
    clock.advance(59.5)

    assert limiter.check("a", POLICY).retry_after_seconds >= 1


def test_blocks_after_consecutive_failures(limiter: SlidingWindowRateLimiter) -> None:
    for _ in range(5):
        limiter.record_failure("login:X", max_failures=5, block_seconds=900)

    decision = limiter.is_blocked("login:X")

    assert not decision.allowed
    assert decision.retry_after_seconds == 900


def test_does_not_block_before_reaching_the_limit(limiter: SlidingWindowRateLimiter) -> None:
    for _ in range(4):
        limiter.record_failure("login:X", max_failures=5, block_seconds=900)

    assert limiter.is_blocked("login:X").allowed


def test_success_clears_failures(limiter: SlidingWindowRateLimiter) -> None:
    """Equivocarse dos veces y después entrar bien no deja penalización."""
    for _ in range(4):
        limiter.record_failure("login:X", max_failures=5, block_seconds=900)

    limiter.record_success("login:X")
    for _ in range(4):
        limiter.record_failure("login:X", max_failures=5, block_seconds=900)

    assert limiter.is_blocked("login:X").allowed


def test_block_expires(limiter: SlidingWindowRateLimiter, clock: FakeClock) -> None:
    for _ in range(5):
        limiter.record_failure("login:X", max_failures=5, block_seconds=900)

    clock.advance(901)

    assert limiter.is_blocked("login:X").allowed


def test_purge_drops_idle_keys(limiter: SlidingWindowRateLimiter, clock: FakeClock) -> None:
    """Sin esto, un atacante rotando IP se lleva la memoria del proceso."""
    for key in ("a", "b", "c"):
        limiter.check(key, POLICY)

    clock.advance(3601)
    removed = limiter.purge(3600)

    assert removed == 3


def test_purge_keeps_active_keys(limiter: SlidingWindowRateLimiter, clock: FakeClock) -> None:
    limiter.check("vieja", POLICY)
    clock.advance(3601)
    limiter.check("nueva", POLICY)

    limiter.purge(3600)

    # La nueva conserva su registro: su cupo no se regala.
    assert limiter.check("nueva", POLICY).allowed
    assert limiter.check("nueva", POLICY).allowed
    assert not limiter.check("nueva", POLICY).allowed


def test_policy_rejects_nonsense() -> None:
    with pytest.raises(ValueError, match="límite"):
        RateLimitPolicy(limit=0, window_seconds=60)
    with pytest.raises(ValueError, match="límite"):
        RateLimitPolicy(limit=5, window_seconds=0)
