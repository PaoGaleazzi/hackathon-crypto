from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from core.convex_arb import DEFAULT_MIN_PROFIT_USD, solve_arbitrage
from core.fees import OrderSide, get_fee_rate
from core.metrics_eval import percentile
from core.scanner import scan_for_opportunities
from core.triangular import (
    CONVERTIBLE_CURRENCIES,
    DEFAULT_STABLECOIN_COST,
    QUOTE_CURRENCY,
    detect_triangular,
)
from models.market import BBO, Exchange

# ── Validating convex_arb against the separate scanner+triangular detectors ──────
#
# The convex program (core.convex_arb) claims to UNIFY two things the live system
# does in separate modules: spatial detection (core.scanner) and triangular-cycle
# detection (core.triangular). This module replays a recorded tick stream and
# checks that claim three ways — the questions the A/B harness must answer:
#
#   1. Does convex flag the SAME opportunities? — every profitable single-BTC-hop
#      cycle is reproduced here by an independent brute force over directed venue
#      pairs (with USD↔USDT conversion), on the IDENTICAL taker-fee + stablecoin
#      cost basis the LP uses. Existence of any profitable cycle ⇔ the LP optimum
#      is > 0 (multi-venue routing changes the optimal SIZE, never whether one
#      exists), so the two must agree tick for tick. A genuine disagreement is a
#      bug; a sub-dollar straddle of the threshold is a boundary tie, bucketed apart.
#
#   2. Is the "no arbitrage" certificate consistent? — on every tick the LP
#      certifies no-arb, the brute force must independently find no profitable
#      cycle.
#
#   3. What does the solver cost per tick? — the convex route buys unification at
#      the price of an LP solve; we record the wall-clock per tick so the hot-path
#      tradeoff against the microsecond scanner is explicit.
#
# A small "production context" tally also runs the REAL scanner/triangular at live
# costs (which additionally charge withdrawal/latency/slippage, so they are
# strictly stricter than the pure-price basis) — to relate the validation to what
# the deployed system would actually flag.


def default_taker_fees(fee_multiplier: float = 1.0) -> dict[Exchange, float]:
    """Live taker fee per exchange, optionally scaled to model a maker/VIP tier."""
    if fee_multiplier < 0:
        raise ValueError(f"fee_multiplier must be >= 0, got {fee_multiplier}")
    return {
        ex: get_fee_rate(ex, OrderSide.TAKER) * fee_multiplier for ex in QUOTE_CURRENCY
    }


@dataclass(frozen=True)
class CycleEdge:
    """The most profitable single-BTC-hop cycle on one tick: buy BTC on
    ``buy_exchange``, sell on ``sell_exchange`` (converting quote currencies at par
    when they differ). ``profit_usd`` is the depth-limited profit on that one pair —
    a lower bound on the convex optimum, but with the SAME sign."""

    buy_exchange: Exchange | None
    sell_exchange: Exchange | None
    multiplier: float   # net units of buy-quote out per unit in; > 1 ⇒ arbitrage
    profit_usd: float

    @property
    def exists(self) -> bool:
        return self.buy_exchange is not None


_NO_EDGE = CycleEdge(None, None, 1.0, 0.0)


def best_cycle_edge(
    state: dict[Exchange, BBO],
    fees: dict[Exchange, float],
    stablecoin_cost: float = DEFAULT_STABLECOIN_COST,
) -> CycleEdge:
    """Brute force the best buy@i → sell@j cycle on the convex cost basis.

    Mirrors solve_arbitrage's economics exactly: the taker fee γ = 1 − fee is
    applied to each leg's received asset and a (1 − stablecoin_cost) factor closes
    a cross-quote loop (USDT↔USD). Selects the pair of maximum depth-limited PROFIT
    — the same objective the LP maximizes, so the chosen venue pair lines up with
    convex's route — and its sign is what the convex optimum's sign must match."""
    best = _NO_EDGE
    convertibles = CONVERTIBLE_CURRENCIES
    conv_gamma = 1.0 - stablecoin_cost

    for buy_ex, buy in state.items():
        quote_b = QUOTE_CURRENCY.get(buy_ex)
        if quote_b is None:
            continue
        gamma_b = 1.0 - fees.get(buy_ex, get_fee_rate(buy_ex, OrderSide.TAKER))
        for sell_ex, sell in state.items():
            if sell_ex == buy_ex:
                continue
            quote_s = QUOTE_CURRENCY.get(sell_ex)
            if quote_s is None:
                continue
            if quote_b != quote_s:
                # Cross-quote loop only closes if both ends are par-convertible.
                if quote_b not in convertibles or quote_s not in convertibles:
                    continue
                conv = conv_gamma
            else:
                conv = 1.0
            gamma_s = 1.0 - fees.get(sell_ex, get_fee_rate(sell_ex, OrderSide.TAKER))

            # Net buy-quote returned per buy-quote spent, round trip.
            multiplier = gamma_b * gamma_s * conv * sell.bid / buy.ask
            # Depth: buy up to ask_qty BTC; the γ_b·qty credited must fit the sell
            # side's bid depth. profit accrues as (multiplier − 1) × quote spent.
            qty = min(buy.ask_qty, sell.bid_qty / gamma_b)
            profit = (multiplier - 1.0) * qty * buy.ask
            if profit > best.profit_usd:
                best = CycleEdge(buy_ex, sell_ex, multiplier, profit)

    return best


@dataclass
class StrategyComparison:
    """Aggregated convex-vs-classic agreement over one replayed tick stream."""

    fee_multiplier: float
    stablecoin_cost: float
    min_profit_usd: float
    boundary_usd: float

    ticks: int = 0
    state_ready: int = 0          # ticks with >= 2 mappable venues (decidable)

    both_arb: int = 0
    both_none: int = 0
    convex_only: int = 0
    classic_only: int = 0
    boundary: int = 0             # disagreements where the edge is sub-$boundary
    mismatches: list[dict] = field(default_factory=list)  # genuine inconsistencies

    direction_total: int = 0      # both-arb ticks
    direction_matches: int = 0    # ... where buy/sell venue agrees

    convex_no_arb_certs: int = 0  # ticks convex certified no-arbitrage
    brute_agrees_no_arb: int = 0  # ... where brute force independently found none

    # Production-context tallies, real (unmodified) cost model.
    scanner_spatial_ticks: int = 0
    triangular_ticks: int = 0

    solve_latencies_ms: list[float] = field(default_factory=list)

    @property
    def agreements(self) -> int:
        return self.both_arb + self.both_none + self.boundary

    @property
    def genuine_mismatches(self) -> int:
        """Ticks where convex and brute force truly disagree (beyond the boundary
        band). The ``mismatches`` list only samples these; this is the full count."""
        return self.convex_only + self.classic_only

    @property
    def consistency(self) -> float:
        """Share of decidable ticks where convex and brute agree (boundary ties
        counted as agreement; only genuine mismatches break it)."""
        return self.agreements / self.state_ready if self.state_ready else 1.0


def _convex_direction(result) -> tuple[Exchange | None, Exchange | None]:
    """The venue convex buys the most BTC on and the one it sells the most on."""
    buy_ex = sell_ex = None
    best_buy = best_sell = 0.0
    for ex, t in result.trades_per_exchange.items():
        if t.buy_btc > best_buy:
            best_buy, buy_ex = t.buy_btc, ex
        if t.sell_btc > best_sell:
            best_sell, sell_ex = t.sell_btc, ex
    return buy_ex, sell_ex


def compare_strategies(
    ticks: Iterable[BBO],
    *,
    fee_multiplier: float = 1.0,
    stablecoin_cost: float = DEFAULT_STABLECOIN_COST,
    min_profit_usd: float = DEFAULT_MIN_PROFIT_USD,
    boundary_usd: float = 1.0,
    production_context: bool = True,
    clock: Callable[[], float] = time.perf_counter,
    max_mismatch_samples: int = 20,
) -> StrategyComparison:
    """Replay ``ticks``, comparing convex_arb.solve_arbitrage against the
    equivalent brute-force detector on every tick.

    ``boundary_usd`` is the band around the detection threshold within which a
    convex/classic disagreement is treated as a numerical tie rather than a bug
    (the optimum and the single-pair lower bound can straddle the threshold by a
    few cents). ``clock`` is injectable so tests stay deterministic.
    """
    fees = default_taker_fees(fee_multiplier)
    cmp = StrategyComparison(
        fee_multiplier=fee_multiplier,
        stablecoin_cost=stablecoin_cost,
        min_profit_usd=min_profit_usd,
        boundary_usd=boundary_usd,
    )
    state: dict[Exchange, BBO] = {}

    for bbo in ticks:
        cmp.ticks += 1
        state[bbo.exchange] = bbo
        decidable = sum(1 for ex in state if QUOTE_CURRENCY.get(ex) is not None) >= 2
        if not decidable:
            continue
        cmp.state_ready += 1

        edge = best_cycle_edge(state, fees, stablecoin_cost)
        classic_arb = edge.profit_usd > min_profit_usd

        t0 = clock()
        result = solve_arbitrage(
            state, fees=fees, stablecoin_cost=stablecoin_cost,
            min_profit_usd=min_profit_usd,
        )
        cmp.solve_latencies_ms.append((clock() - t0) * 1000.0)
        convex_arb = result.is_arbitrage

        if convex_arb:
            if classic_arb:
                cmp.both_arb += 1
                cmp.direction_total += 1
                cb, cs = _convex_direction(result)
                if cb == edge.buy_exchange and cs == edge.sell_exchange:
                    cmp.direction_matches += 1
            elif result.profit_usd <= boundary_usd:
                cmp.boundary += 1
            else:
                cmp.convex_only += 1
                _record_mismatch(cmp, bbo, edge, result, "convex_only", max_mismatch_samples)
        else:
            cmp.convex_no_arb_certs += 1
            if not classic_arb:
                cmp.both_none += 1
                cmp.brute_agrees_no_arb += 1
            elif edge.profit_usd <= boundary_usd:
                cmp.boundary += 1
                cmp.brute_agrees_no_arb += 1
            else:
                cmp.classic_only += 1
                _record_mismatch(cmp, bbo, edge, result, "classic_only", max_mismatch_samples)

        if production_context:
            now = bbo.ws_received_at
            if scan_for_opportunities(state, now=now):
                cmp.scanner_spatial_ticks += 1
            if detect_triangular(state):
                cmp.triangular_ticks += 1

    return cmp


def _record_mismatch(cmp, bbo, edge, result, kind, cap):
    if len(cmp.mismatches) < cap:
        cmp.mismatches.append(
            {
                "tick_exchange": bbo.exchange.value,
                "ws_received_at": bbo.ws_received_at.isoformat(),
                "kind": kind,
                "brute_profit_usd": round(edge.profit_usd, 6),
                "brute_pair": (
                    f"{edge.buy_exchange.value}->{edge.sell_exchange.value}"
                    if edge.exists else None
                ),
                "convex_profit_usd": round(result.profit_usd, 6),
            }
        )


def render_comparison(cmp: StrategyComparison, *, source: str) -> str:
    """Human-readable validation report answering the three harness questions."""
    lat = cmp.solve_latencies_ms
    dir_pct = (
        100.0 * cmp.direction_matches / cmp.direction_total
        if cmp.direction_total else 100.0
    )
    lines = [
        f"═ Convex arbitrage validation · {source} ═",
        "",
        f"Cost basis: taker fees ×{cmp.fee_multiplier:g}  "
        f"stablecoin {cmp.stablecoin_cost:g}  "
        f"min-profit ${cmp.min_profit_usd:g}  boundary ${cmp.boundary_usd:g}",
        "",
        "── Q1/Q2 · convex vs equivalent brute-force (identical cost basis) ──",
        f"  ticks replayed              : {cmp.ticks}",
        f"  decidable (≥2 venues)       : {cmp.state_ready}",
        f"  both detect arbitrage       : {cmp.both_arb}"
        f"   (same best venue pair {cmp.direction_matches}/{cmp.direction_total}"
        f" = {dir_pct:.1f}%; gaps are alternate optima, not errors)",
        f"  both certify no-arbitrage   : {cmp.both_none}",
        f"  boundary ties (≤${cmp.boundary_usd:g})       : {cmp.boundary}",
        f"  convex-only (real)          : {cmp.convex_only}",
        f"  classic-only (real)         : {cmp.classic_only}",
        f"  GENUINE MISMATCHES          : {cmp.genuine_mismatches}"
        f"  {'✓ none' if not cmp.genuine_mismatches else '✗ SEE BELOW'}",
        f"  → detection consistency     : {cmp.consistency:.4%}",
        "",
        "── no-arbitrage certificate consistency ──",
        f"  convex 'no arbitrage' certs : {cmp.convex_no_arb_certs}",
        f"  brute force agrees no-arb   : {cmp.brute_agrees_no_arb}"
        + (
            f"  ({100.0 * cmp.brute_agrees_no_arb / cmp.convex_no_arb_certs:.2f}%)"
            if cmp.convex_no_arb_certs else "  (n/a)"
        ),
    ]
    if cmp.scanner_spatial_ticks or cmp.triangular_ticks or cmp.state_ready:
        lines += [
            "",
            "── production context · live cost model (incl. withdrawal/latency) ──",
            f"  scanner spatial opps (≥1/tick) : {cmp.scanner_spatial_ticks} ticks",
            f"  triangular cycles (≥1/tick)    : {cmp.triangular_ticks} ticks",
            "  note: the live scanner also charges withdrawal+latency+slippage, so "
            "it is\n        strictly stricter than the pure-price convex/triangular "
            "basis above.",
        ]
    if lat:
        lines += [
            "",
            "── Q3 · convex solver latency per tick (ms) ──",
            f"  p50 {percentile(lat, 50):.3f}   p95 {percentile(lat, 95):.3f}   "
            f"p99 {percentile(lat, 99):.3f}   max {max(lat):.3f}   "
            f"mean {sum(lat) / len(lat):.3f}",
        ]
    if cmp.mismatches:
        lines += ["", "── genuine mismatches (sample) ──"]
        lines += [f"  {m}" for m in cmp.mismatches]
    return "\n".join(lines)
