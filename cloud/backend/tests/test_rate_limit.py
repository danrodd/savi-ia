from __future__ import annotations

from app.shared.rate_limit import SlidingWindowLimiter


class _Now:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_allows_up_to_limit_then_reports_retry_after() -> None:
    now = _Now()
    limiter = SlidingWindowLimiter(3, 60, now)
    assert [limiter.hit("a") for _ in range(3)] == [None, None, None]
    now.t += 10
    assert limiter.hit("a") == 50


def test_window_slides_and_keys_are_independent() -> None:
    now = _Now()
    limiter = SlidingWindowLimiter(1, 60, now)
    assert limiter.hit("a") is None
    assert limiter.hit("b") is None
    assert limiter.hit("a") == 60
    now.t += 60
    assert limiter.hit("a") is None


def test_retry_after_is_at_least_one_second() -> None:
    now = _Now()
    limiter = SlidingWindowLimiter(1, 60, now)
    limiter.hit("a")
    now.t += 59.9
    assert limiter.hit("a") == 1
