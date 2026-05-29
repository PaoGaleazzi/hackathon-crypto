from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from core.fees import OrderSide, estimate_withdrawal_cost, get_fee_rate
from models.market import BBO, Exchange

# Every venue trades BTC against its quote currency.
BASE_CURRENCY = "BTC"

# Default capital (in the held/start currency, ~USDT) used to turn the fixed BTC
# withdrawal fee into an absolute net profit. The headline net_profit_pct stays
# size-independent (fees only); net_profit is this notional minus withdrawal.
DEFAULT_NOTIONAL = 10_000.0

# Quote currency each exchange settles BTC against. USD and USDT are DISTINCT
# graph nodes — that is precisely what makes a real 3-currency triangle possible
# across venues that each only stream a single BTC pair. Without this distinction
# a "triangle" over one asset degenerates into two-venue spatial arbitrage.
QUOTE_CURRENCY: dict[Exchange, str] = {
    Exchange.BINANCE: "USDT",
    Exchange.OKX: "USDT",
    Exchange.BYBIT: "USDT",
    Exchange.KRAKEN: "USD",
    Exchange.COINBASE: "USD",
    Exchange.GEMINI: "USD",
    Exchange.BITSTAMP: "USD",
}

# Fiat/stablecoins assumed convertible near par (USDT≈USD). The conversion is NOT
# free: the default cost is a small spread. Feed a real USDT/USD quote here for
# production. With fewer than two of these present in the state, no triangle
# exists and the detector correctly returns nothing.
CONVERTIBLE_CURRENCIES = frozenset({"USD", "USDT", "USDC"})
DEFAULT_STABLECOIN_COST = 0.0001  # 1 bp per conversion leg

# NOTE: net_profit_pct nets the three legs' trading/conversion fees only (two
# taker fees + one stablecoin spread) and is size-independent. net_profit also
# subtracts the fixed BTC withdrawal cost (transferring BTC out of the BUY venue
# to the SELL venue) for the given notional. Latency/slippage are NOT modeled.


@dataclass(frozen=True)
class TriangularLeg:
    src: str
    dst: str
    action: str  # "BUY" (quote→BTC), "SELL" (BTC→quote), "CONVERT" (quote→quote)
    exchange: Exchange | None  # None for a stablecoin conversion
    price: float | None        # ask for BUY, bid for SELL, None for CONVERT
    fee_rate: float
    rate: float                # net units of dst received per 1 unit of src


@dataclass(frozen=True)
class TriangularOpportunity:
    cycle: tuple[str, str, str]  # currencies in traversal order: c1→c2→c3→c1
    legs: tuple[TriangularLeg, TriangularLeg, TriangularLeg]
    net_multiplier: float        # product of leg rates; > 1.0 means profit
    net_profit_pct: float        # (net_multiplier - 1) * 100, fees only
    notional: float              # capital assumed for the absolute figures below
    withdrawal_cost: float       # fixed BTC-transfer cost out of the BUY venue
    net_profit: float            # notional*(net_multiplier-1) - withdrawal_cost

    @property
    def path(self) -> str:
        c1, c2, c3 = self.cycle
        return f"{c1}→{c2}→{c3}→{c1}"


def _build_legs(
    bbo_state: dict[Exchange, BBO], stablecoin_cost: float
) -> list[TriangularLeg]:
    """Directed edges of the currency graph: two per BBO (buy/sell BTC) plus the
    stablecoin conversions between every pair of convertible quote currencies."""
    legs: list[TriangularLeg] = []
    present_quotes: set[str] = set()

    for exchange, bbo in bbo_state.items():
        quote = QUOTE_CURRENCY.get(exchange)
        if quote is None:  # unmapped exchange can't be placed in the graph
            continue
        present_quotes.add(quote)
        fee = get_fee_rate(exchange, OrderSide.TAKER)
        legs.append(TriangularLeg(
            src=quote, dst=BASE_CURRENCY, action="BUY", exchange=exchange,
            price=bbo.ask, fee_rate=fee, rate=(1.0 - fee) / bbo.ask,
        ))
        legs.append(TriangularLeg(
            src=BASE_CURRENCY, dst=quote, action="SELL", exchange=exchange,
            price=bbo.bid, fee_rate=fee, rate=bbo.bid * (1.0 - fee),
        ))

    convertibles = sorted(present_quotes & CONVERTIBLE_CURRENCIES)
    convert_rate = 1.0 - stablecoin_cost
    for src in convertibles:
        for dst in convertibles:
            if src == dst:
                continue
            legs.append(TriangularLeg(
                src=src, dst=dst, action="CONVERT", exchange=None,
                price=None, fee_rate=stablecoin_cost, rate=convert_rate,
            ))
    return legs


def _make_opportunity(
    legs: tuple[TriangularLeg, TriangularLeg, TriangularLeg],
    notional: float,
) -> TriangularOpportunity:
    """Rotate the cycle to start at the BUY leg (the cash you hold → BTC). This
    collapses the three rotations of one loop into a single canonical form and
    reads as the intuitive 'hold cash → buy BTC → sell BTC → convert back'."""
    buy_index = next((i for i, leg in enumerate(legs) if leg.action == "BUY"), 0)
    rotated = legs[buy_index:] + legs[:buy_index]
    net_multiplier = rotated[0].rate * rotated[1].rate * rotated[2].rate

    # BTC bought on the BUY venue must be withdrawn to the SELL venue — a fixed
    # cost (BTC fee × price), independent of notional.
    buy_leg = rotated[0]
    withdrawal_cost = (
        estimate_withdrawal_cost(buy_leg.exchange, buy_leg.price)
        if buy_leg.exchange is not None and buy_leg.price is not None
        else 0.0
    )
    net_profit = notional * (net_multiplier - 1.0) - withdrawal_cost

    return TriangularOpportunity(
        cycle=(rotated[0].src, rotated[1].src, rotated[2].src),
        legs=rotated,
        net_multiplier=net_multiplier,
        net_profit_pct=(net_multiplier - 1.0) * 100.0,
        notional=notional,
        withdrawal_cost=withdrawal_cost,
        net_profit=net_profit,
    )


def detect_triangular(
    bbo_state: dict[Exchange, BBO],
    *,
    stablecoin_cost: float = DEFAULT_STABLECOIN_COST,
    min_profit_pct: float = 0.0,
    notional: float = DEFAULT_NOTIONAL,
) -> list[TriangularOpportunity]:
    """Find profitable 3-currency arbitrage cycles (e.g. USDT→BTC→USD→USDT).

    Each cycle uses three DISTINCT currencies, so it is never a disguised
    two-venue spatial trade. Profit is the product of the three legs' net rates.
    Returns opportunities with net_profit_pct > min_profit_pct, best first.
    `notional` only scales the reported absolute net_profit; the filter is on the
    size-independent net_profit_pct (fees only).
    """
    if stablecoin_cost < 0:
        raise ValueError(f"stablecoin_cost must be >= 0, got {stablecoin_cost}")
    if notional <= 0:
        raise ValueError(f"notional must be positive, got {notional}")

    out_legs: dict[str, list[TriangularLeg]] = defaultdict(list)
    for leg in _build_legs(bbo_state, stablecoin_cost):
        out_legs[leg.src].append(leg)

    seen: set[tuple] = set()
    opportunities: list[TriangularOpportunity] = []

    for c1, first_legs in out_legs.items():
        for e1 in first_legs:
            c2 = e1.dst
            if c2 == c1:
                continue
            for e2 in out_legs.get(c2, ()):
                c3 = e2.dst
                if c3 in (c1, c2):
                    continue
                for e3 in out_legs.get(c3, ()):
                    if e3.dst != c1:
                        continue
                    opp = _make_opportunity((e1, e2, e3), notional)
                    if opp.net_profit_pct <= min_profit_pct:
                        continue
                    key = tuple(
                        (leg.src, leg.dst, leg.exchange, leg.price) for leg in opp.legs
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    opportunities.append(opp)

    opportunities.sort(key=lambda o: o.net_profit_pct, reverse=True)
    return opportunities


def triangular_to_dict(opp: TriangularOpportunity) -> dict:
    """JSON-serializable form for the WS broadcast and the REST endpoint."""
    return {
        "path": opp.path,
        "cycle": list(opp.cycle),
        "net_multiplier": opp.net_multiplier,
        "net_profit_pct": opp.net_profit_pct,
        "notional": opp.notional,
        "withdrawal_cost": opp.withdrawal_cost,
        "net_profit": opp.net_profit,
        "legs": [
            {
                "src": leg.src,
                "dst": leg.dst,
                "action": leg.action,
                "exchange": leg.exchange.value if leg.exchange is not None else None,
                "price": leg.price,
                "fee_rate": leg.fee_rate,
                "rate": leg.rate,
            }
            for leg in opp.legs
        ],
    }


# ── in-memory latest-detection cache ─────────────────────────────────────────────
# Detection is 100% in-memory (never DuckDB), consistent with the BBO hot path.
# The pipeline writes here every tick; GET /api/triangular reads it.

_latest_opportunities: list[TriangularOpportunity] = []


def set_latest_opportunities(opportunities: list[TriangularOpportunity]) -> None:
    global _latest_opportunities
    _latest_opportunities = opportunities


def get_latest_opportunities() -> list[TriangularOpportunity]:
    return list(_latest_opportunities)
