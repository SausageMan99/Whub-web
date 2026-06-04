import pytest

from src import main as worker_main


class StopPolling(Exception):
    pass


def test_poll_with_backoff_uses_exponential_delays_for_consecutive_poll_errors():
    delays = []

    def failing_claim():
        raise RuntimeError("database unavailable")

    def recording_sleep(delay):
        delays.append(delay)
        if len(delays) == 5:
            raise StopPolling

    with pytest.raises(StopPolling):
        worker_main.poll_with_backoff(
            claim_func=failing_claim,
            process_func=lambda job: None,
            sleep_func=recording_sleep,
            base_delay=10,
        )

    assert delays == [10, 20, 40, 80, 160]


def test_poll_with_backoff_caps_exponential_backoff_at_300_seconds():
    delays = []

    def failing_claim():
        raise RuntimeError("database unavailable")

    def recording_sleep(delay):
        delays.append(delay)
        if len(delays) == 7:
            raise StopPolling

    with pytest.raises(StopPolling):
        worker_main.poll_with_backoff(
            claim_func=failing_claim,
            process_func=lambda job: None,
            sleep_func=recording_sleep,
            base_delay=10,
        )

    assert delays == [10, 20, 40, 80, 160, 300, 300]


def test_circuit_breaker_opens_after_10_consecutive_errors():
    now = [1_000.0]
    breaker = worker_main.CircuitBreaker(
        failure_threshold=10,
        recovery_timeout=300,
        time_func=lambda: now[0],
    )

    for _ in range(9):
        assert breaker.allow_request()
        breaker.record_failure()
        assert breaker.state == "closed"

    assert breaker.allow_request()
    breaker.record_failure()

    assert breaker.state == "open"
    assert not breaker.allow_request()


def test_circuit_breaker_transitions_to_half_open_after_recovery_timeout():
    now = [1_000.0]
    breaker = worker_main.CircuitBreaker(
        failure_threshold=2,
        recovery_timeout=300,
        time_func=lambda: now[0],
    )

    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == "open"

    now[0] += 299
    assert not breaker.allow_request()
    assert breaker.state == "open"

    now[0] += 1
    assert breaker.allow_request()
    assert breaker.state == "half-open"

    breaker.record_success()
    assert breaker.state == "closed"
    assert breaker.failure_count == 0
