from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from core.fill_probability import (
    DEFAULT_TAU_MS,
    estimate_failure_penalty,
    expected_profit,
    fill_probability,
)
from core.scorer import rank_opportunities
from models.market import Exchange, Opportunity


def _make_opportunity(detected_at: datetime, net_spread: float = 100.0) -> Opportunity:
    return Opportunity(
        buy_exchange=Exchange.BINANCE,
        sell_exchange=Exchange.KRAKEN,
        buy_ask=100_000.0,
        sell_bid=100_200.0,
        gross_spread=200.0,
        net_spread=net_spread,
        score=0.0,
        detected_at=detected_at,
        available_qty=1.0,
        optimal_qty=1.0,
    )


# ---------------------------------------------------------------------------
# fill_probability — exponential decay
# ---------------------------------------------------------------------------

def test_fill_probability_is_one_at_zero_latency():
    assert fill_probability(0.0, tau_ms=50.0) == pytest.approx(1.0, rel=1e-12)


def test_fill_probability_is_one_over_e_at_one_tau():
    # P_fill(tau) = exp(-1) ≈ 0.367879
    assert fill_probability(50.0, tau_ms=50.0) == pytest.approx(1.0 / math.e, rel=1e-9)


def test_fill_probability_decays_monotonically_with_latency():
    p0 = fill_probability(0.0)
    p25 = fill_probability(25.0)
    p50 = fill_probability(50.0)
    p100 = fill_probability(100.0)
    assert p0 > p25 > p50 > p100
    assert p100 > 0.0


def test_fill_probability_raises_on_negative_latency():
    with pytest.raises(ValueError):
        fill_probability(-1.0)


def test_fill_probability_raises_on_non_positive_tau():
    with pytest.raises(ValueError):
        fill_probability(10.0, tau_ms=0.0)


# ---------------------------------------------------------------------------
# expected_profit — known-answer case computed by hand
# ---------------------------------------------------------------------------

def test_expected_profit_known_answer():
    # latency = 50ms == tau  -> P_fill = e^-1 = 0.367879441
    # E = P_fill * net_profit - (1 - P_fill) * penalty
    #   = 0.367879441 * 100 - 0.632120559 * 10
    #   = 36.7879441 - 6.32120559 = 30.4667385
    now = datetime(2026, 5, 29, 12, 0, 0, 50_000, tzinfo=timezone.utc)
    detected_at = now - timedelta(milliseconds=50.0)
    opp = _make_opportunity(detected_at, net_spread=100.0)

    result = expected_profit(opp, now, tau_ms=50.0, penalty=10.0)

    assert result == pytest.approx(30.4667385, rel=1e-6)


def test_expected_profit_equals_net_spread_at_zero_latency():
    # P_fill = 1 -> the penalty term vanishes, E[profit] == net_spread
    now = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
    opp = _make_opportunity(now, net_spread=100.0)

    result = expected_profit(opp, now, tau_ms=50.0, penalty=10.0)

    assert result == pytest.approx(100.0, rel=1e-9)


def test_estimate_failure_penalty_is_sum_of_taker_fees():
    # Binance taker 0.001 on 1 BTC @ 100k + Kraken taker 0.0026 on 1 BTC @ 100.2k
    opp = _make_opportunity(datetime(2026, 5, 29, tzinfo=timezone.utc))
    expected = 1.0 * 100_000.0 * 0.001 + 1.0 * 100_200.0 * 0.0026
    assert estimate_failure_penalty(opp) == pytest.approx(expected, rel=1e-9)


# ---------------------------------------------------------------------------
# scorer — fresh opportunity ranks above stale one with same spread
# ---------------------------------------------------------------------------

def test_fresh_opportunity_ranks_above_stale_with_same_spread():
    now = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
    fresh = _make_opportunity(now - timedelta(milliseconds=5.0), net_spread=100.0)
    stale = _make_opportunity(now - timedelta(milliseconds=300.0), net_spread=100.0)

    ranked = rank_opportunities([stale, fresh], now=now)

    assert ranked[0].detected_at == fresh.detected_at
    assert ranked[0].score > ranked[1].score


def test_stale_opportunity_scores_negative_when_penalty_dominates():
    # Old enough that P_fill is tiny -> dominated by the failure penalty term
    now = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
    stale = _make_opportunity(now - timedelta(milliseconds=500.0), net_spread=100.0)

    ranked = rank_opportunities([stale], now=now)

    assert ranked[0].score < 0.0
