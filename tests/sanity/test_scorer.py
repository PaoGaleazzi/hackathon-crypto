from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.scorer import rank_opportunities, score_opportunity
from models.market import Exchange, Opportunity

_NOW = datetime(2026, 5, 29, 6, 0, 0, tzinfo=timezone.utc)


def _opp(
    net_spread: float = 100.0,
    buy_ask: float = 70_000.0,
    available_qty: float = 1.0,
    optimal_qty: float | None = None,
    detected_ms_ago: float = 10.0,
) -> Opportunity:
    return Opportunity(
        buy_exchange=Exchange.BINANCE,
        sell_exchange=Exchange.KRAKEN,
        buy_ask=buy_ask,
        sell_bid=buy_ask + 500.0,
        gross_spread=net_spread + 50.0,
        net_spread=net_spread,
        score=0.0,
        detected_at=_NOW - timedelta(milliseconds=detected_ms_ago),
        available_qty=available_qty,
        optimal_qty=optimal_qty if optimal_qty is not None else available_qty,
    )


# ── score_opportunity ─────────────────────────────────────────────────────────

def test_score_higher_net_spread_wins_with_equal_latency():
    # Opp A: net=200, buy_ask=70_000, qty=1.0, latency=10ms
    #   pct = 200/70_000 = 0.002857, score = 0.002857/10 = 0.0002857
    # Opp B: net=100, same params
    #   pct = 100/70_000 = 0.001429, score = 0.001429/10 = 0.0001429
    score_a = score_opportunity(_opp(net_spread=200.0, detected_ms_ago=10.0), _NOW)
    score_b = score_opportunity(_opp(net_spread=100.0, detected_ms_ago=10.0), _NOW)
    assert score_a == pytest.approx(0.0002857, rel=1e-3)
    assert score_b == pytest.approx(0.0001429, rel=1e-3)
    assert score_a > score_b


def test_score_stale_opportunity_ranks_lower_than_fresh():
    # Same spread, latency 10ms vs 510ms
    # fresh  = (100/70_000) / 10  ≈ 0.0001429
    # stale  = (100/70_000) / 510 ≈ 0.00000280
    score_fresh = score_opportunity(_opp(net_spread=100.0, detected_ms_ago=10.0), _NOW)
    score_stale = score_opportunity(_opp(net_spread=100.0, detected_ms_ago=510.0), _NOW)
    assert score_fresh > score_stale
    assert score_stale == pytest.approx(100.0 / 70_000 / 510.0, rel=1e-3)


def test_score_liquidity_below_1_when_optimal_exceeds_available():
    # available=0.3, optimal=1.0 → liquidity=0.3 → lower score than full liquidity
    score_partial = score_opportunity(_opp(available_qty=0.3, optimal_qty=1.0), _NOW)
    score_full = score_opportunity(_opp(available_qty=0.3, optimal_qty=0.3), _NOW)
    assert score_partial < score_full
    # liquidity_score=0.3 vs 1.0, all else equal → ratio should be 0.3
    assert score_partial == pytest.approx(score_full * 0.3, rel=1e-6)


def test_score_latency_floor_at_1ms_when_detected_now():
    # detected_at = now → latency = 0ms → floored to 1ms → finite score
    opp = _opp(detected_ms_ago=0.0)
    score = score_opportunity(opp, _NOW)
    assert score > 0
    assert score == pytest.approx(score_opportunity(_opp(detected_ms_ago=1.0), _NOW), rel=1e-6)


def test_score_optimal_qty_zero_uses_liquidity_1():
    # optimal_qty=0 edge case → liquidity_score=1.0, no ZeroDivisionError
    opp = _opp(available_qty=0.5, optimal_qty=0.0)
    score = score_opportunity(opp, _NOW)
    assert score == pytest.approx(score_opportunity(_opp(available_qty=0.5, optimal_qty=0.5), _NOW))


# ── rank_opportunities ────────────────────────────────────────────────────────

def test_rank_returns_empty_on_empty_list():
    assert rank_opportunities([], now=_NOW) == []


def test_rank_single_opportunity_returns_it_with_score_set():
    opp = _opp(net_spread=100.0)
    result = rank_opportunities([opp], now=_NOW)
    assert len(result) == 1
    assert result[0].score > 0


def test_rank_order_descending_by_score():
    # A: big spread, fresh. B: small spread, fresh. C: big spread, stale.
    opp_a = _opp(net_spread=200.0, detected_ms_ago=10.0)
    opp_b = _opp(net_spread=100.0, detected_ms_ago=10.0)
    opp_c = _opp(net_spread=200.0, detected_ms_ago=510.0)

    result = rank_opportunities([opp_c, opp_b, opp_a], now=_NOW)

    assert result[0].net_spread == pytest.approx(200.0)
    assert result[0].score > result[1].score > result[2].score


def test_rank_updates_score_field_on_returned_objects():
    opp = _opp(net_spread=100.0)
    assert opp.score == 0.0
    result = rank_opportunities([opp], now=_NOW)
    assert result[0].score != 0.0


def test_rank_does_not_mutate_input_list():
    opp = _opp(net_spread=100.0)
    original_score = opp.score
    rank_opportunities([opp], now=_NOW)
    assert opp.score == original_score
