from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from models.market import Exchange, OrderBookLevel

# Score above this threshold marks the exchange as DEGRADED.
# Calibrated from synthetic books: healthy market ≈ 1e-5–1e-4, fragmented ≈ 0.1–10+.
FRAGMENTATION_THRESHOLD = 0.05


class LiquidityStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class FragmentationResult:
    exchange: Exchange
    score: float
    status: LiquidityStatus
    level_count: int
    computed_at: datetime


def compute_fragmentation_score(
    levels: list[OrderBookLevel],
    top_n: int = 10,
) -> float:
    """
    O(N) fragmentation score inspired by econophysics order book analysis.

    Formula: Σ (relative_gap_i / qty_i) / total_depth
      - relative_gap_i = |price[i+1] - price[i]| / price[0]  (normalized price gap)
      - qty_i = depth at level i (inverse-weights thin levels, amplifying their gaps)
      - total_depth = Σ qty over top_n levels (scale-invariant normalization)

    Interpretation:
      Low score  → liquidity concentrated near top, tight gaps → healthy for arb.
      High score → large gaps between sparse levels → elevated slippage risk → DEGRADED.

    Returns 0.0 for books with fewer than 2 levels (no gaps to measure).
    """
    if len(levels) < 2:
        return 0.0

    top = levels[:top_n]
    n = len(top)
    reference_price = top[0].price
    total_depth = sum(l.qty for l in top)

    weighted_gap_sum = 0.0
    for i in range(n - 1):
        gap = abs(top[i + 1].price - top[i].price)
        rel_gap = gap / reference_price
        # NOTE: inverse qty weight — a gap behind a thin level is more dangerous
        # than the same gap behind deep liquidity; this asymmetry is the key signal.
        weighted_gap_sum += rel_gap / top[i].qty

    return weighted_gap_sum / total_depth


class LiquidityHealthMonitor:
    """
    In-memory monitor of per-exchange liquidity fragmentation.

    Call update() whenever fresh order book depth arrives; query is_healthy()
    before routing arbitrage legs to avoid exchanges in DEGRADED state.
    """

    def __init__(self, threshold: float = FRAGMENTATION_THRESHOLD) -> None:
        self._threshold = threshold
        self._state: dict[Exchange, FragmentationResult] = {}

    def update(
        self,
        exchange: Exchange,
        levels: list[OrderBookLevel],
        top_n: int = 10,
    ) -> FragmentationResult:
        """Recompute fragmentation score for exchange and cache the result."""
        score = compute_fragmentation_score(levels, top_n=top_n)
        status = (
            LiquidityStatus.DEGRADED if score > self._threshold else LiquidityStatus.HEALTHY
        )
        result = FragmentationResult(
            exchange=exchange,
            score=round(score, 8),
            status=status,
            level_count=min(len(levels), top_n),
            computed_at=datetime.now(timezone.utc),
        )
        self._state[exchange] = result
        return result

    def get(self, exchange: Exchange) -> FragmentationResult | None:
        return self._state.get(exchange)

    def get_all(self) -> dict[Exchange, FragmentationResult]:
        return dict(self._state)

    def is_healthy(self, exchange: Exchange) -> bool:
        """Return True when exchange is HEALTHY or UNKNOWN (no data → don't block)."""
        result = self._state.get(exchange)
        return result is None or result.status == LiquidityStatus.HEALTHY

    def as_dict(self) -> dict:
        return {
            ex.value: {
                "score": r.score,
                "status": r.status.value,
                "level_count": r.level_count,
                "computed_at": r.computed_at.isoformat(),
            }
            for ex, r in self._state.items()
        }


# ── module-level singleton ────────────────────────────────────────────────────

_instance: LiquidityHealthMonitor | None = None


def get_liquidity_monitor() -> LiquidityHealthMonitor:
    global _instance
    if _instance is None:
        _instance = LiquidityHealthMonitor()
    return _instance
