from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from core.circuit_breaker import (
    COOLDOWN_SECS,
    LOSS_THRESHOLD_USD,
    STALE_THRESHOLD,
    CircuitBreaker,
    CircuitBreakerState,
)
from models.market import Exchange
from models.trade import Trade

_NOW = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)


# ── helpers ───────────────────────────────────────────────────────────────────

def _trade(status: str, net_profit: float = 0.0) -> Trade:
    return Trade(
        id=str(uuid.uuid4()),
        buy_exchange=Exchange.BINANCE,
        sell_exchange=Exchange.KRAKEN,
        qty=0.1,
        buy_price=70_000.0,
        sell_price=70_500.0,
        fee_buy=7.0,
        fee_sell=18.33,
        slippage_est=0.0,
        net_profit=net_profit,
        status=status,  # type: ignore[arg-type]
        ws_received_at=_NOW,
        decision_at=_NOW,
        latency_ms=42.0,
        executed_at=_NOW,
    )


# ── initial state ─────────────────────────────────────────────────────────────

def test_initial_state_is_closed():
    cb = CircuitBreaker()
    assert cb.state == CircuitBreakerState.CLOSED


def test_allows_trade_when_closed():
    cb = CircuitBreaker()
    assert cb.allow_trade(now=_NOW) is True


# ── stale threshold ───────────────────────────────────────────────────────────

def test_opens_after_stale_threshold_consecutive_trades():
    # STALE_THRESHOLD = 3; three consecutive ABORTED_STALE must open the breaker
    cb = CircuitBreaker()
    for _ in range(STALE_THRESHOLD):
        cb.record_trade(_trade("ABORTED_STALE"), now=_NOW)
    assert cb.state == CircuitBreakerState.OPEN


def test_third_stale_trade_is_the_trip():
    cb = CircuitBreaker()
    for i in range(STALE_THRESHOLD - 1):
        tripped = cb.record_trade(_trade("ABORTED_STALE"), now=_NOW)
        assert tripped is False, f"tripped early on trade {i + 1}"
    tripped = cb.record_trade(_trade("ABORTED_STALE"), now=_NOW)
    assert tripped is True


def test_stale_counter_resets_on_executed_trade():
    # 2 stale + 1 executed resets counter → must need 3 more stale to trip
    cb = CircuitBreaker()
    cb.record_trade(_trade("ABORTED_STALE"), now=_NOW)
    cb.record_trade(_trade("ABORTED_STALE"), now=_NOW)
    cb.record_trade(_trade("EXECUTED", net_profit=50.0), now=_NOW)
    # Only 2 stale since reset, not at threshold
    assert cb.state == CircuitBreakerState.CLOSED


def test_two_stale_does_not_trip():
    cb = CircuitBreaker()
    for _ in range(STALE_THRESHOLD - 1):
        cb.record_trade(_trade("ABORTED_STALE"), now=_NOW)
    assert cb.state == CircuitBreakerState.CLOSED


# ── loss threshold ────────────────────────────────────────────────────────────

def test_opens_when_rolling_loss_exceeds_threshold():
    # Known answer: -51 USD in window → trip
    # LOSS_THRESHOLD_USD = 50.0; rolling_loss ≤ -50 triggers
    cb = CircuitBreaker()
    cb.record_trade(_trade("EXECUTED", net_profit=-51.0), now=_NOW)
    assert cb.state == CircuitBreakerState.OPEN


def test_does_not_open_when_loss_below_threshold():
    # -49.99 USD is less than threshold — stays CLOSED
    cb = CircuitBreaker()
    cb.record_trade(_trade("EXECUTED", net_profit=-49.99), now=_NOW)
    assert cb.state == CircuitBreakerState.CLOSED


def test_opens_when_losses_accumulate_across_trades():
    # Known: -30 + -30 = -60 → trip (window = 5 min, both in window)
    cb = CircuitBreaker()
    cb.record_trade(_trade("EXECUTED", net_profit=-30.0), now=_NOW)
    assert cb.state == CircuitBreakerState.CLOSED
    cb.record_trade(_trade("EXECUTED", net_profit=-30.0), now=_NOW)
    assert cb.state == CircuitBreakerState.OPEN


def test_old_losses_evicted_from_window():
    # Loss at T=0: -60 USD, recorded at T=0.
    # At T=301s (past 300s window): loss should be evicted → no trip.
    cb = CircuitBreaker()
    t0 = _NOW
    t_after_window = _NOW + timedelta(seconds=301)
    cb.record_trade(_trade("EXECUTED", net_profit=-60.0), now=t0)
    # Manually advance time: the next call evicts t0 entry
    cb.record_trade(_trade("EXECUTED", net_profit=0.0), now=t_after_window)
    assert cb.state == CircuitBreakerState.CLOSED


# ── block when open ───────────────────────────────────────────────────────────

def test_blocks_trade_when_open():
    cb = CircuitBreaker()
    for _ in range(STALE_THRESHOLD):
        cb.record_trade(_trade("ABORTED_STALE"), now=_NOW)
    assert cb.state == CircuitBreakerState.OPEN
    assert cb.allow_trade(now=_NOW) is False


# ── cooldown and HALF_OPEN ────────────────────────────────────────────────────

def test_transitions_to_half_open_after_cooldown():
    # Known: COOLDOWN_SECS = 60; after 60s OPEN → HALF_OPEN
    cb = CircuitBreaker()
    for _ in range(STALE_THRESHOLD):
        cb.record_trade(_trade("ABORTED_STALE"), now=_NOW)
    assert cb.state == CircuitBreakerState.OPEN

    t_after_cooldown = _NOW + timedelta(seconds=COOLDOWN_SECS)
    cb.allow_trade(now=t_after_cooldown)  # triggers _maybe_transition
    assert cb.state == CircuitBreakerState.HALF_OPEN


def test_half_open_allows_trade():
    cb = CircuitBreaker()
    for _ in range(STALE_THRESHOLD):
        cb.record_trade(_trade("ABORTED_STALE"), now=_NOW)
    t_after = _NOW + timedelta(seconds=COOLDOWN_SECS)
    assert cb.allow_trade(now=t_after) is True


def test_half_open_closes_on_successful_trade():
    cb = CircuitBreaker()
    for _ in range(STALE_THRESHOLD):
        cb.record_trade(_trade("ABORTED_STALE"), now=_NOW)
    t_after = _NOW + timedelta(seconds=COOLDOWN_SECS)
    cb.allow_trade(now=t_after)  # → HALF_OPEN
    cb.record_trade(_trade("EXECUTED", net_profit=10.0), now=t_after)
    assert cb.state == CircuitBreakerState.CLOSED


def test_half_open_reopens_on_failure():
    cb = CircuitBreaker()
    for _ in range(STALE_THRESHOLD):
        cb.record_trade(_trade("ABORTED_STALE"), now=_NOW)
    t_after = _NOW + timedelta(seconds=COOLDOWN_SECS)
    cb.allow_trade(now=t_after)  # → HALF_OPEN
    tripped = cb.record_trade(_trade("ABORTED_STALE"), now=t_after)
    assert tripped is True
    assert cb.state == CircuitBreakerState.OPEN


def test_half_open_reopen_resets_cooldown_timer():
    cb = CircuitBreaker()
    for _ in range(STALE_THRESHOLD):
        cb.record_trade(_trade("ABORTED_STALE"), now=_NOW)
    t_half = _NOW + timedelta(seconds=COOLDOWN_SECS)
    cb.allow_trade(now=t_half)  # → HALF_OPEN
    cb.record_trade(_trade("ABORTED_STALE"), now=t_half)  # → OPEN again

    # Countdown at t_half should be ~60s (just reopened)
    countdown = cb.countdown_secs(now=t_half)
    assert countdown == pytest.approx(COOLDOWN_SECS, abs=1)


# ── countdown ─────────────────────────────────────────────────────────────────

def test_countdown_returns_none_when_closed():
    cb = CircuitBreaker()
    assert cb.countdown_secs(now=_NOW) is None


def test_countdown_known_answer():
    # Open at T=0, check at T=20s → countdown = 40s
    cb = CircuitBreaker()
    for _ in range(STALE_THRESHOLD):
        cb.record_trade(_trade("ABORTED_STALE"), now=_NOW)
    t_20s = _NOW + timedelta(seconds=20)
    countdown = cb.countdown_secs(now=t_20s)
    assert countdown == pytest.approx(40.0, abs=0.01)


# ── as_dict ───────────────────────────────────────────────────────────────────

def test_as_dict_reflects_state():
    cb = CircuitBreaker()
    cb.record_trade(_trade("EXECUTED", net_profit=-30.0), now=_NOW)
    d = cb.as_dict(now=_NOW)
    assert d["state"] == "CLOSED"
    assert d["rolling_loss_usd"] == pytest.approx(-30.0, abs=0.01)
    assert d["consecutive_stale"] == 0
    assert d["countdown_secs"] is None
