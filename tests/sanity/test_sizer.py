from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.sizer import InsufficientBalanceError, OptimalSizer
from models.market import Exchange, Opportunity

_NOW = datetime(2026, 5, 29, 6, 0, 0, tzinfo=timezone.utc)
_HUGE_BALANCE = 1_000_000.0  # USDT, large enough to never bind


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


# ── order book depth caps q* ──────────────────────────────────────────────────

def test_optimal_qty_capped_by_orderbook_depth():
    sizer = OptimalSizer(max_position_size=1.0, min_trade_size=0.001)
    q = sizer.compute_optimal_qty(_opp(available_qty=0.1), balance_usdt=_HUGE_BALANCE)
    assert q <= 0.1
    assert q == pytest.approx(0.1, abs=1e-6)


# ── insufficient balance ──────────────────────────────────────────────────────

def test_insufficient_balance_raises():
    sizer = OptimalSizer(max_position_size=1.0, min_trade_size=0.001)
    # balance 10 USDT at ask 50_000 funds 0.0002 BTC < min_trade_size 0.001
    with pytest.raises(InsufficientBalanceError):
        sizer.compute_optimal_qty(_opp(buy_ask=50_000.0), balance_usdt=10.0)


# ── risk limit caps q* ────────────────────────────────────────────────────────

def test_optimal_qty_never_exceeds_max_position():
    sizer = OptimalSizer(max_position_size=1.0, min_trade_size=0.001)
    q = sizer.compute_optimal_qty(_opp(available_qty=5.0), balance_usdt=_HUGE_BALANCE)
    assert q <= 1.0
    assert q == pytest.approx(1.0, abs=1e-6)


# ── all constraints slack → q* = min(available, max_position) ──────────────────

def test_optimal_qty_equals_min_of_constraints_when_slack():
    sizer = OptimalSizer(max_position_size=1.0, min_trade_size=0.001)
    # available 0.5 < max_position 1.0, balance huge → q* = 0.5
    q = sizer.compute_optimal_qty(_opp(available_qty=0.5), balance_usdt=_HUGE_BALANCE)
    assert q == pytest.approx(min(0.5, 1.0), abs=1e-6)


# ── balance binds before liquidity/risk ───────────────────────────────────────

def test_optimal_qty_capped_by_balance_when_balance_binds():
    sizer = OptimalSizer(max_position_size=1.0, min_trade_size=0.001)
    # balance 25_000 at ask 50_000 → 0.5 BTC, below available 2.0 and max 1.0
    q = sizer.compute_optimal_qty(
        _opp(buy_ask=50_000.0, available_qty=2.0), balance_usdt=25_000.0
    )
    assert q == pytest.approx(0.5, abs=1e-6)


# ── non-negativity ────────────────────────────────────────────────────────────

def test_optimal_qty_always_non_negative():
    sizer = OptimalSizer(max_position_size=1.0, min_trade_size=0.001)
    q = sizer.compute_optimal_qty(_opp(available_qty=0.5), balance_usdt=_HUGE_BALANCE)
    assert q >= 0.0


def test_optimal_qty_zero_when_liquidity_below_min_trade_size():
    sizer = OptimalSizer(max_position_size=1.0, min_trade_size=0.001)
    # available 0.0005 < min_trade_size 0.001, balance fine → nothing tradable, q*=0
    q = sizer.compute_optimal_qty(_opp(available_qty=0.0005), balance_usdt=_HUGE_BALANCE)
    assert q == 0.0
    assert q >= 0.0


def test_optimal_qty_zero_when_spread_unprofitable():
    sizer = OptimalSizer(max_position_size=1.0, min_trade_size=0.001)
    # sell_bid below buy_ask → negative per-unit net spread → q*=0 (defensive)
    q = sizer.compute_optimal_qty(
        _opp(buy_ask=50_000.0, sell_bid=49_000.0), balance_usdt=_HUGE_BALANCE
    )
    assert q == 0.0
