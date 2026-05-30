from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.fees import OrderSide, get_fee_rate
from models.market import BBO, Exchange

# ── Funding-rate arbitrage on BTC perpetuals ─────────────────────────────────────
#
# Perpetual futures have no expiry, so an 8-hourly *funding* payment ties the perp
# price to spot: when the perp trades above index (longs crowded) longs PAY shorts;
# when below, shorts pay longs. The rate is small per period but compounds — at the
# 2026 BTC average (~0.05%/8h) that is ~55% annualized, far above the spatial edge
# which is arbitraged away. Two market-neutral ways to harvest it:
#
#   1. CASH-AND-CARRY (single venue): hold +1 BTC spot and −1 BTC perp. Delta is
#      zero — a spot move is exactly offset by the perp leg — yet you keep collecting
#      funding every period. With positive funding you are the short (you RECEIVE);
#      with negative funding the whole structure flips (long perp / short spot) and
#      you receive again. Net edge per period = |funding| − (spot_fee + perp_fee).
#
#   2. CROSS-EXCHANGE FUNDING (two venues, no spot): short the perp where funding is
#      HIGH (receive it) and long the perp where funding is LOW (pay it). The BTC
#      exposure of the two perps cancels, so you are delta-neutral and pocket the
#      funding *spread*. Net per period = |fund_A − fund_B| − (fee_A + fee_B)·2,
#      charging a full round-trip (entry + exit) on both legs.
#
# Everything here is a pure function of in-memory state — no WS, no DB. The detector
# just keeps the latest funding/spot snapshots and re-scores on each update.

# BTC perps fund every 8h → 3 periods/day.
PERIODS_PER_DAY: int = 3
DAYS_PER_YEAR: int = 365

# Annualized net return (fraction) below which an opportunity is not worth flagging.
# 0.0 means "any strictly positive carry after fees"; callers can raise the bar.
DEFAULT_MIN_ANNUALIZED_RETURN: float = 0.0


@dataclass(frozen=True)
class FundingRate:
    """Latest funding snapshot for one perpetual contract on one venue.

    `rate` is the per-period funding rate as a fraction (0.0005 == 0.05% per 8h)
    and MAY be negative — a negative rate means shorts pay longs.
    """

    exchange: Exchange
    symbol: str
    rate: float
    next_funding_time: datetime
    mark_price: float
    index_price: float
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.mark_price <= 0:
            raise ValueError(f"mark_price must be positive, got {self.mark_price}")
        if self.index_price <= 0:
            raise ValueError(f"index_price must be positive, got {self.index_price}")


@dataclass(frozen=True)
class CashCarryOpportunity:
    """A single-venue cash-and-carry: long spot + short perp (or the mirror when
    funding is negative). All rates are fractions; per-period quantities are the
    funding/fee figures, annualized_return is the compounded yearly yield."""

    exchange: Exchange
    symbol: str
    direction: str          # "long_spot_short_perp" | "short_spot_long_perp"
    funding_rate: float     # raw per-period rate (signed)
    funding_capture: float  # per-period rate actually captured (always >= 0)
    total_fees: float       # spot_fee + perp_fee (per period, both legs)
    net_after_fees: float   # funding_capture - total_fees, per period
    annualized_return: float
    profitable: bool


@dataclass(frozen=True)
class CrossExchangeFundingOpportunity:
    """A delta-neutral cross-exchange funding trade: short the perp on
    `short_exchange` (high funding, received) and long it on `long_exchange`
    (low funding, paid)."""

    symbol: str
    long_exchange: Exchange   # pay the low funding here (long perp)
    short_exchange: Exchange  # receive the high funding here (short perp)
    funding_spread: float     # |funding_short - funding_long|, always >= 0
    total_fees: float         # (fee_long + fee_short) * 2  (entry + exit)
    net_after_fees: float     # funding_spread - total_fees, per period
    annualized_return: float
    profitable: bool


def annualized_funding_return(
    rate_per_period: float, periods_per_day: int = PERIODS_PER_DAY
) -> float:
    """Simple (non-compounded) annualization of a per-period funding rate.

    0.0005 per 8h → 0.0005 * 3 * 365 = 0.5475 (54.75% APR).
    """
    if periods_per_day <= 0:
        raise ValueError(f"periods_per_day must be positive, got {periods_per_day}")
    return rate_per_period * periods_per_day * DAYS_PER_YEAR


def _taker_fee(exchange: Exchange, fees: dict[Exchange, float] | None) -> float:
    """Per-leg taker fee for a venue, overridable via `fees`, else the live schedule."""
    if fees is not None and exchange in fees:
        return fees[exchange]
    return get_fee_rate(exchange, OrderSide.TAKER)


def detect_cash_and_carry(
    spot_bbo: dict[Exchange, BBO],
    perp_funding: dict[Exchange, FundingRate],
    fees: dict[Exchange, float] | None = None,
    *,
    periods_per_day: int = PERIODS_PER_DAY,
    min_annualized_return: float = DEFAULT_MIN_ANNUALIZED_RETURN,
) -> list[CashCarryOpportunity]:
    """Find per-venue cash-and-carry trades whose fee-net funding clears the bar.

    A venue qualifies only if it has BOTH a spot quote and a perp funding rate
    (the structure needs both legs). For each, the captured rate is |funding|
    (you always take the receiving side); the direction records which side that is.

    Returns opportunities sorted by annualized_return, descending.
    """
    opportunities: list[CashCarryOpportunity] = []

    for exchange, funding in perp_funding.items():
        if exchange not in spot_bbo:
            continue  # no spot leg to hedge the perp — skip

        spot_fee = _taker_fee(exchange, fees)
        perp_fee = _taker_fee(exchange, fees)
        total_fees = spot_fee + perp_fee

        funding_capture = abs(funding.rate)
        # Positive funding: longs pay shorts → be short the perp, long the spot.
        # Negative funding: shorts pay longs → be long the perp, short the spot.
        direction = (
            "long_spot_short_perp" if funding.rate >= 0 else "short_spot_long_perp"
        )

        net_after_fees = funding_capture - total_fees
        annualized = annualized_funding_return(net_after_fees, periods_per_day)

        opportunities.append(
            CashCarryOpportunity(
                exchange=exchange,
                symbol=funding.symbol,
                direction=direction,
                funding_rate=funding.rate,
                funding_capture=funding_capture,
                total_fees=total_fees,
                net_after_fees=net_after_fees,
                annualized_return=annualized,
                profitable=annualized > min_annualized_return,
            )
        )

    opportunities.sort(key=lambda o: o.annualized_return, reverse=True)
    return opportunities


def detect_cross_exchange_funding(
    funding_rates: dict[Exchange, FundingRate],
    fees: dict[Exchange, float] | None = None,
    *,
    periods_per_day: int = PERIODS_PER_DAY,
    min_annualized_return: float = DEFAULT_MIN_ANNUALIZED_RETURN,
) -> list[CrossExchangeFundingOpportunity]:
    """Find delta-neutral funding-spread trades across pairs of venues.

    For each unordered pair we short the higher-funding perp and long the
    lower-funding one. The spread |fund_A − fund_B| must clear a full round-trip
    of fees on both legs ((fee_A + fee_B)·2) to be net-positive.

    Returns opportunities sorted by annualized_return, descending.
    """
    opportunities: list[CrossExchangeFundingOpportunity] = []

    exchanges = list(funding_rates)
    for i in range(len(exchanges)):
        for j in range(i + 1, len(exchanges)):
            ex_a, ex_b = exchanges[i], exchanges[j]
            fr_a, fr_b = funding_rates[ex_a], funding_rates[ex_b]

            # Short where funding is higher (receive), long where lower (pay).
            if fr_a.rate >= fr_b.rate:
                short_ex, long_ex = ex_a, ex_b
            else:
                short_ex, long_ex = ex_b, ex_a

            funding_spread = abs(fr_a.rate - fr_b.rate)
            # Entry and exit on both legs → 2× the per-leg taker fee on each venue.
            total_fees = (_taker_fee(long_ex, fees) + _taker_fee(short_ex, fees)) * 2
            net_after_fees = funding_spread - total_fees
            annualized = annualized_funding_return(net_after_fees, periods_per_day)

            opportunities.append(
                CrossExchangeFundingOpportunity(
                    symbol=fr_a.symbol,
                    long_exchange=long_ex,
                    short_exchange=short_ex,
                    funding_spread=funding_spread,
                    total_fees=total_fees,
                    net_after_fees=net_after_fees,
                    annualized_return=annualized,
                    profitable=annualized > min_annualized_return,
                )
            )

    opportunities.sort(key=lambda o: o.annualized_return, reverse=True)
    return opportunities


class FundingArbDetector:
    """Stateful funding-arbitrage detector.

    Keeps the latest funding snapshot per exchange (and optional spot BBO for the
    cash-and-carry leg) and re-scores both opportunity types on demand. Pure
    in-memory — mirrors the hot-path discipline of the rest of core/.
    """

    def __init__(
        self,
        fees: dict[Exchange, float] | None = None,
        *,
        periods_per_day: int = PERIODS_PER_DAY,
        min_annualized_return: float = DEFAULT_MIN_ANNUALIZED_RETURN,
    ) -> None:
        self._fees = fees
        self._periods_per_day = periods_per_day
        self._min_annualized_return = min_annualized_return
        self._funding: dict[Exchange, FundingRate] = {}
        self._spot: dict[Exchange, BBO] = {}

    def update_funding(self, funding: FundingRate) -> None:
        self._funding[funding.exchange] = funding

    def update_spot(self, bbo: BBO) -> None:
        self._spot[bbo.exchange] = bbo

    @property
    def funding_rates(self) -> dict[Exchange, FundingRate]:
        return dict(self._funding)

    def detect_cash_and_carry(self) -> list[CashCarryOpportunity]:
        return detect_cash_and_carry(
            self._spot,
            self._funding,
            self._fees,
            periods_per_day=self._periods_per_day,
            min_annualized_return=self._min_annualized_return,
        )

    def detect_cross_exchange_funding(
        self,
    ) -> list[CrossExchangeFundingOpportunity]:
        return detect_cross_exchange_funding(
            self._funding,
            self._fees,
            periods_per_day=self._periods_per_day,
            min_annualized_return=self._min_annualized_return,
        )

    def detect(self) -> dict[str, list]:
        """All opportunities of both kinds from the current state."""
        return {
            "cash_and_carry": self.detect_cash_and_carry(),
            "cross_exchange_funding": self.detect_cross_exchange_funding(),
        }


# ── JSON serialization (REST / WS) ────────────────────────────────────────────────


def funding_rate_to_dict(funding: FundingRate) -> dict:
    """JSON-serializable form of a funding snapshot, with the rate annualized."""
    return {
        "exchange": funding.exchange.value,
        "symbol": funding.symbol,
        "rate": funding.rate,
        "annualized_rate": annualized_funding_return(funding.rate),
        "mark_price": funding.mark_price,
        "index_price": funding.index_price,
        "next_funding_time": funding.next_funding_time.isoformat(),
        "timestamp": funding.timestamp.isoformat(),
    }


def cash_carry_to_dict(opp: CashCarryOpportunity) -> dict:
    return {
        "exchange": opp.exchange.value,
        "symbol": opp.symbol,
        "direction": opp.direction,
        "funding_rate": opp.funding_rate,
        "funding_capture": opp.funding_capture,
        "total_fees": opp.total_fees,
        "net_after_fees": opp.net_after_fees,
        "annualized_return": opp.annualized_return,
        "profitable": opp.profitable,
    }


def cross_exchange_to_dict(opp: CrossExchangeFundingOpportunity) -> dict:
    return {
        "symbol": opp.symbol,
        "long_exchange": opp.long_exchange.value,
        "short_exchange": opp.short_exchange.value,
        "funding_spread": opp.funding_spread,
        "total_fees": opp.total_fees,
        "net_after_fees": opp.net_after_fees,
        "annualized_return": opp.annualized_return,
        "profitable": opp.profitable,
    }


# ── module-level singleton (fed by the funding poller, read by the REST route) ────

_instance: FundingArbDetector | None = None


def get_funding_detector() -> FundingArbDetector:
    global _instance
    if _instance is None:
        _instance = FundingArbDetector()
    return _instance
