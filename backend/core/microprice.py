from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

from models.market import BBO, Exchange

# Default length of the per-key micro-price history window.
DEFAULT_HISTORY_LEN = 20

# Default symbol when callers don't disambiguate (BBO carries no symbol field yet).
DEFAULT_SYMBOL = "BTC-USD"


def microprice(bid: float, ask: float, bid_size: float, ask_size: float) -> float:
    """
    Stoikov-style micro-price (simple imbalance-weighted mid).

        imbalance = bid_size / (bid_size + ask_size)
        micro     = ask * imbalance + bid * (1 - imbalance)

    The imbalance weights the mid toward the side under pressure: heavy bid
    volume (high imbalance) means buying pressure, so the fair short-term price
    sits closer to the ask. It is a better forward predictor than (bid+ask)/2
    because the naive mid ignores book imbalance entirely.

    Raises ValueError on non-positive sizes (no liquidity → no fair price).
    """
    if bid_size <= 0 or ask_size <= 0:
        raise ValueError(
            f"sizes must be positive, got bid_size={bid_size}, ask_size={ask_size}"
        )

    imbalance = bid_size / (bid_size + ask_size)
    return ask * imbalance + bid * (1.0 - imbalance)


def microprice_adjustment(
    bid: float, ask: float, bid_size: float, ask_size: float
) -> float:
    """
    Signed offset of the micro-price over the naive mid: micro - mid.

    Positive → upward (buy-side) pressure; negative → downward (sell-side).
    """
    mid = (bid + ask) / 2.0
    return microprice(bid, ask, bid_size, ask_size) - mid


@dataclass(frozen=True)
class MicropriceSnapshot:
    micro: float
    mid: float
    adjustment: float
    imbalance: float
    computed_at: datetime


class MicropriceEstimator:
    """
    In-memory micro-price tracker keyed by (exchange, symbol).

    Call update() (or update_from_bbo()) on each fresh BBO; query current() for
    the latest snapshot and trend() for the short-window drift of the micro-price.
    History is bounded to a rolling window per key — no DuckDB on this path.
    """

    def __init__(self, history_len: int = DEFAULT_HISTORY_LEN) -> None:
        if history_len < 2:
            raise ValueError(f"history_len must be >= 2, got {history_len}")
        self._history_len = history_len
        self._history: dict[tuple[Exchange, str], deque[MicropriceSnapshot]] = {}

    def update(
        self,
        exchange: Exchange,
        bid: float,
        ask: float,
        bid_size: float,
        ask_size: float,
        symbol: str = DEFAULT_SYMBOL,
    ) -> MicropriceSnapshot:
        """Compute and store a micro-price snapshot for (exchange, symbol)."""
        mid = (bid + ask) / 2.0
        micro = microprice(bid, ask, bid_size, ask_size)
        snapshot = MicropriceSnapshot(
            micro=micro,
            mid=mid,
            adjustment=micro - mid,
            imbalance=bid_size / (bid_size + ask_size),
            computed_at=datetime.now(timezone.utc),
        )
        key = (exchange, symbol)
        window = self._history.get(key)
        if window is None:
            window = deque(maxlen=self._history_len)
            self._history[key] = window
        window.append(snapshot)
        return snapshot

    def update_from_bbo(
        self, bbo: BBO, symbol: str = DEFAULT_SYMBOL
    ) -> MicropriceSnapshot:
        """Convenience wrapper that reads the four legs off a BBO."""
        return self.update(
            bbo.exchange, bbo.bid, bbo.ask, bbo.bid_qty, bbo.ask_qty, symbol=symbol
        )

    def current(
        self, exchange: Exchange, symbol: str = DEFAULT_SYMBOL
    ) -> MicropriceSnapshot | None:
        """Latest snapshot for the key, or None if never updated."""
        window = self._history.get((exchange, symbol))
        return window[-1] if window else None

    def trend(self, exchange: Exchange, symbol: str = DEFAULT_SYMBOL) -> float:
        """
        Average per-update change of the micro-price over the window.

            trend = (micro_latest - micro_oldest) / (n - 1)

        Positive → micro-price drifting up across the window; negative → down.
        Returns NaN when fewer than 2 points exist (no slope to measure).
        """
        window = self._history.get((exchange, symbol))
        if window is None or len(window) < 2:
            return math.nan
        return (window[-1].micro - window[0].micro) / (len(window) - 1)
