from __future__ import annotations

import math

import pytest

from core.fees import (
    _BTC_ANNUAL_VOL,
    _LATENCY_MS,
    _MS_PER_YEAR,
    _SLIPPAGE_IMPACT_COEFF,
    _WITHDRAWAL_FEES_BTC,
    calculate_fee,
    calculate_net_spread,
    estimate_latency_cost,
    estimate_slippage,
    estimate_withdrawal_cost,
    OrderSide,
)
from models.market import Exchange


# ---------------------------------------------------------------------------
# estimate_withdrawal_cost
# ---------------------------------------------------------------------------

def test_estimate_withdrawal_cost_kraken_at_100k():
    # 0.00015 BTC * 100_000 USDT/BTC = 15.0 USDT
    result = estimate_withdrawal_cost(Exchange.KRAKEN, btc_price=100_000.0)
    assert result == pytest.approx(15.0, rel=1e-9)


def test_estimate_withdrawal_cost_binance_at_100k():
    # 0.0005 BTC * 100_000 = 50.0 USDT
    result = estimate_withdrawal_cost(Exchange.BINANCE, btc_price=100_000.0)
    assert result == pytest.approx(50.0, rel=1e-9)


def test_estimate_withdrawal_cost_scales_with_price():
    # Fee is fixed BTC amount, so USDT cost scales linearly with price
    low = estimate_withdrawal_cost(Exchange.OKX, btc_price=50_000.0)
    high = estimate_withdrawal_cost(Exchange.OKX, btc_price=100_000.0)
    assert high == pytest.approx(2 * low, rel=1e-9)


def test_estimate_withdrawal_cost_raises_on_zero_price():
    with pytest.raises(ValueError, match="btc_price must be positive"):
        estimate_withdrawal_cost(Exchange.BINANCE, btc_price=0.0)


# ---------------------------------------------------------------------------
# estimate_slippage  (sqrt / Almgren-Chriss model)
# ---------------------------------------------------------------------------

def test_estimate_slippage_qty_equals_depth():
    # When qty == depth_qty: impact_fraction = COEFF * sqrt(1) = COEFF
    # cost = qty * price * COEFF
    qty, price, depth = 0.1, 100_000.0, 0.1
    expected = qty * price * _SLIPPAGE_IMPACT_COEFF  # = 10.0 USDT
    result = estimate_slippage(qty, price, depth_qty=depth)
    assert result == pytest.approx(expected, rel=1e-9)


def test_estimate_slippage_quarter_depth():
    # qty/depth = 0.25; sqrt(0.25) = 0.5; so impact is halved vs full depth
    qty, price, depth = 0.025, 100_000.0, 0.1
    expected = qty * price * _SLIPPAGE_IMPACT_COEFF * math.sqrt(0.025 / 0.1)
    result = estimate_slippage(qty, price, depth_qty=depth)
    assert result == pytest.approx(expected, rel=1e-9)


def test_estimate_slippage_power_law_scaling():
    # formula = COEFF * price / sqrt(depth) * qty^(3/2)
    # doubling qty multiplies slippage by 2^(3/2) = 2*sqrt(2)
    base = estimate_slippage(0.1, 100_000.0, depth_qty=1.0)
    doubled = estimate_slippage(0.2, 100_000.0, depth_qty=1.0)
    assert doubled == pytest.approx(base * 2 * math.sqrt(2), rel=1e-6)


def test_estimate_slippage_raises_on_zero_depth():
    with pytest.raises(ValueError, match="depth_qty must be positive"):
        estimate_slippage(0.1, 100_000.0, depth_qty=0.0)


# ---------------------------------------------------------------------------
# estimate_latency_cost
# ---------------------------------------------------------------------------

def test_estimate_latency_cost_binance_known_answer():
    # vol_per_ms = 0.80 / sqrt(365 * 24 * 3600 * 1000)
    # Binance latency = 5.0 ms
    vol_per_ms = _BTC_ANNUAL_VOL / math.sqrt(_MS_PER_YEAR)
    expected = 0.1 * 100_000.0 * vol_per_ms * _LATENCY_MS[Exchange.BINANCE]
    result = estimate_latency_cost(Exchange.BINANCE, qty=0.1, price=100_000.0)
    assert result == pytest.approx(expected, rel=1e-9)


def test_estimate_latency_cost_kraken_greater_than_binance():
    # Kraken has 10x higher latency than Binance → 10x higher cost
    binance_cost = estimate_latency_cost(Exchange.BINANCE, qty=0.1, price=100_000.0)
    kraken_cost = estimate_latency_cost(Exchange.KRAKEN, qty=0.1, price=100_000.0)
    expected_ratio = _LATENCY_MS[Exchange.KRAKEN] / _LATENCY_MS[Exchange.BINANCE]
    assert kraken_cost == pytest.approx(binance_cost * expected_ratio, rel=1e-9)


def test_estimate_latency_cost_scales_linearly_with_qty():
    single = estimate_latency_cost(Exchange.OKX, qty=1.0, price=100_000.0)
    double = estimate_latency_cost(Exchange.OKX, qty=2.0, price=100_000.0)
    assert double == pytest.approx(2 * single, rel=1e-9)


# ---------------------------------------------------------------------------
# calculate_net_spread  (integration: all 4 cost components)
# ---------------------------------------------------------------------------

def test_calculate_net_spread_positive_with_wide_spread():
    # Binance buy @ 100_000, Coinbase sell @ 101_500, qty=1.0, no depth → slippage=0
    # Gross = 1500 USDT; fees + withdrawal + latency should leave positive net
    result = calculate_net_spread(
        Exchange.BINANCE, Exchange.COINBASE,
        buy_ask=100_000.0, sell_bid=101_500.0,
        qty=1.0,
    )
    assert result > 0.0, f"Expected positive net spread, got {result:.4f} USDT"


def test_calculate_net_spread_negative_when_thin_spread():
    # 10 bp spread after fees + withdrawal + latency is unprofitable
    result = calculate_net_spread(
        Exchange.BINANCE, Exchange.KRAKEN,
        buy_ask=100_000.0, sell_bid=100_100.0,
        qty=0.1,
    )
    assert result < 0.0, f"Expected negative net spread, got {result:.4f} USDT"


def test_calculate_net_spread_includes_withdrawal():
    # net with depth should be less than just fees alone
    fee_only = (
        (100_200.0 - 100_000.0) * 0.1
        - calculate_fee(Exchange.BINANCE, 0.1, 100_000.0, OrderSide.TAKER)
        - calculate_fee(Exchange.KRAKEN, 0.1, 100_200.0, OrderSide.TAKER)
    )
    full_net = calculate_net_spread(
        Exchange.BINANCE, Exchange.KRAKEN,
        buy_ask=100_000.0, sell_bid=100_200.0,
        qty=0.1,
    )
    withdrawal = estimate_withdrawal_cost(Exchange.BINANCE, 100_000.0)
    assert full_net < fee_only - withdrawal + 0.01  # strictly less than fee-only net


def test_calculate_net_spread_slippage_reduces_net():
    # Providing depth_qty makes net worse (more costs) than without
    no_depth = calculate_net_spread(
        Exchange.BINANCE, Exchange.OKX,
        buy_ask=100_000.0, sell_bid=101_000.0,
        qty=0.5,
    )
    with_depth = calculate_net_spread(
        Exchange.BINANCE, Exchange.OKX,
        buy_ask=100_000.0, sell_bid=101_000.0,
        qty=0.5,
        buy_depth_qty=1.0,
        sell_depth_qty=1.0,
    )
    assert with_depth < no_depth


def test_calculate_net_spread_manual_sum_matches():
    # Verify the function equals hand-computed sum of 4 components
    buy_ex, sell_ex = Exchange.BINANCE, Exchange.OKX
    buy_ask, sell_bid, qty, depth = 100_000.0, 101_000.0, 0.2, 1.0

    gross = (sell_bid - buy_ask) * qty
    fee_buy = calculate_fee(buy_ex, qty, buy_ask, OrderSide.TAKER)
    fee_sell = calculate_fee(sell_ex, qty, sell_bid, OrderSide.TAKER)
    withdrawal = estimate_withdrawal_cost(buy_ex, buy_ask)
    slip_buy = estimate_slippage(qty, buy_ask, depth)
    slip_sell = estimate_slippage(qty, sell_bid, depth)
    lat_buy = estimate_latency_cost(buy_ex, qty, buy_ask)
    lat_sell = estimate_latency_cost(sell_ex, qty, sell_bid)
    expected = gross - fee_buy - fee_sell - withdrawal - slip_buy - slip_sell - lat_buy - lat_sell

    result = calculate_net_spread(
        buy_ex, sell_ex, buy_ask, sell_bid, qty,
        buy_depth_qty=depth, sell_depth_qty=depth,
    )
    assert result == pytest.approx(expected, rel=1e-9)
