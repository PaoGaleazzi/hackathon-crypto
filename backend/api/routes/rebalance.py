from __future__ import annotations

from fastapi import APIRouter

from core.rebalancer import get_latest_plan

router = APIRouter(tags=["rebalance"])


@router.get("/rebalance")
async def get_rebalance() -> dict:
    """Latest wallet rebalance plan computed by the pipeline.

    Advisory only — the plan is never auto-executed. Served from the in-memory
    cache (no DuckDB); `status` is "NONE" until the first plan is computed.
    """
    plan, computed_at = get_latest_plan()
    if plan is None:
        return {
            "status": "NONE",
            "total_cost_usd": 0.0,
            "n_transfers": 0,
            "transfers": [],
            "computed_at": None,
        }
    return {
        "status": plan.status,
        "total_cost_usd": plan.total_cost_usd,
        "n_transfers": len(plan.transfers),
        "transfers": [
            {
                "asset": t.asset,
                "from": t.from_exchange.value,
                "to": t.to_exchange.value,
                "amount": t.amount,
                "fee_usd": t.fee_usd,
            }
            for t in plan.transfers
        ],
        "computed_at": computed_at.isoformat() if computed_at is not None else None,
    }
