from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.fees import calculate_net_spread
from core.sizer import (
    InsufficientBalanceError,
    OptimalSizer,
    estimate_market_impact,
)
from models.market import Exchange, Opportunity

_NOW = datetime(2026, 5, 29, 6, 0, 0, tzinfo=timezone.utc)
_HUGE_BALANCE = 1_000_000.0  # USDT, large enough to never bind

# Net spread per unit (USDT/BTC). The sizer's linear edge `s` is whatever
# calculate_net_spread returns at qty=1.0 — gross minus the four cost components
# (taker fees, withdrawal, latency; slippage is 0 here since no depth is passed).
# We derive `s` from the same source of truth instead of hardcoding it, so these
# known-answer tests for q* = s/(2λ) stay correct as the fee model evolves.
# buy_ask=50_000, sell_bid=51_000 → gross/unit = 1_000.
_S_BINANCE_KRAKEN = calculate_net_spread(
    Exchange.BINANCE, Exchange.KRAKEN, 50_000.0, 51_000.0, 1.0
)  # ≈ 779.79
_S_BINANCE_OKX = calculate_net_spread(
    Exchange.BINANCE, Exchange.OKX, 50_000.0, 51_000.0, 1.0
)  # ≈ 870.58


def _opp(
    buy_ask: float = 50_000.0,
    sell_bid: float = 51_000.0,
    available_qty: float = 1.0,
    buy_exchange: Exchange = Exchange.BINANCE,
    sell_exchange: Exchange = Exchange.KRAKEN,
) -> Opportunity:
    # net_spread / gross_spread / score are recomputed by the sizer from prices,
    # so the stored values here only need to be internally consistent placeholders.
    return Opportunity(
        buy_exchange=buy_exchange,
        sell_exchange=sell_exchange,
        buy_ask=buy_ask,
        sell_bid=sell_bid,
        gross_spread=(sell_bid - buy_ask) * available_qty,
        net_spread=1.0,
        score=0.0,
        detected_at=_NOW,
        available_qty=available_qty,
        optimal_qty=0.0,
    )


# ── λ estimator: known-answer cases ─────────────────────────────────────────────
# λ = impact_coeff · (sell_bid − buy_ask) / available_qty

def test_estimate_market_impact_known_answer():
    # (51_000 − 50_000) / 2.0 = 500.0
    lam = estimate_market_impact(_opp(available_qty=2.0))
    assert lam == pytest.approx(500.0)


def test_estimate_market_impact_thinner_depth_steeper_lambda():
    # Halving available depth doubles λ → impact bites sooner.
    lam_thin = estimate_market_impact(_opp(available_qty=1.0))
    lam_deep = estimate_market_impact(_opp(available_qty=2.0))
    assert lam_thin == pytest.approx(2 * lam_deep)


def test_estimate_market_impact_scales_with_coeff():
    base = estimate_market_impact(_opp(available_qty=2.0), impact_coeff=1.0)
    scaled = estimate_market_impact(_opp(available_qty=2.0), impact_coeff=3.0)
    assert scaled == pytest.approx(3.0 * base)


def test_estimate_market_impact_zero_when_spread_non_positive():
    # sell_bid <= buy_ask → no edge → λ = 0 (caller falls back to linear)
    assert estimate_market_impact(_opp(buy_ask=51_000.0, sell_bid=50_000.0)) == 0.0


# ── interior optimum: the core differentiator ──────────────────────────────────
# Quadratic impact makes q* = s / (2λ) an INTERIOR point, not a constraint boundary.

def test_optimal_qty_interior_matches_analytic_hand_computed():
    # BINANCE→OKX: s ≈ 870.58, explicit λ = 1000 → q* = s / (2·1000) ≈ 0.4353 BTC.
    # available_qty = 1.0 and max_position = 1.0 both slack → optimum is interior.
    sizer = OptimalSizer(max_position_size=1.0, min_trade_size=0.001)
    q = sizer.compute_optimal_qty(
        _opp(sell_exchange=Exchange.OKX, available_qty=1.0),
        balance_usdt=_HUGE_BALANCE,
        market_impact=1000.0,
    )
    assert q == pytest.approx(_S_BINANCE_OKX / 2000.0, abs=1e-4)


def test_optimal_qty_interior_matches_analytic_with_estimated_lambda():
    # Estimated λ; verify the QP lands on the analytic KKT point s / (2λ).
    sizer = OptimalSizer(max_position_size=100.0, min_trade_size=0.001)
    opp = _opp(available_qty=10.0)  # deep book so depth does not cap
    lam = estimate_market_impact(opp)  # 1000 / 10 = 100.0
    expected = _S_BINANCE_KRAKEN / (2 * lam)  # 817.4 / 200 = 4.087
    q = sizer.compute_optimal_qty(opp, balance_usdt=_HUGE_BALANCE)
    assert q == pytest.approx(expected, rel=1e-3)
    assert q < opp.available_qty  # strictly interior, not pinned to depth


def test_optimal_qty_decreases_as_lambda_increases():
    # Monotonicity: steeper impact → smaller optimal size (both interior).
    sizer = OptimalSizer(max_position_size=100.0, min_trade_size=0.001)
    opp = _opp(available_qty=10.0)
    q_low = sizer.compute_optimal_qty(opp, _HUGE_BALANCE, market_impact=200.0)
    q_high = sizer.compute_optimal_qty(opp, _HUGE_BALANCE, market_impact=800.0)
    assert q_high < q_low
    assert q_low == pytest.approx(_S_BINANCE_KRAKEN / 400, rel=1e-3)   # ≈ 1.9495
    assert q_high == pytest.approx(_S_BINANCE_KRAKEN / 1600, rel=1e-3)  # ≈ 0.4874


# ── constraints still bind when the analytic optimum exceeds them ───────────────

def test_optimal_qty_capped_by_orderbook_depth():
    # Small λ → analytic optimum (≈40.9) far exceeds depth 0.1 → capped to depth.
    sizer = OptimalSizer(max_position_size=100.0, min_trade_size=0.001)
    q = sizer.compute_optimal_qty(
        _opp(available_qty=0.1), _HUGE_BALANCE, market_impact=10.0
    )
    assert q == pytest.approx(0.1, abs=1e-4)


def test_optimal_qty_capped_by_balance_when_balance_binds():
    # balance 25_000 at ask 50_000 → 0.5 BTC cap; analytic optimum far exceeds it.
    sizer = OptimalSizer(max_position_size=100.0, min_trade_size=0.001)
    q = sizer.compute_optimal_qty(
        _opp(buy_ask=50_000.0, available_qty=100.0),
        balance_usdt=25_000.0,
        market_impact=10.0,
    )
    assert q == pytest.approx(0.5, abs=1e-4)


def test_optimal_qty_never_exceeds_max_position():
    # max_position 1.0 binds before the (huge) analytic optimum.
    sizer = OptimalSizer(max_position_size=1.0, min_trade_size=0.001)
    q = sizer.compute_optimal_qty(
        _opp(available_qty=100.0), _HUGE_BALANCE, market_impact=10.0
    )
    assert q == pytest.approx(1.0, abs=1e-4)


# ── linear fallback (λ = 0): degenerate optimum at the tightest bound ───────────

def test_optimal_qty_linear_fallback_pins_to_upper_bound():
    sizer = OptimalSizer(max_position_size=1.0, min_trade_size=0.001)
    q = sizer.compute_optimal_qty(
        _opp(available_qty=0.5), _HUGE_BALANCE, market_impact=0.0
    )
    assert q == pytest.approx(0.5, abs=1e-4)


# ── profitability gate ──────────────────────────────────────────────────────────

def test_optimal_qty_zero_when_min_size_trade_loses_to_impact():
    # λ enormous → analytic optimum below min_trade_size; forcing the 0.001 floor
    # would cost more in slippage than the edge yields → don't trade.
    # P(0.001) = 0.001·817.4 − 1e7·0.001² = 0.8174 − 10 < 0.
    sizer = OptimalSizer(max_position_size=1.0, min_trade_size=0.001)
    q = sizer.compute_optimal_qty(
        _opp(available_qty=1.0), _HUGE_BALANCE, market_impact=1e7
    )
    assert q == 0.0


# ── balance / liquidity / spread guards (λ-independent) ─────────────────────────

def test_insufficient_balance_raises():
    sizer = OptimalSizer(max_position_size=1.0, min_trade_size=0.001)
    # balance 10 USDT at ask 50_000 funds 0.0002 BTC < min_trade_size 0.001
    with pytest.raises(InsufficientBalanceError):
        sizer.compute_optimal_qty(_opp(buy_ask=50_000.0), balance_usdt=10.0)


def test_optimal_qty_zero_when_liquidity_below_min_trade_size():
    sizer = OptimalSizer(max_position_size=1.0, min_trade_size=0.001)
    # available 0.0005 < min_trade_size 0.001 → nothing tradable, q* = 0
    q = sizer.compute_optimal_qty(_opp(available_qty=0.0005), balance_usdt=_HUGE_BALANCE)
    assert q == 0.0


def test_optimal_qty_zero_when_spread_unprofitable():
    sizer = OptimalSizer(max_position_size=1.0, min_trade_size=0.001)
    # sell_bid below buy_ask → negative per-unit net spread → q* = 0 (defensive)
    q = sizer.compute_optimal_qty(
        _opp(buy_ask=50_000.0, sell_bid=49_000.0), balance_usdt=_HUGE_BALANCE
    )
    assert q == 0.0


def test_optimal_qty_always_non_negative():
    sizer = OptimalSizer(max_position_size=1.0, min_trade_size=0.001)
    q = sizer.compute_optimal_qty(_opp(available_qty=0.5), balance_usdt=_HUGE_BALANCE)
    assert q >= 0.0
