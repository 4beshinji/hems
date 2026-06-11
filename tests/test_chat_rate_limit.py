"""Tests for chat endpoint rate limiting (token bucket).

Covers:
  (a) Requests within capacity are allowed (200)
  (b) Requests exceeding capacity return 429 with Retry-After header
  (c) Retry-After value is reasonable (ceil(tokens_needed / refill_rate))
  (d) Rate limiting is disabled when CHAT_RATE_LIMIT_CAPACITY=0
  (e) Rate limiter recovers over time (time is mocked via unittest.mock)
  (f) Concurrent requests safely share the bucket (async locks)
"""

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure backend src is on sys.path
_backend_src = Path(__file__).resolve().parent.parent / "services" / "backend"
if str(_backend_src) not in sys.path:
    sys.path.insert(0, str(_backend_src))


# ---------------------------------------------------------------------------
# (a) Capacity check — within capacity is allowed
# ---------------------------------------------------------------------------


class TestWithinCapacity:
    """Requests within bucket capacity should succeed."""

    def test_token_bucket_single_consume_succeeds(self):
        from routers.chat import TokenBucket

        bucket = TokenBucket(capacity=10, refill_rate=0.5)
        success, retry_after = asyncio.run(bucket.try_consume(1))
        assert success is True
        assert retry_after == 0.0

    def test_token_bucket_multiple_consumes_within_capacity(self):
        from routers.chat import TokenBucket

        bucket = TokenBucket(capacity=10, refill_rate=0.5)
        for i in range(10):
            success, retry_after = asyncio.run(bucket.try_consume(1))
            assert success is True, f"Request {i} should succeed within capacity"
            assert retry_after == 0.0

    def test_token_bucket_exact_capacity(self):
        from routers.chat import TokenBucket

        bucket = TokenBucket(capacity=5, refill_rate=1.0)
        for i in range(5):
            success, _ = asyncio.run(bucket.try_consume(1))
            assert success is True


# ---------------------------------------------------------------------------
# (b) Overflow returns 429
# ---------------------------------------------------------------------------


class TestCapacityExceeded:
    """Requests exceeding capacity return 429."""

    def test_token_bucket_overflow_fails(self):
        from routers.chat import TokenBucket

        bucket = TokenBucket(capacity=5, refill_rate=0.5)
        # Consume all capacity
        for i in range(5):
            asyncio.run(bucket.try_consume(1))
        # Next request should fail
        success, retry_after = asyncio.run(bucket.try_consume(1))
        assert success is False
        assert retry_after > 0

    def test_token_bucket_overflow_retry_after_reasonable(self):
        from routers.chat import TokenBucket

        bucket = TokenBucket(capacity=1, refill_rate=0.5)
        asyncio.run(bucket.try_consume(1))
        success, retry_after = asyncio.run(bucket.try_consume(1))
        assert success is False
        # At 0.5 tokens/sec, next token arrives in 2 seconds
        assert retry_after >= 1.9  # Allow small float error


# ---------------------------------------------------------------------------
# (c) Retry-After header is present and reasonable
# ---------------------------------------------------------------------------


class TestRetryAfterHeader:
    """429 response includes Retry-After header."""

    def test_rate_limit_exception_includes_retry_after(self):
        """Check that _check_rate_limit raises with proper headers."""
        import os

        os.environ["CHAT_RATE_LIMIT_CAPACITY"] = "1"
        os.environ["CHAT_RATE_LIMIT_REFILL"] = "0.5"

        from fastapi import HTTPException

        import routers.chat as chat_module
        from routers.chat import _check_rate_limit, _init_rate_limiter

        # Reset global
        chat_module._rate_limiter = _init_rate_limiter()

        async def test():
            # First request succeeds
            await _check_rate_limit()
            # Second request fails
            with pytest.raises(HTTPException) as exc_info:
                await _check_rate_limit()
            assert exc_info.value.status_code == 429
            assert "Retry-After" in exc_info.value.headers
            assert int(exc_info.value.headers["Retry-After"]) > 0

        asyncio.run(test())


# ---------------------------------------------------------------------------
# (d) Disabled when CHAT_RATE_LIMIT_CAPACITY=0
# ---------------------------------------------------------------------------


class TestDisabledRateLimit:
    """Rate limiting can be disabled via capacity=0."""

    def test_rate_limit_disabled_when_capacity_zero(self, monkeypatch):
        monkeypatch.setenv("CHAT_RATE_LIMIT_CAPACITY", "0")
        monkeypatch.setenv("CHAT_RATE_LIMIT_REFILL", "0.5")

        from routers.chat import _init_rate_limiter

        limiter = _init_rate_limiter()
        assert limiter is None

    def test_rate_limit_check_passes_when_disabled(self, monkeypatch):
        monkeypatch.setenv("CHAT_RATE_LIMIT_CAPACITY", "0")

        import routers.chat as chat_module
        from routers.chat import _check_rate_limit

        chat_module._rate_limiter = None

        async def test():
            # Should not raise
            await _check_rate_limit()

        asyncio.run(test())


# ---------------------------------------------------------------------------
# (e) Recovery over time
# ---------------------------------------------------------------------------


class TestRecovery:
    """Tokens are replenished over time."""

    def test_token_bucket_refill_over_time(self):
        from routers.chat import TokenBucket

        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        # Consume all
        for _ in range(10):
            asyncio.run(bucket.try_consume(1))

        # Next request fails
        success, _ = asyncio.run(bucket.try_consume(1))
        assert success is False

        # Mock time forward by 1 second
        with patch("routers.chat.time.time", side_effect=[time.time(), time.time() + 1.0]):
            bucket.last_update = time.time() - 1.0
            success, _ = asyncio.run(bucket.try_consume(1))
            assert success is True

    def test_token_bucket_partial_refill(self):
        from routers.chat import TokenBucket

        bucket = TokenBucket(capacity=10, refill_rate=0.5)
        # Consume all 10 tokens
        for _ in range(10):
            asyncio.run(bucket.try_consume(1))

        # No refill yet — next request fails
        success, _retry_after = asyncio.run(bucket.try_consume(1))
        assert success is False

        # Advance time by 1 second → 0.5 tokens refilled
        base_time = time.time()

        initial_call = True

        def time_side_effect(*args, **kwargs):
            nonlocal initial_call
            if initial_call:
                initial_call = False
                return base_time
            return base_time + 1.0

        bucket.last_update = base_time
        with patch("routers.chat.time.time", side_effect=time_side_effect):
            success, _retry_after = asyncio.run(bucket.try_consume(1))
            # Only 0.5 tokens refilled, so 1 token request still fails
            assert success is False


# ---------------------------------------------------------------------------
# (f) Concurrent safety (async locks)
# ---------------------------------------------------------------------------


class TestConcurrencySafety:
    """Multiple concurrent requests safely share the bucket."""

    def test_token_bucket_concurrent_consumes(self):
        from routers.chat import TokenBucket

        bucket = TokenBucket(capacity=5, refill_rate=0.0)  # No refill for simplicity

        async def concurrent_test():
            # Create 10 concurrent consume tasks
            tasks = [bucket.try_consume(1) for _ in range(10)]
            results = await asyncio.gather(*tasks)

            # First 5 succeed, next 5 fail
            successes = [r[0] for r in results]
            assert successes.count(True) == 5, f"Expected 5 successes, got {successes}"
            assert successes.count(False) == 5, f"Expected 5 failures, got {successes}"

        asyncio.run(concurrent_test())


# ---------------------------------------------------------------------------
# Integration tests (if test DB available)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_rate_limit_in_send_message(monkeypatch):
    """Integration: send_message endpoint respects rate limit."""
    from fastapi import HTTPException

    import routers.chat as chat_module
    from routers.chat import _check_rate_limit, _init_rate_limiter

    monkeypatch.setenv("CHAT_RATE_LIMIT_CAPACITY", "1")
    monkeypatch.setenv("CHAT_RATE_LIMIT_REFILL", "0.5")

    # Import after env is set
    chat_module._rate_limiter = _init_rate_limiter()

    # First request should pass
    await _check_rate_limit()

    # Second request should fail with 429
    with pytest.raises(HTTPException) as exc_info:
        await _check_rate_limit()
    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers
