from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, field_validator


class Exchange(str, Enum):
    BINANCE = "binance"
    KRAKEN = "kraken"
    COINBASE = "coinbase"
    OKX = "okx"


class BBO(BaseModel):
    exchange: Exchange
    bid: float
    ask: float
    bid_qty: float
    ask_qty: float
    ws_received_at: datetime
    normalized_at: datetime | None = None

    model_config = {"frozen": True}

    @field_validator("bid", "ask", "bid_qty", "ask_qty")
    @classmethod
    def must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"price/qty must be positive, got {v}")
        return v


class OrderBookLevel(BaseModel):
    price: float
    qty: float

    model_config = {"frozen": True}

    @field_validator("price", "qty")
    @classmethod
    def must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"price/qty must be positive, got {v}")
        return v


class OrderBook(BaseModel):
    """Top-N order book depth. bids descending by price, asks ascending — best first."""
    exchange: Exchange
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    ws_received_at: datetime
    normalized_at: datetime | None = None

    model_config = {"frozen": True}

    @property
    def best_bid(self) -> float | None:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> float | None:
        return self.asks[0].price if self.asks else None


class Opportunity(BaseModel):
    buy_exchange: Exchange
    sell_exchange: Exchange
    buy_ask: float
    sell_bid: float
    gross_spread: float
    net_spread: float
    score: float
    detected_at: datetime
    available_qty: float
    optimal_qty: float
    status: str = "PENDING"
