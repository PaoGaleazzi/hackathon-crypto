from __future__ import annotations

from dataclasses import dataclass

from models.market import OrderBookLevel


@dataclass(frozen=True)
class WalkResult:
    filled_qty: float
    avg_price: float           # volume-weighted; 0.0 when filled_qty == 0
    fill_ratio: float          # filled_qty / target_qty, in [0, 1]
    levels_consumed: int


def walk_the_book(levels: list[OrderBookLevel], target_qty: float) -> WalkResult:
    """
    Consume order book levels (best-first) until target_qty is filled or depth runs out.

    Returns the volume-weighted average execution price and the fill ratio. When total
    depth < target_qty, the result is a partial fill (fill_ratio < 1.0). An empty book
    is a valid market state (no liquidity) → zero-fill result, not an error.
    """
    if target_qty <= 0:
        raise ValueError(f"target_qty must be positive, got {target_qty}")

    remaining = target_qty
    cost = 0.0
    filled = 0.0
    levels_consumed = 0

    for level in levels:
        take = min(remaining, level.qty)
        cost += take * level.price
        filled += take
        remaining -= take
        levels_consumed += 1
        if remaining <= 0:
            break

    avg_price = cost / filled if filled > 0 else 0.0
    return WalkResult(
        filled_qty=filled,
        avg_price=avg_price,
        fill_ratio=filled / target_qty,
        levels_consumed=levels_consumed,
    )
