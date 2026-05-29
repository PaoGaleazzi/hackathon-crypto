from __future__ import annotations

import pytest

from core.fees import OrderSide, calculate_fee, calculate_net_spread, get_fee_rate
from models.market import Exchange


# ── get_fee_rate: table completeness ──────────────────────────────────────────

@pytest.mark.parametrize("exchange,side,expected", [
    (Exchange.BINANCE,  OrderSide.MAKER, 0.001),
    (Exchange.BINANCE,  OrderSide.TAKER, 0.001),
    (Exchange.KRAKEN,   OrderSide.MAKER, 0.0016),
    (Exchange.KRAKEN,   OrderSide.TAKER, 0.0026),
    (Exchange.COINBASE, OrderSide.MAKER, 0.004),
    (Exchange.COINBASE, OrderSide.TAKER, 0.006),
])
def test_get_fee_rate_all_exchanges_and_sides(exchange, side, expected):
    assert get_fee_rate(exchange, side) == pytest.approx(expected)


# ── calculate_fee: known-answer cases ─────────────────────────────────────────
# All computed by hand: fee = qty * price * rate

def test_calculate_fee_binance_taker_known_answer():
    # 0.1 BTC * 70_000 USDT * 0.001 = 7.0 USDT
    result = calculate_fee(Exchange.BINANCE, qty=0.1, price=70_000.0, side=OrderSide.TAKER)
    assert result == pytest.approx(7.0)


def test_calculate_fee_kraken_maker_known_answer():
    # 0.1 BTC * 70_000 USDT * 0.0016 = 11.2 USDT
    result = calculate_fee(Exchange.KRAKEN, qty=0.1, price=70_000.0, side=OrderSide.MAKER)
    assert result == pytest.approx(11.2)


def test_calculate_fee_coinbase_taker_known_answer():
    # 0.1 BTC * 70_000 USDT * 0.006 = 42.0 USDT
    result = calculate_fee(Exchange.COINBASE, qty=0.1, price=70_000.0, side=OrderSide.TAKER)
    assert result == pytest.approx(42.0)


# ── calculate_fee: input validation ───────────────────────────────────────────

def test_calculate_fee_raises_on_zero_qty():
    with pytest.raises(ValueError, match="qty must be positive"):
        calculate_fee(Exchange.BINANCE, qty=0.0, price=70_000.0, side=OrderSide.TAKER)


def test_calculate_fee_raises_on_negative_qty():
    with pytest.raises(ValueError, match="qty must be positive"):
        calculate_fee(Exchange.BINANCE, qty=-0.1, price=70_000.0, side=OrderSide.TAKER)


def test_calculate_fee_raises_on_negative_price():
    with pytest.raises(ValueError, match="price must be positive"):
        calculate_fee(Exchange.BINANCE, qty=0.1, price=-1.0, side=OrderSide.TAKER)


# ── calculate_net_spread: known-answer cases ──────────────────────────────────
# buy BINANCE ask=70_000, sell KRAKEN bid=70_500, qty=1.0, no depth_qty
#   gross        = (70_500 - 70_000) * 1.0                              =  500.0
#   fee_buy      = 1.0 * 70_000 * 0.001 (Binance taker)                =   70.0
#   fee_sell     = 1.0 * 70_500 * 0.0026 (Kraken taker)                =  183.3
#   withdrawal   = 0.0005 * 70_000 (Binance BTC network fee)           =   35.0
#   slippage     = 0 (no depth_qty supplied)
#   latency_buy  ≈ 1.0 * 70_000 * (0.80/√(365*24*3600*1000)) * 5ms   ≈    1.58
#   latency_sell ≈ 1.0 * 70_500 * (0.80/√(365*24*3600*1000)) * 50ms  ≈   15.87
#   net ≈ 500.0 - 70.0 - 183.3 - 35.0 - 1.58 - 15.87                 ≈  194.24

def test_calculate_net_spread_positive_case():
    result = calculate_net_spread(
        buy_exchange=Exchange.BINANCE,
        sell_exchange=Exchange.KRAKEN,
        buy_ask=70_000.0,
        sell_bid=70_500.0,
        qty=1.0,
    )
    assert result == pytest.approx(194.2434510580133, rel=1e-4)


def test_calculate_net_spread_negative_when_spread_too_small():
    # tiny 10-point spread, fees dominate
    # gross = 10 * 0.1 = 1.0, fees ~25.2 → net < 0
    result = calculate_net_spread(
        buy_exchange=Exchange.BINANCE,
        sell_exchange=Exchange.KRAKEN,
        buy_ask=70_000.0,
        sell_bid=70_010.0,
        qty=0.1,
    )
    assert result < 0
