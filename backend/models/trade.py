from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from models.market import Exchange

TradeStatus = Literal[
    "EXECUTED",
    "ABORTED_STALE",
    "SKIPPED_MIN_FILL",
    "REJECTED_INSUFFICIENT_BALANCE",
    "REJECTED_NEGATIVE_NET",
    "REJECTED_LATENCY_RISK",
    "CIRCUIT_BREAKER_OPEN",
]


class Trade(BaseModel):
    id: str
    buy_exchange: Exchange
    sell_exchange: Exchange
    qty: float
    buy_price: float
    sell_price: float
    fee_buy: float
    fee_sell: float
    slippage_est: float
    net_profit: float
    fill_ratio: float = 1.0  # executed_qty / requested_qty; < 1.0 on partial fill
    status: TradeStatus
    ws_received_at: datetime
    decision_at: datetime
    latency_ms: float
    executed_at: datetime


class WalletBalance(BaseModel):
    exchange: Exchange
    usdt: float
    btc: float
    updated_at: datetime
