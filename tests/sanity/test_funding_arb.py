from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.funding_arb import (
    FundingArbDetector,
    FundingRate,
    annualized_funding_return,
    detect_cash_and_carry,
    detect_cross_exchange_funding,
)
from models.market import BBO, Exchange

_NOW = datetime(2026, 5, 30, 6, 0, 0, tzinfo=timezone.utc)
_NEXT = _NOW + timedelta(hours=8)

# Real Binance/OKX taker fees are both 0.001 (see core/fees.py). A frictionless
# overlay is handy when we want the carry numbers to match a clean hand-calc.
_NO_FEES = {ex: 0.0 for ex in Exchange}


def _funding(
    exchange: Exchange, rate: float, symbol: str = "BTCUSDT", mark: float = 100_000.0
) -> FundingRate:
    return FundingRate(
        exchange=exchange,
        symbol=symbol,
        rate=rate,
        next_funding_time=_NEXT,
        mark_price=mark,
        index_price=mark,
        timestamp=_NOW,
    )


def _spot(exchange: Exchange, bid: float = 99_990.0, ask: float = 100_000.0) -> BBO:
    return BBO(
        exchange=exchange,
        bid=bid,
        ask=ask,
        bid_qty=1.0,
        ask_qty=1.0,
        ws_received_at=_NOW,
    )


# ── annualization: the canonical 0.05%/8h → 54.75% APR ────────────────────────────


def test_annualized_funding_return_known_value():
    # 0.0005 per 8h, 3 periods/day, 365 days → 0.5475.
    assert annualized_funding_return(0.0005) == pytest.approx(0.5475)


def test_annualized_funding_return_scales_with_rate():
    assert annualized_funding_return(0.0051) == pytest.approx(0.0051 * 3 * 365)
    assert annualized_funding_return(0.0, periods_per_day=3) == 0.0


def test_annualized_funding_return_rejects_bad_period():
    with pytest.raises(ValueError, match="periods_per_day"):
        annualized_funding_return(0.0005, periods_per_day=0)


# ── cash-and-carry ────────────────────────────────────────────────────────────────


def test_cash_and_carry_profitable_when_funding_exceeds_fees():
    # Funding 0.6%/8h on Binance, real taker fees 0.001 each leg → 0.002 total.
    # net = 0.006 - 0.002 = 0.004 per period → annualized 0.004*3*365 = 4.38.
    spot = {Exchange.BINANCE: _spot(Exchange.BINANCE)}
    funding = {Exchange.BINANCE: _funding(Exchange.BINANCE, 0.006)}

    opps = detect_cash_and_carry(spot, funding)

    assert len(opps) == 1
    opp = opps[0]
    assert opp.profitable is True
    assert opp.direction == "long_spot_short_perp"
    assert opp.total_fees == pytest.approx(0.002)
    assert opp.funding_capture == pytest.approx(0.006)
    assert opp.net_after_fees == pytest.approx(0.004)
    assert opp.annualized_return == pytest.approx(4.38)


def test_cash_and_carry_fees_eat_edge_when_funding_low():
    # Funding only 0.05%/8h, but two taker legs cost 0.2% → carry is negative.
    spot = {Exchange.BINANCE: _spot(Exchange.BINANCE)}
    funding = {Exchange.BINANCE: _funding(Exchange.BINANCE, 0.0005)}

    opps = detect_cash_and_carry(spot, funding)

    assert len(opps) == 1
    assert opps[0].profitable is False
    assert opps[0].net_after_fees == pytest.approx(0.0005 - 0.002)
    assert opps[0].annualized_return < 0


def test_cash_and_carry_zero_fee_matches_pure_funding():
    spot = {Exchange.BINANCE: _spot(Exchange.BINANCE)}
    funding = {Exchange.BINANCE: _funding(Exchange.BINANCE, 0.0005)}

    opps = detect_cash_and_carry(spot, funding, _NO_FEES)

    assert opps[0].net_after_fees == pytest.approx(0.0005)
    assert opps[0].annualized_return == pytest.approx(0.5475)
    assert opps[0].profitable is True


def test_negative_funding_inverts_cash_and_carry_direction():
    # Shorts pay longs → flip to long perp / short spot, still capturing |funding|.
    spot = {Exchange.BINANCE: _spot(Exchange.BINANCE)}
    funding = {Exchange.BINANCE: _funding(Exchange.BINANCE, -0.006)}

    opps = detect_cash_and_carry(spot, funding, _NO_FEES)

    opp = opps[0]
    assert opp.direction == "short_spot_long_perp"
    assert opp.funding_rate == pytest.approx(-0.006)
    assert opp.funding_capture == pytest.approx(0.006)  # captured magnitude is positive
    assert opp.net_after_fees == pytest.approx(0.006)
    assert opp.profitable is True


def test_cash_and_carry_requires_spot_leg():
    # Perp funding present but no spot to hedge it → not an opportunity.
    funding = {Exchange.OKX: _funding(Exchange.OKX, 0.006)}
    opps = detect_cash_and_carry({}, funding, _NO_FEES)
    assert opps == []


def test_cash_and_carry_sorted_by_annualized_return():
    spot = {
        Exchange.BINANCE: _spot(Exchange.BINANCE),
        Exchange.OKX: _spot(Exchange.OKX),
    }
    funding = {
        Exchange.BINANCE: _funding(Exchange.BINANCE, 0.004),
        Exchange.OKX: _funding(Exchange.OKX, 0.008),
    }
    opps = detect_cash_and_carry(spot, funding, _NO_FEES)

    assert [o.exchange for o in opps] == [Exchange.OKX, Exchange.BINANCE]


# ── cross-exchange funding ────────────────────────────────────────────────────────


def test_cross_exchange_known_spread_net_positive():
    # Binance 0.06%/8h vs OKX 0.01%/8h → spread 0.05%/8h. With no fees the spread
    # annualizes exactly like the canonical single rate: 0.0005*3*365 = 0.5475.
    funding = {
        Exchange.BINANCE: _funding(Exchange.BINANCE, 0.0006),
        Exchange.OKX: _funding(Exchange.OKX, 0.0001),
    }
    opps = detect_cross_exchange_funding(funding, _NO_FEES)

    assert len(opps) == 1
    opp = opps[0]
    assert opp.profitable is True
    assert opp.short_exchange == Exchange.BINANCE  # higher funding → short to receive
    assert opp.long_exchange == Exchange.OKX       # lower funding → long, pay less
    assert opp.funding_spread == pytest.approx(0.0005)
    assert opp.annualized_return == pytest.approx(0.5475)


def test_cross_exchange_picks_higher_funding_as_short_either_order():
    # Order of insertion must not change which venue is the short leg.
    funding = {
        Exchange.OKX: _funding(Exchange.OKX, 0.0001),
        Exchange.BINANCE: _funding(Exchange.BINANCE, 0.0006),
    }
    opp = detect_cross_exchange_funding(funding, _NO_FEES)[0]
    assert opp.short_exchange == Exchange.BINANCE
    assert opp.long_exchange == Exchange.OKX


def test_cross_exchange_fees_eat_small_spread():
    # Spread 0.05%/8h, but a full round-trip on both legs costs (0.001+0.001)*2
    # = 0.004 → net negative.
    funding = {
        Exchange.BINANCE: _funding(Exchange.BINANCE, 0.0006),
        Exchange.OKX: _funding(Exchange.OKX, 0.0001),
    }
    opps = detect_cross_exchange_funding(funding)  # real fees

    assert opps[0].total_fees == pytest.approx(0.004)
    assert opps[0].net_after_fees == pytest.approx(0.0005 - 0.004)
    assert opps[0].profitable is False


def test_cross_exchange_large_spread_clears_real_fees():
    # Spread 0.6%/8h easily clears the 0.004 round-trip → net 0.002, annualized 2.19.
    funding = {
        Exchange.BINANCE: _funding(Exchange.BINANCE, 0.0061),
        Exchange.OKX: _funding(Exchange.OKX, 0.0001),
    }
    opp = detect_cross_exchange_funding(funding)[0]

    assert opp.funding_spread == pytest.approx(0.006)
    assert opp.net_after_fees == pytest.approx(0.002)
    assert opp.annualized_return == pytest.approx(2.19)
    assert opp.profitable is True


def test_cross_exchange_single_venue_has_no_pairs():
    funding = {Exchange.BINANCE: _funding(Exchange.BINANCE, 0.006)}
    assert detect_cross_exchange_funding(funding) == []


# ── FundingRate validation ────────────────────────────────────────────────────────


def test_funding_rate_rejects_nonpositive_prices():
    with pytest.raises(ValueError, match="mark_price"):
        _funding(Exchange.BINANCE, 0.0005, mark=0.0)

    with pytest.raises(ValueError, match="index_price"):
        FundingRate(
            exchange=Exchange.BINANCE,
            symbol="BTCUSDT",
            rate=0.0005,
            next_funding_time=_NEXT,
            mark_price=100_000.0,
            index_price=-1.0,
            timestamp=_NOW,
        )


# ── stateful detector ─────────────────────────────────────────────────────────────


def test_detector_tracks_state_and_detects_both():
    det = FundingArbDetector(fees=_NO_FEES)
    det.update_spot(_spot(Exchange.BINANCE))
    det.update_funding(_funding(Exchange.BINANCE, 0.006))
    det.update_funding(_funding(Exchange.OKX, 0.0001))

    result = det.detect()

    # Binance has both legs → one cash-and-carry; the pair → one cross-exchange.
    cc = result["cash_and_carry"]
    assert len(cc) == 1
    assert cc[0].exchange == Exchange.BINANCE
    assert cc[0].profitable is True

    cx = result["cross_exchange_funding"]
    assert len(cx) == 1
    assert cx[0].short_exchange == Exchange.BINANCE
    assert cx[0].long_exchange == Exchange.OKX


def test_detector_update_overwrites_latest_funding():
    det = FundingArbDetector(fees=_NO_FEES)
    det.update_spot(_spot(Exchange.BINANCE))
    det.update_funding(_funding(Exchange.BINANCE, 0.001))
    det.update_funding(_funding(Exchange.BINANCE, 0.009))  # fresher snapshot wins

    cc = det.detect_cash_and_carry()
    assert cc[0].funding_rate == pytest.approx(0.009)
    assert det.funding_rates[Exchange.BINANCE].rate == pytest.approx(0.009)


def test_detector_empty_state_yields_nothing():
    det = FundingArbDetector()
    result = det.detect()
    assert result["cash_and_carry"] == []
    assert result["cross_exchange_funding"] == []
