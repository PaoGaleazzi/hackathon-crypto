from __future__ import annotations

import math
from enum import Enum

from models.market import Exchange


class OrderSide(str, Enum):
    MAKER = "maker"
    TAKER = "taker"


# Real exchange fee rates (maker/taker) as of 2026
_FEE_RATES: dict[Exchange, dict[OrderSide, float]] = {
    Exchange.BINANCE:  {OrderSide.MAKER: 0.001,  OrderSide.TAKER: 0.001},
    Exchange.KRAKEN:   {OrderSide.MAKER: 0.0016, OrderSide.TAKER: 0.0026},
    Exchange.COINBASE: {OrderSide.MAKER: 0.004,  OrderSide.TAKER: 0.006},
    Exchange.OKX:      {OrderSide.MAKER: 0.0008, OrderSide.TAKER: 0.001},
    Exchange.BYBIT:    {OrderSide.MAKER: 0.001,  OrderSide.TAKER: 0.001},
    Exchange.BITSTAMP: {OrderSide.MAKER: 0.003,  OrderSide.TAKER: 0.004},
    Exchange.GEMINI:   {OrderSide.MAKER: 0.002,  OrderSide.TAKER: 0.004},
}

# BTC withdrawal fees (network + platform fee) per exchange as of 2026
# Sources: Binance/Kraken/Coinbase/OKX/Bybit official fee schedule pages
_WITHDRAWAL_FEES_BTC: dict[Exchange, float] = {
    Exchange.BINANCE:  0.0005,    # ~$50 at $100k/BTC
    Exchange.KRAKEN:   0.00015,   # ~$15 at $100k/BTC
    Exchange.COINBASE: 0.0001,    # ~$10 at $100k/BTC (variable; network fee estimate)
    Exchange.OKX:      0.0004,    # ~$40 at $100k/BTC
    Exchange.BYBIT:    0.0005,    # ~$50 at $100k/BTC
    Exchange.BITSTAMP: 0.0003,    # ~$30 at $100k/BTC
    Exchange.GEMINI:   0.001,     # ~$100 at $100k/BTC
}

# Typical WebSocket round-trip latency per exchange (milliseconds)
_LATENCY_MS: dict[Exchange, float] = {
    Exchange.BINANCE:  5.0,
    Exchange.KRAKEN:   50.0,
    Exchange.COINBASE: 30.0,
    Exchange.OKX:      10.0,
    Exchange.BYBIT:    15.0,
    Exchange.BITSTAMP: 40.0,
    Exchange.GEMINI:   35.0,
}

# BTC annualized realized vol (crypto 24/7, conservative)
_BTC_ANNUAL_VOL = 0.80

# Square-root market impact coefficient (Almgren-Chriss); dimensionless.
# At qty == depth_qty: impact_bps = COEFF * 100 bps = 0.1% of notional.
_SLIPPAGE_IMPACT_COEFF = 0.001

_MS_PER_YEAR: int = 365 * 24 * 3600 * 1000


def get_fee_rate(exchange: Exchange, side: OrderSide) -> float:
    try:
        return _FEE_RATES[exchange][side]
    except KeyError:
        raise KeyError(f"No fee rate registered for exchange={exchange!r}, side={side!r}")


def calculate_fee(exchange: Exchange, qty: float, price: float, side: OrderSide) -> float:
    """Returns trading fee in USDT: qty * price * rate."""
    if qty <= 0:
        raise ValueError(f"qty must be positive, got {qty}")
    if price <= 0:
        raise ValueError(f"price must be positive, got {price}")
    return qty * price * get_fee_rate(exchange, side)


def estimate_withdrawal_cost(exchange: Exchange, btc_price: float) -> float:
    """Fixed BTC withdrawal cost in USDT (one per arb cycle, not per BTC)."""
    if btc_price <= 0:
        raise ValueError(f"btc_price must be positive, got {btc_price}")
    return _WITHDRAWAL_FEES_BTC[exchange] * btc_price


def estimate_slippage(qty: float, price: float, depth_qty: float) -> float:
    """
    Square-root market impact model (Almgren-Chriss): cost in USDT.
    impact_fraction = COEFF * sqrt(qty / depth_qty)
    """
    if qty <= 0:
        raise ValueError(f"qty must be positive, got {qty}")
    if price <= 0:
        raise ValueError(f"price must be positive, got {price}")
    if depth_qty <= 0:
        raise ValueError(f"depth_qty must be positive, got {depth_qty}")
    impact_fraction = _SLIPPAGE_IMPACT_COEFF * math.sqrt(qty / depth_qty)
    return qty * price * impact_fraction


def estimate_latency_cost(exchange: Exchange, qty: float, price: float) -> float:
    """
    Expected adverse-selection cost during execution latency.
    cost = notional * (annual_vol / sqrt(ms_per_year)) * latency_ms
    """
    if qty <= 0:
        raise ValueError(f"qty must be positive, got {qty}")
    if price <= 0:
        raise ValueError(f"price must be positive, got {price}")
    vol_per_ms = _BTC_ANNUAL_VOL / math.sqrt(_MS_PER_YEAR)
    latency_ms = _LATENCY_MS[exchange]
    return qty * price * vol_per_ms * latency_ms


def calculate_net_spread(
    buy_exchange: Exchange,
    sell_exchange: Exchange,
    buy_ask: float,
    sell_bid: float,
    qty: float,
    buy_depth_qty: float | None = None,
    sell_depth_qty: float | None = None,
) -> float:
    """
    Net P&L (USDT) of one arb cycle including all 4 cost components:
    1. Trading fees  — taker rate, both legs
    2. Withdrawal    — buy-side exchange fixed BTC fee converted to USDT
    3. Slippage      — sqrt market-impact model; 0 when depth_qty not provided
    4. Latency       — adverse-selection cost over typical WS round-trip
    """
    gross = (sell_bid - buy_ask) * qty
    fee_buy = calculate_fee(buy_exchange, qty, buy_ask, OrderSide.TAKER)
    fee_sell = calculate_fee(sell_exchange, qty, sell_bid, OrderSide.TAKER)
    withdrawal = estimate_withdrawal_cost(buy_exchange, buy_ask)
    slippage_buy = estimate_slippage(qty, buy_ask, buy_depth_qty) if buy_depth_qty is not None else 0.0
    slippage_sell = estimate_slippage(qty, sell_bid, sell_depth_qty) if sell_depth_qty is not None else 0.0
    latency_buy = estimate_latency_cost(buy_exchange, qty, buy_ask)
    latency_sell = estimate_latency_cost(sell_exchange, qty, sell_bid)
    return gross - fee_buy - fee_sell - withdrawal - slippage_buy - slippage_sell - latency_buy - latency_sell
