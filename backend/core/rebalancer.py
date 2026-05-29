from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from core.fees import estimate_withdrawal_cost
from models.market import Exchange
from models.trade import WalletBalance

DEFAULT_BAND = 0.1               # ±10% of target tolerated before any action
STABLECOIN_WITHDRAWAL_USD = 1.0  # flat USD/USDT network withdrawal fee (proxy)
_FLOW_TOL = 1e-9                 # treat flows below this as zero

# Why MILP and not linprog/min_cost_flow: withdrawal fees are FIXED per transfer
# (a flat BTC/USDT fee, independent of amount). A per-unit LP (linprog,
# networkx.min_cost_flow) cannot represent that — it would charge proportional to
# volume, which for a ~$1 stablecoin fee makes moving USDT absurdly expensive. The
# correct model is a fixed-charge transportation problem: a binary "route used"
# variable per edge carries the flat fee. scipy.optimize.milp solves it exactly.


@dataclass(frozen=True)
class RebalanceTransfer:
    asset: str
    from_exchange: Exchange
    to_exchange: Exchange
    amount: float
    fee_usd: float            # flat withdrawal fee charged once for this transfer


@dataclass(frozen=True)
class RebalancePlan:
    transfers: list[RebalanceTransfer]
    total_cost_usd: float
    status: str               # "OK" | "BALANCED" | "INFEASIBLE"


def _asset_balance(wallet: WalletBalance, asset: str) -> float:
    if asset == "BTC":
        return wallet.btc
    if asset == "USDT":
        return wallet.usdt
    raise ValueError(f"unsupported asset {asset!r} (expected 'BTC' or 'USDT')")


def _transfer_fee_usd(
    asset: str, source: Exchange, btc_price: float, stablecoin_withdrawal_usd: float
) -> float:
    if asset == "BTC":
        return estimate_withdrawal_cost(source, btc_price)
    if asset == "USDT":
        return stablecoin_withdrawal_usd
    raise ValueError(f"unsupported asset {asset!r} (expected 'BTC' or 'USDT')")


def _solve_asset(
    asset: str,
    exchanges: list[Exchange],
    current: dict[Exchange, float],
    target_map: dict[Exchange, float],
    band: float,
    fee_of: Callable[[Exchange], float],
) -> tuple[list[RebalanceTransfer], bool]:
    """Fixed-charge transportation MILP for one asset. Returns (transfers, feasible).

        minimize   Σ_e fee(source_e)·y_e        (flat fee per used route)
                   + ε·Σ_e x_e                   (tie-break toward minimal volume)
        s.t.       lo_k ≤ current_k + inflow_k − outflow_k ≤ hi_k   (target band)
                   x_e ≤ M·y_e                   (no flow on an unused route)
                   x_e ≥ 0,  y_e ∈ {0, 1}
    """
    n = len(exchanges)
    lo = np.array([target_map[e] * (1.0 - band) for e in exchanges])
    hi = np.array([target_map[e] * (1.0 + band) for e in exchanges])
    cur = np.array([current[e] for e in exchanges])

    in_band = bool(np.all((cur >= lo - _FLOW_TOL) & (cur <= hi + _FLOW_TOL)))
    if n < 2 or in_band:
        # Nothing movable (single node) or already balanced. Out-of-band with
        # n<2 is infeasible — no route exists to fix it.
        return [], in_band

    edges = [(i, j) for i in range(n) for j in range(n) if i != j]
    n_edges = len(edges)
    big_m = float(cur.sum() + hi.sum() + 1.0)  # safe upper bound on any single flow

    fees = np.array([fee_of(exchanges[i]) for i, _ in edges])
    min_fee = float(fees[fees > 0].min()) if np.any(fees > 0) else 1.0
    # ε kept small enough that the volume term can never flip a fixed-fee decision.
    eps = min_fee / (1e3 * big_m * n_edges + 1.0)
    cost = np.concatenate([np.full(n_edges, eps), fees])

    # Balance: net (inflow − outflow) per node within [lo−cur, hi−cur].
    a_bal = np.zeros((n, 2 * n_edges))
    for e, (i, j) in enumerate(edges):
        a_bal[i, e] -= 1.0
        a_bal[j, e] += 1.0

    # Linking: x_e − M·y_e ≤ 0.
    a_link = np.zeros((n_edges, 2 * n_edges))
    for e in range(n_edges):
        a_link[e, e] = 1.0
        a_link[e, n_edges + e] = -big_m

    a = np.vstack([a_bal, a_link])
    con_lo = np.concatenate([lo - cur, np.full(n_edges, -np.inf)])
    con_hi = np.concatenate([hi - cur, np.zeros(n_edges)])

    integrality = np.concatenate([np.zeros(n_edges), np.ones(n_edges)])
    var_bounds = Bounds(
        np.zeros(2 * n_edges),
        np.concatenate([np.full(n_edges, big_m), np.ones(n_edges)]),
    )

    res = milp(
        c=cost,
        constraints=LinearConstraint(a, con_lo, con_hi),
        integrality=integrality,
        bounds=var_bounds,
    )
    if not res.success or res.x is None:
        return [], False

    transfers = [
        RebalanceTransfer(
            asset=asset,
            from_exchange=exchanges[i],
            to_exchange=exchanges[j],
            amount=float(res.x[e]),
            fee_usd=fee_of(exchanges[i]),
        )
        for e, (i, j) in enumerate(edges)
        if res.x[e] > _FLOW_TOL
    ]
    return transfers, True


def plan_rebalance(
    wallets: dict[Exchange, WalletBalance],
    targets: dict[str, dict[Exchange, float]],
    btc_price: float,
    band: float = DEFAULT_BAND,
    stablecoin_withdrawal_usd: float = STABLECOIN_WITHDRAWAL_USD,
) -> RebalancePlan:
    """Minimum-cost wallet rebalancing as a fixed-charge min-cost flow.

    `targets[asset][exchange]` is the desired inventory; a wallet is left alone
    while it stays within ±`band` of its target. Transfers move one asset between
    exchanges, each costing that exchange's flat withdrawal fee (USD). Not meant to
    run every tick — call it every N trades or when a wallet breaches its band.
    """
    if btc_price <= 0:
        raise ValueError(f"btc_price must be positive, got {btc_price}")
    if band < 0:
        raise ValueError(f"band must be non-negative, got {band}")

    all_transfers: list[RebalanceTransfer] = []
    feasible = True

    for asset, target_map in targets.items():
        exchanges = list(target_map.keys())
        missing = [e for e in exchanges if e not in wallets]
        if missing:
            raise ValueError(f"targets reference wallets not present: {missing}")
        current = {e: _asset_balance(wallets[e], asset) for e in exchanges}

        def fee_of(source: Exchange, _asset: str = asset) -> float:
            return _transfer_fee_usd(_asset, source, btc_price, stablecoin_withdrawal_usd)

        transfers, ok = _solve_asset(asset, exchanges, current, target_map, band, fee_of)
        feasible = feasible and ok
        all_transfers.extend(transfers)

    if not feasible:
        return RebalancePlan(transfers=[], total_cost_usd=0.0, status="INFEASIBLE")

    total_cost = sum(t.fee_usd for t in all_transfers)
    status = "OK" if all_transfers else "BALANCED"
    return RebalancePlan(transfers=all_transfers, total_cost_usd=total_cost, status=status)


# ── in-memory latest-plan cache ──────────────────────────────────────────────────
# The pipeline writes the most recent plan here every N executed trades; GET
# /api/rebalance reads it. Advisory only — transfers are never auto-executed.

_latest_plan: RebalancePlan | None = None
_latest_computed_at: datetime | None = None


def set_latest_plan(plan: RebalancePlan, computed_at: datetime) -> None:
    global _latest_plan, _latest_computed_at
    _latest_plan = plan
    _latest_computed_at = computed_at


def get_latest_plan() -> tuple[RebalancePlan | None, datetime | None]:
    return _latest_plan, _latest_computed_at
