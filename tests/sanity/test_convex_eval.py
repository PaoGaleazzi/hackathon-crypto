from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.convex_eval import (
    best_cycle_edge,
    compare_strategies,
    default_taker_fees,
    render_comparison,
)
from models.market import BBO, Exchange

_NOW = datetime(2026, 5, 30, 6, 0, 0, tzinfo=timezone.utc)


def _bbo(exchange: Exchange, bid: float, ask: float, qty: float = 1.0, t=_NOW) -> BBO:
    return BBO(
        exchange=exchange,
        bid=bid,
        ask=ask,
        bid_qty=qty,
        ask_qty=qty,
        ws_received_at=t,
        normalized_at=t,
    )


def _fake_clock():
    """Deterministic monotonic clock (1 ms per call) so latency is reproducible."""
    ticks = iter(range(10_000))
    return lambda: next(ticks) / 1000.0


# ── brute-force edge matches the convex cost model ───────────────────────────────


def test_best_cycle_edge_matches_hand_calc():
    state = {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=99_990.0, ask=100_000.0),
        Exchange.KRAKEN: _bbo(Exchange.KRAKEN, bid=100_500.0, ask=100_510.0),
    }
    fees = default_taker_fees()
    edge = best_cycle_edge(state, fees, stablecoin_cost=0.0)

    assert edge.buy_exchange == Exchange.BINANCE
    assert edge.sell_exchange == Exchange.KRAKEN
    # Same multiplier as the triangular/convex hand calc.
    assert edge.multiplier == pytest.approx(0.999 * 0.9974 * 1.005, rel=1e-9)
    assert edge.profit_usd == pytest.approx(100_000.0 * (edge.multiplier - 1.0), rel=1e-9)


def test_best_cycle_edge_no_arbitrage():
    state = {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=99_990.0, ask=100_000.0),
        Exchange.KRAKEN: _bbo(Exchange.KRAKEN, bid=99_980.0, ask=99_995.0),
    }
    edge = best_cycle_edge(state, default_taker_fees(), stablecoin_cost=0.0)

    assert edge.multiplier <= 1.0
    assert edge.profit_usd <= 0.0


# ── convex vs brute-force agreement over a stream ────────────────────────────────


def _arb_stream():
    """Two ticks: the first builds a second venue (decidable from there), creating a
    clear Binance→Kraken cross; the rest stay crossed."""
    return [
        _bbo(Exchange.BINANCE, bid=99_990.0, ask=100_000.0, t=_NOW),
        _bbo(Exchange.KRAKEN, bid=100_500.0, ask=100_510.0, t=_NOW + timedelta(milliseconds=1)),
        _bbo(Exchange.KRAKEN, bid=100_500.0, ask=100_510.0, t=_NOW + timedelta(milliseconds=2)),
    ]


def test_compare_detects_agreement_on_real_arb():
    cmp = compare_strategies(
        _arb_stream(), stablecoin_cost=0.0, clock=_fake_clock()
    )

    assert cmp.state_ready == 2          # first tick has only 1 venue
    assert cmp.both_arb == 2
    assert cmp.classic_only == 0
    assert cmp.convex_only == 0
    assert cmp.mismatches == []
    assert cmp.consistency == 1.0
    # Same best pair found by both detectors.
    assert cmp.direction_matches == cmp.direction_total == 2


def test_compare_agrees_on_no_arbitrage():
    stream = [
        _bbo(Exchange.BINANCE, bid=99_990.0, ask=100_000.0, t=_NOW),
        _bbo(Exchange.KRAKEN, bid=99_980.0, ask=99_995.0, t=_NOW + timedelta(milliseconds=1)),
    ]
    cmp = compare_strategies(stream, stablecoin_cost=0.0, clock=_fake_clock())

    assert cmp.both_none == 1
    assert cmp.both_arb == 0
    assert cmp.convex_no_arb_certs == 1
    assert cmp.brute_agrees_no_arb == 1
    assert cmp.mismatches == []
    assert cmp.consistency == 1.0


def test_compare_records_solver_latency_per_decidable_tick():
    cmp = compare_strategies(_arb_stream(), stablecoin_cost=0.0, clock=_fake_clock())

    # One latency sample per decidable tick.
    assert len(cmp.solve_latencies_ms) == cmp.state_ready == 2
    assert all(x >= 0 for x in cmp.solve_latencies_ms)


def test_fee_multiplier_lifts_detections():
    # A thin cross that clears taker fees only once they are scaled down.
    state_stream = [
        _bbo(Exchange.BINANCE, bid=99_990.0, ask=100_000.0, t=_NOW),
        _bbo(Exchange.OKX, bid=100_120.0, ask=100_130.0, t=_NOW + timedelta(milliseconds=1)),
    ]
    full = compare_strategies(state_stream, stablecoin_cost=0.0, clock=_fake_clock())
    cheap = compare_strategies(
        state_stream, fee_multiplier=0.1, stablecoin_cost=0.0, clock=_fake_clock()
    )

    # Both quoted in USDT: 100120·(1-fee)² vs 100000. At full Binance/OKX taker
    # (0.1% each) the ~120 USD edge is eaten; at 0.1× fees it survives.
    assert full.both_none == 1
    assert cheap.both_arb == 1
    # Whatever the tier, convex and brute never genuinely disagree.
    assert full.mismatches == [] and cheap.mismatches == []


def test_render_comparison_answers_three_questions():
    cmp = compare_strategies(_arb_stream(), stablecoin_cost=0.0, clock=_fake_clock())
    report = render_comparison(cmp, source="unit")

    assert "detection consistency" in report
    assert "no-arbitrage certificate consistency" in report
    assert "solver latency per tick" in report
    assert "GENUINE MISMATCHES          : 0" in report


def test_empty_state_is_safely_consistent():
    cmp = compare_strategies([], clock=_fake_clock())

    assert cmp.state_ready == 0
    assert cmp.consistency == 1.0
    assert cmp.mismatches == []
