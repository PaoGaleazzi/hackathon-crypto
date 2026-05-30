from __future__ import annotations

from fastapi import APIRouter

from core.funding_arb import (
    cash_carry_to_dict,
    cross_exchange_to_dict,
    funding_rate_to_dict,
    get_funding_detector,
)

router = APIRouter(tags=["funding"])


@router.get("/funding")
async def get_funding() -> dict:
    """Live funding-rate state and the arbitrage opportunities derived from it.

    Served from the in-memory FundingArbDetector that the funding-poller task
    refreshes every 10s (no DuckDB on this path).
    """
    detector = get_funding_detector()
    rates = detector.funding_rates
    result = detector.detect()
    cash_and_carry = result["cash_and_carry"]
    cross_exchange = result["cross_exchange_funding"]

    # Best annualized return across every detected opportunity (both kinds).
    # Opportunities are sorted desc, so the first of each list is its best.
    candidates = [o.annualized_return for o in cash_and_carry]
    candidates += [o.annualized_return for o in cross_exchange]
    best_annualized_return = max(candidates) if candidates else None

    return {
        "funding_rates": {
            ex.value: funding_rate_to_dict(fr) for ex, fr in rates.items()
        },
        "cash_and_carry": [cash_carry_to_dict(o) for o in cash_and_carry],
        "cross_exchange": [cross_exchange_to_dict(o) for o in cross_exchange],
        "best_annualized_return": best_annualized_return,
    }
