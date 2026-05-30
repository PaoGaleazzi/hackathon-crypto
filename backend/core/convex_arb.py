from __future__ import annotations

import warnings
from dataclasses import dataclass

import cvxpy as cp
import numpy as np

from core.fees import OrderSide, get_fee_rate
from core.triangular import (
    BASE_CURRENCY,
    CONVERTIBLE_CURRENCIES,
    DEFAULT_STABLECOIN_COST,
    QUOTE_CURRENCY,
)
from models.market import BBO, Exchange, OrderBook

# ── Multi-exchange arbitrage as a single convex program ──────────────────────────
#
# This is the Angeris–Evans–Chitra–Boyd "Optimal Routing for CFMMs" framework
# (ACM EC 2022, arXiv:2204.05238) specialised to limit order books. Instead of a
# scanner that *finds* an opportunity and a sizer that then *sizes* it, we solve
# ONE program that does both: if an arbitrage exists it returns the optimal route
# AND the exact quantities per leg; if none exists it certifies that fact
# (the convex optimum is exactly 0 — a global proof, not a heuristic miss).
#
# Universe of global assets: {BTC, USD, USDT}. USD ≠ USDT (same distinction the
# triangular detector makes — that is what lets a real 3-currency cycle exist).
# BTC is the only intermediate asset; the trade must net to zero BTC and settle
# entirely in cash.
#
# For each venue i the local trade is split into per-level fills on the order book
# (walk-the-book is piecewise-linear, so the whole program is a linear program —
# convex, globally solvable, no local optima). Following the triangular
# convention, the taker fee γ_i = 1 − fee_i is applied to the *received* asset:
#   • BUY  : pay  Σ x_k · ask_k  quote   →  receive  γ · Σ x_k       BTC
#   • SELL : pay  Σ y_k          BTC     →  receive  γ · Σ y_k · bid_k quote
# where x_k, y_k ∈ [0, depth_k] are the BTC quantities matched at each level.
#
# Aggregate net flow Ψ over the global universe:
#   Ψ_BTC  = Σ_i (γ_i Σ_k x_{i,k} − Σ_k y_{i,k})
#   Ψ_USD  = Σ_{i: USD-quoted}  (γ_i Σ y·bid − Σ x·ask)  + conversion flow
#   Ψ_USDT = Σ_{i: USDT-quoted} (γ_i Σ y·bid − Σ x·ask)  + conversion flow
#
#   maximize   p^T Ψ          (p_USD = p_USDT = 1; BTC term vanishes, Ψ_BTC = 0)
#   subject to Ψ_BTC = 0      conservation: no net intermediate BTC, end in cash
#              Ψ_USD ≥ 0      self-financing: never end short any cash currency
#              Ψ_USDT ≥ 0
#              0 ≤ x_k ≤ depth_k,  0 ≤ y_k ≤ depth_k   (order-book liquidity)
#
# Because each cash currency must end non-negative, every leg is funded by the
# proceeds of another — the optimum value is precisely the surplus cash conjured
# out of a closed, self-financing loop, i.e. the arbitrage profit in USD. With no
# arbitrage the only feasible point that survives is "trade nothing", value 0.
#
# Cross-currency loops (buy with USDT, sell for USD) only close if USD can be
# turned back into USDT. We model that par conversion as one more market with a
# small spread `stablecoin_cost`, exactly as the triangular detector's CONVERT
# leg. Without it, only same-quote spatial arbitrage is reachable.

CASH_CURRENCIES: tuple[str, ...] = ("USD", "USDT")

# Profit (USD) below which we declare "no arbitrage". Set comfortably above LP
# solver noise (~1e-6 at BTC price scale) yet far below any real edge.
DEFAULT_MIN_PROFIT_USD = 1e-3


@dataclass(frozen=True)
class ExchangeTrade:
    """The optimal trade routed through one venue. Quantities are in BTC for the
    matched amounts and in the venue's quote currency for the cash legs."""

    exchange: Exchange
    quote_currency: str
    buy_btc: float        # gross BTC matched on the asks (bounded by ask depth)
    sell_btc: float       # gross BTC matched on the bids (bounded by bid depth)
    quote_spent: float    # quote paid to buy (Σ x·ask)
    quote_received: float # quote received from selling, net of fee (γ·Σ y·bid)

    @property
    def fee_rate(self) -> float:
        return get_fee_rate(self.exchange, OrderSide.TAKER)

    @property
    def btc_credited(self) -> float:
        """BTC actually credited from buys, after the taker fee."""
        return (1.0 - self.fee_rate) * self.buy_btc

    @property
    def net_btc(self) -> float:
        return self.btc_credited - self.sell_btc

    @property
    def net_quote(self) -> float:
        return self.quote_received - self.quote_spent

    @property
    def side(self) -> str:
        if self.buy_btc > self.sell_btc:
            return "BUY"
        if self.sell_btc > self.buy_btc:
            return "SELL"
        return "FLAT"


@dataclass(frozen=True)
class ArbitrageResult:
    profit_usd: float
    is_arbitrage: bool
    certificate: str
    trades_per_exchange: dict[Exchange, ExchangeTrade]
    conversions: dict[str, float]  # e.g. {"USD->USDT": 100000.0}
    status: str                    # cvxpy solver status

    @property
    def active_trades(self) -> dict[Exchange, ExchangeTrade]:
        """Only the venues the optimum actually routes through (drops FLAT)."""
        return {ex: t for ex, t in self.trades_per_exchange.items() if t.side != "FLAT"}


def _levels(
    exchange: Exchange,
    bbo_state: dict[Exchange, BBO],
    depth: dict[Exchange, OrderBook] | None,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """(ask_levels, bid_levels) as [(price, qty), ...]. Prefer full order-book
    depth when available, otherwise the single BBO top-of-book level."""
    book = depth.get(exchange) if depth else None
    if book is not None and book.asks and book.bids:
        asks = [(lvl.price, lvl.qty) for lvl in book.asks]
        bids = [(lvl.price, lvl.qty) for lvl in book.bids]
        return asks, bids
    bbo = bbo_state[exchange]
    return [(bbo.ask, bbo.ask_qty)], [(bbo.bid, bbo.bid_qty)]


_ACCEPTABLE = (cp.OPTIMAL, cp.OPTIMAL_INACCURATE)


def _solve(problem: cp.Problem) -> None:
    """Solve the LP, escalating across solvers until one converges.

    CLARABEL is fast and accurate on the well-scaled problem; on the rare
    ill-conditioned tick it can hit its iteration cap (status 'user_limit'), so we
    retry with a larger budget and finally fall back to SCS (a robust first-order
    solver). On a no-arbitrage tick the optimum is a flat 0 and the conic solver
    legitimately reports OPTIMAL_INACCURATE near that degenerate vertex — accepted
    and treated as "no arbitrage" — so silence only that one expected warning.
    """
    attempts = (
        (cp.CLARABEL, {}),
        (cp.CLARABEL, {"max_iter": 50_000}),
        (cp.SCS, {"max_iters": 50_000}),
    )
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="Solution may be inaccurate", category=UserWarning
        )
        for solver, kwargs in attempts:
            try:
                problem.solve(solver=solver, **kwargs)
            except cp.error.SolverError:
                continue
            if problem.status in _ACCEPTABLE and problem.value is not None:
                return
    raise RuntimeError(f"convex arbitrage solver failed: status {problem.status!r}")


def solve_arbitrage(
    bbo_state: dict[Exchange, BBO],
    fees: dict[Exchange, float] | None = None,
    depth: dict[Exchange, OrderBook] | None = None,
    *,
    stablecoin_cost: float = DEFAULT_STABLECOIN_COST,
    min_profit_usd: float = DEFAULT_MIN_PROFIT_USD,
) -> ArbitrageResult:
    """Solve multi-exchange BTC arbitrage as one convex program.

    Args:
        bbo_state: latest top-of-book per exchange (the always-present input).
        fees: taker fee per exchange (0.001 == 10 bps). Defaults to the live
            taker schedule in core.fees for any exchange not overridden.
        depth: optional full order book per exchange; when given, the program
            walks every level (piecewise-linear liquidity) instead of just BBO.
        stablecoin_cost: spread on the USD↔USDT par conversion (per leg). Set 0
            to treat the stablecoin as perfectly fungible with USD.
        min_profit_usd: optimum below this is treated as zero — no arbitrage.

    Returns:
        ArbitrageResult with the optimal profit, the per-venue trade quantities,
        and — when the optimum is 0 — a certificate that no arbitrage exists.
    """
    if stablecoin_cost < 0:
        raise ValueError(f"stablecoin_cost must be >= 0, got {stablecoin_cost}")
    if min_profit_usd < 0:
        raise ValueError(f"min_profit_usd must be >= 0, got {min_profit_usd}")

    fees = fees or {}
    # Only venues we know how to place in the currency graph participate.
    exchanges = [ex for ex in bbo_state if QUOTE_CURRENCY.get(ex) is not None]

    if not exchanges:
        return ArbitrageResult(
            profit_usd=0.0,
            is_arbitrage=False,
            certificate="no arbitrage exists (no mappable exchanges in state)",
            trades_per_exchange={},
            conversions={},
            status="EMPTY",
        )

    # Net flow accumulators over the global cash universe and the BTC intermediate.
    psi_btc: cp.Expression = cp.Constant(0.0)
    psi_cash: dict[str, cp.Expression] = {c: cp.Constant(0.0) for c in CASH_CURRENCIES}

    constraints: list[cp.Constraint] = []
    buy_vars: dict[Exchange, cp.Variable] = {}
    sell_vars: dict[Exchange, cp.Variable] = {}
    venue_meta: dict[Exchange, tuple[str, np.ndarray, np.ndarray]] = {}
    total_cash_capacity = 0.0

    # Numerical conditioning: BTC prices (~1e5) on O(1) quantities make the LP
    # badly scaled — at low fees, where arbitrage is dense, the conic solver can
    # exhaust its iteration budget. Normalize every price by a representative BTC
    # price so the constraint data is O(1); the cash objective then comes out in
    # units of `scale`, which we multiply back at the end. Quantities (BTC) are
    # already O(1) and stay unscaled, so conservation Ψ_BTC = 0 is untouched.
    scale = max(bbo_state[ex].ask for ex in exchanges)

    for ex in exchanges:
        quote = QUOTE_CURRENCY[ex]
        gamma = 1.0 - fees.get(ex, get_fee_rate(ex, OrderSide.TAKER))
        asks, bids = _levels(ex, bbo_state, depth)

        ask_p = np.array([p for p, _ in asks], dtype=float)
        ask_q = np.array([q for _, q in asks], dtype=float)
        bid_p = np.array([p for p, _ in bids], dtype=float)
        bid_q = np.array([q for _, q in bids], dtype=float)

        x = cp.Variable(len(asks), nonneg=True)  # gross BTC matched on asks
        y = cp.Variable(len(bids), nonneg=True)  # gross BTC matched on bids
        constraints += [x <= ask_q, y <= bid_q]
        buy_vars[ex] = x
        sell_vars[ex] = y
        venue_meta[ex] = (quote, ask_p, bid_p)  # TRUE prices, for USD reporting

        # Local flow (prices scaled): buys credit γ·x BTC and cost x·(ask/scale)
        # quote; sells deliver y BTC and credit γ·y·(bid/scale) quote.
        psi_btc = psi_btc + gamma * cp.sum(x) - cp.sum(y)
        quote_spent = (ask_p / scale) @ x
        quote_received = gamma * ((bid_p / scale) @ y)
        psi_cash[quote] = psi_cash[quote] + quote_received - quote_spent

        total_cash_capacity += float((ask_p / scale) @ ask_q) + float((bid_p / scale) @ bid_q)

    # USD↔USDT par conversion, modelled as one more market — only when both cash
    # currencies are actually present (otherwise no cross-currency loop to close).
    present_quotes = {QUOTE_CURRENCY[ex] for ex in exchanges}
    conversion_vars: dict[str, cp.Variable] = {}
    convertibles = sorted(present_quotes & CONVERTIBLE_CURRENCIES & set(CASH_CURRENCIES))
    conv_gamma = 1.0 - stablecoin_cost
    cap = total_cash_capacity if total_cash_capacity > 0 else 1.0
    for src in convertibles:
        for dst in convertibles:
            if src == dst:
                continue
            u = cp.Variable(nonneg=True)  # units of `src` converted into `dst`
            # Bound conversions by total cash on the books — keeps the LP well
            # posed (no degenerate back-and-forth cycling) without clipping any
            # real solution, which can never exceed available liquidity.
            constraints.append(u <= cap)
            conversion_vars[f"{src}->{dst}"] = u
            psi_cash[src] = psi_cash[src] - u
            psi_cash[dst] = psi_cash[dst] + conv_gamma * u

    # Conservation + self-financing. Objective = total net cash (p = 1 for both
    # cash currencies; the BTC price term drops out since Ψ_BTC is pinned to 0).
    constraints.append(psi_btc == 0)
    for c in CASH_CURRENCIES:
        constraints.append(psi_cash[c] >= 0)
    objective = cp.Maximize(psi_cash["USD"] + psi_cash["USDT"])

    problem = cp.Problem(objective, constraints)
    _solve(problem)

    # Rescale the objective (in units of `scale`) back to USD.
    profit = max(float(problem.value) * scale, 0.0)
    is_arb = profit > min_profit_usd

    trades = _extract_trades(venue_meta, buy_vars, sell_vars, fees, active=is_arb)
    conversions = (
        # Conversion variables are in scaled-quote units → back to USD via `scale`.
        {k: round(float(v.value) * scale, 8) for k, v in conversion_vars.items()
         if v.value is not None and float(v.value) * scale > 1e-3}
        if is_arb else {}
    )

    if is_arb:
        certificate = (
            f"arbitrage exists: optimal self-financing profit ${profit:.2f} "
            f"(convex optimum > 0), routed through {len(trades)} venue(s)"
        )
    else:
        certificate = "no arbitrage exists (convex optimum = 0)"

    return ArbitrageResult(
        profit_usd=profit,
        is_arbitrage=is_arb,
        certificate=certificate,
        trades_per_exchange=trades,
        conversions=conversions,
        status=str(problem.status),
    )


def _extract_trades(
    venue_meta: dict[Exchange, tuple[str, np.ndarray, np.ndarray]],
    buy_vars: dict[Exchange, cp.Variable],
    sell_vars: dict[Exchange, cp.Variable],
    fees: dict[Exchange, float],
    *,
    active: bool,
) -> dict[Exchange, ExchangeTrade]:
    """Collapse the per-level fills back into one trade per venue. When there is
    no arbitrage we report flat trades — there is nothing to execute."""
    trades: dict[Exchange, ExchangeTrade] = {}
    for ex, (quote, ask_p, bid_p) in venue_meta.items():
        if not active:
            trades[ex] = ExchangeTrade(ex, quote, 0.0, 0.0, 0.0, 0.0)
            continue
        gamma = 1.0 - fees.get(ex, get_fee_rate(ex, OrderSide.TAKER))
        x = np.asarray(buy_vars[ex].value).reshape(-1)
        y = np.asarray(sell_vars[ex].value).reshape(-1)
        # Clamp solver dust (sub-µBTC) to zero so reported quantities are clean.
        x = np.where(x > 1e-6, x, 0.0)
        y = np.where(y > 1e-6, y, 0.0)
        trades[ex] = ExchangeTrade(
            exchange=ex,
            quote_currency=quote,
            buy_btc=float(x.sum()),
            sell_btc=float(y.sum()),
            quote_spent=float(ask_p @ x),
            quote_received=float(gamma * (bid_p @ y)),
        )
    return trades


def arbitrage_to_dict(result: ArbitrageResult) -> dict:
    """JSON-serializable form for the REST endpoint / WS broadcast (used once the
    module is wired into the pipeline)."""
    return {
        "profit_usd": result.profit_usd,
        "is_arbitrage": result.is_arbitrage,
        "certificate": result.certificate,
        "status": result.status,
        "conversions": result.conversions,
        "trades": [
            {
                "exchange": t.exchange.value,
                "quote_currency": t.quote_currency,
                "side": t.side,
                "buy_btc": t.buy_btc,
                "sell_btc": t.sell_btc,
                "btc_credited": t.btc_credited,
                "quote_spent": t.quote_spent,
                "quote_received": t.quote_received,
                "net_btc": t.net_btc,
                "net_quote": t.net_quote,
            }
            for t in result.trades_per_exchange.values()
            if t.side != "FLAT"
        ],
    }
