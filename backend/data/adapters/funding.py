from __future__ import annotations

import asyncio
import logging
import urllib.request
from datetime import datetime, timezone

import orjson

import data.bbo_state as bbo_state
from core.funding_arb import FundingRate, get_funding_detector
from models.market import Exchange

logger = logging.getLogger(__name__)

# ── funding-rate REST poller ──────────────────────────────────────────────────────
#
# Funding updates only every 8h and changes slowly, so a 10s REST poll is both
# sufficient and far more reliable than juggling three more WS streams (no
# subscribe handshakes, no reconnect bookkeeping). Each cycle fetches all three
# venues concurrently off the event loop (blocking urllib in a thread), feeds the
# shared FundingArbDetector, and re-syncs the spot legs from live BBO state so the
# cash-and-carry detector always scores against current spot.

_POLL_INTERVAL_S = 10.0
_HTTP_TIMEOUT_S = 8.0
_USER_AGENT = "arb-bot/1.0"

_BINANCE_URL = "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT"
_BYBIT_URL = "https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT"
_OKX_URL = "https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP"


def _fetch_json(url: str) -> dict:
    """Blocking GET + JSON parse. Always called via asyncio.to_thread."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:  # noqa: S310 (fixed https hosts)
        return orjson.loads(resp.read())


def _ms_to_dt(ms: int | str) -> datetime:
    """Epoch milliseconds (int or numeric string) → aware UTC datetime."""
    return datetime.fromtimestamp(int(ms) / 1000.0, tz=timezone.utc)


def _reference_price(exchange: Exchange) -> float:
    """Best available spot mid for a venue, used to fill mark/index when an
    endpoint omits them (OKX's funding-rate route). Falls back to the mean mid
    across all connected venues, then to a sane BTC constant if state is empty."""
    bbo = bbo_state.get(exchange)
    if bbo is not None:
        return (bbo.bid + bbo.ask) / 2.0
    all_bbo = bbo_state.get_all()
    if all_bbo:
        mids = [(b.bid + b.ask) / 2.0 for b in all_bbo.values()]
        return sum(mids) / len(mids)
    return 100_000.0


# ── per-exchange parsers ───────────────────────────────────────────────────────────


def parse_binance(payload: dict, now: datetime) -> FundingRate:
    return FundingRate(
        exchange=Exchange.BINANCE,
        symbol=payload["symbol"],
        rate=float(payload["lastFundingRate"]),
        next_funding_time=_ms_to_dt(payload["nextFundingTime"]),
        mark_price=float(payload["markPrice"]),
        index_price=float(payload.get("indexPrice") or payload["markPrice"]),
        timestamp=now,
    )


def parse_bybit(payload: dict, now: datetime) -> FundingRate:
    ticker = payload["result"]["list"][0]
    mark = float(ticker["markPrice"])
    return FundingRate(
        exchange=Exchange.BYBIT,
        symbol=ticker["symbol"],
        rate=float(ticker["fundingRate"]),
        next_funding_time=_ms_to_dt(ticker["nextFundingTime"]),
        mark_price=mark,
        index_price=float(ticker.get("indexPrice") or mark),
        timestamp=now,
    )


def parse_okx(payload: dict, now: datetime) -> FundingRate:
    # The funding-rate endpoint carries no price, so price the contract off live
    # OKX spot (BTC-USDT-SWAP tracks it closely) for the mark/index fields.
    entry = payload["data"][0]
    price = _reference_price(Exchange.OKX)
    return FundingRate(
        exchange=Exchange.OKX,
        symbol=entry["instId"],
        rate=float(entry["fundingRate"]),
        next_funding_time=_ms_to_dt(entry["fundingTime"]),
        mark_price=price,
        index_price=price,
        timestamp=now,
    )


_SOURCES: list[tuple[str, str, callable]] = [
    ("binance", _BINANCE_URL, parse_binance),
    ("bybit", _BYBIT_URL, parse_bybit),
    ("okx", _OKX_URL, parse_okx),
]


async def _poll_source(name: str, url: str, parser) -> FundingRate | None:
    """Fetch + parse one venue. Isolated failure: a down endpoint logs and yields
    None without taking the other venues down with it."""
    try:
        payload = await asyncio.to_thread(_fetch_json, url)
        now = datetime.now(timezone.utc)
        return parser(payload, now)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("Funding poll failed for %s: %s", name, exc)
        return None


async def poll_once() -> list[FundingRate]:
    """One polling cycle: fetch all venues, feed the detector, sync spot legs."""
    detector = get_funding_detector()

    results = await asyncio.gather(
        *(_poll_source(name, url, parser) for name, url, parser in _SOURCES)
    )
    rates = [r for r in results if r is not None]
    for rate in rates:
        detector.update_funding(rate)
        logger.info(
            "FUNDING %s | rate=%+.5f (%.1f%% APR) | mark=%.1f",
            rate.exchange.value, rate.rate,
            rate.rate * 3 * 365 * 100, rate.mark_price,
        )

    # Keep the cash-and-carry spot legs current from live BBO state.
    for bbo in bbo_state.get_all().values():
        detector.update_spot(bbo)

    return rates


async def run() -> None:
    """Poll funding rates every 10s, feeding the shared FundingArbDetector."""
    logger.info("Funding poller started (every %.0fs)", _POLL_INTERVAL_S)
    while True:
        try:
            await poll_once()
        except asyncio.CancelledError:
            logger.info("Funding poller stopped")
            raise
        except Exception as exc:
            logger.exception("Funding poller error: %s", exc)
        await asyncio.sleep(_POLL_INTERVAL_S)
