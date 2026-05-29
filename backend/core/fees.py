from __future__ import annotations

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
}


def get_fee_rate(exchange: Exchange, side: OrderSide) -> float:
    try:
        return _FEE_RATES[exchange][side]
    except KeyError:
        raise KeyError(f"No fee rate registered for exchange={exchange!r}, side={side!r}")


def calculate_fee(exchange: Exchange, qty: float, price: float, side: OrderSide) -> float:
    """Returns fee in USDT: qty * price * rate."""
    if qty <= 0:
        raise ValueError(f"qty must be positive, got {qty}")
    if price <= 0:
        raise ValueError(f"price must be positive, got {price}")
    return qty * price * get_fee_rate(exchange, side)


def calculate_net_spread(
    buy_exchange: Exchange,
    sell_exchange: Exchange,
    buy_ask: float,
    sell_bid: float,
    qty: float,
) -> float:
    """Net P&L (USDT) of one arb trade. Both legs use taker fees."""
    gross = (sell_bid - buy_ask) * qty
    fee_buy = calculate_fee(buy_exchange, qty, buy_ask, OrderSide.TAKER)
    fee_sell = calculate_fee(sell_exchange, qty, sell_bid, OrderSide.TAKER)
    return gross - fee_buy - fee_sell
