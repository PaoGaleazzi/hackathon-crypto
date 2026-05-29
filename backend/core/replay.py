from __future__ import annotations

import json
import statistics
from collections import deque
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import settings
from core.executor import build_rejected_trade, simulate_execution
from core.fees import OrderSide, calculate_fee, estimate_slippage
from core.fill_probability import DEFAULT_TAU_MS
from core.risk_buffer import K_DEFAULT_95, passes_latency_buffer
from core.scanner import scan_for_opportunities
from core.scorer import rank_opportunities
from core.sizer import InsufficientBalanceError, OptimalSizer
from models.market import BBO, Exchange
from models.trade import Trade, WalletBalance

__all__ = [
    "TickRecorder",
    "record_ticks",
    "load_ticks",
    "replay_ticks",
    "RunConfig",
    "run_replay",
]

# ── recording ───────────────────────────────────────────────────────────────
#
# A "tick" is a single normalized BBO update — exactly what the live pipeline
# wakes on. We persist one BBO per JSONL line, in arrival order, so the recorded
# stream re-creates the in-memory state transitions deterministically on replay.
# DuckDB is the live store; JSONL is the *replay* store — self-contained, diffable
# and trivially shippable as a fixture.


class TickRecorder:
    """Append BBO ticks to a JSONL file, one BBO per line, in arrival order.

    Usage::

        with TickRecorder("ticks.jsonl") as rec:
            rec.record(bbo)

    The file is opened in append mode so a recording can be resumed across runs.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")
        self.count = 0

    def record(self, bbo: BBO) -> None:
        # mode="json" renders the Exchange enum to its string value and the
        # datetimes to ISO-8601 — a lossless round-trip back through model_validate.
        self._fh.write(json.dumps(bbo.model_dump(mode="json"), separators=(",", ":")))
        self._fh.write("\n")
        self.count += 1

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.flush()
            self._fh.close()

    def __enter__(self) -> TickRecorder:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def record_ticks(bbos: Iterable[BBO], path: str | Path) -> int:
    """Write an iterable of BBOs to a JSONL file, returning the number written."""
    with TickRecorder(path) as rec:
        for bbo in bbos:
            rec.record(bbo)
        return rec.count


def replay_ticks(path: str | Path) -> Iterator[BBO]:
    """Stream BBOs back from a JSONL file in recorded order.

    Reconstruction is exact: floats round-trip through ``repr`` in JSON and the
    Exchange/datetime fields rebuild via Pydantic validation, so replaying the
    same file twice yields identical BBO objects."""
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            yield BBO.model_validate(json.loads(line))


def load_ticks(path: str | Path) -> list[BBO]:
    """Eagerly load all ticks from a JSONL file into a list."""
    return list(replay_ticks(path))


# ── backtest engine ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RunConfig:
    """A single arbitrage-bot configuration to evaluate over a recorded dataset.

    Every field is a tunable knob; an A/B test varies one or more and replays the
    same ticks under each. Knobs that map to global ``settings`` (``stale_quote_ms``,
    ``min_fill_ratio``) are applied via a scoped override during the run and
    restored afterward, so the real executor exercises them unchanged.
    """

    name: str
    # Engine-level gates ----------------------------------------------------
    # Only the single best-ranked opportunity per tick is executed (greedy
    # backtest), and only if its net spread clears this floor — the primary
    # precision/false-positive knob.
    min_net_spread_usd: float = 0.0
    min_trade_size_btc: float = field(default_factory=lambda: settings.min_trade_size_btc)
    tau_ms: float = DEFAULT_TAU_MS
    # When False, the micro-price signal is neutralized before ranking (every
    # opportunity treated as confirmed), so the scorer's micro-price penalty is
    # not applied — lets an A/B isolate the value of that signal.
    enable_microprice: bool = True
    # Almgren-Chriss latency-risk gate. assumed_latency_ms models the production
    # ws→decision delay the buffer protects against (replay compute time is
    # microseconds and not representative). Set apply_latency_buffer=False to disable.
    apply_latency_buffer: bool = True
    latency_buffer_k: float = K_DEFAULT_95
    assumed_latency_ms: float = 50.0
    vol_window: int = 50
    # settings overrides (None = leave the global default in place) ----------
    stale_quote_ms: int | None = None
    min_fill_ratio: float | None = None
    # initial wallet state, per exchange
    initial_usdt: float = 10_000.0
    initial_btc: float = 0.5


class _SpreadVolTracker:
    """Rolling per-pair volatility of the cross-exchange mid spread (USD/BTC).

    Feeds σ to the Almgren-Chriss latency buffer. Keyed by unordered pair: the
    std of (mid_a − mid_b) is direction-independent, so buy@A/sell@B and the
    reverse share one estimate."""

    def __init__(self, window: int) -> None:
        self.window = window
        self._hist: dict[frozenset[Exchange], deque[float]] = {}

    def update(self, state: dict[Exchange, BBO]) -> None:
        exchanges = list(state)
        for i in range(len(exchanges)):
            for j in range(i + 1, len(exchanges)):
                a, b = exchanges[i], exchanges[j]
                mid_a = (state[a].bid + state[a].ask) / 2.0
                mid_b = (state[b].bid + state[b].ask) / 2.0
                key = frozenset((a, b))
                dq = self._hist.get(key)
                if dq is None:
                    dq = deque(maxlen=self.window)
                    self._hist[key] = dq
                dq.append(mid_a - mid_b)

    def sigma(self, a: Exchange, b: Exchange) -> float:
        dq = self._hist.get(frozenset((a, b)))
        if dq is None or len(dq) < 2:
            return 0.0
        return statistics.pstdev(dq)


@contextmanager
def _settings_override(config: RunConfig):
    """Temporarily apply a config's settings-backed knobs, restoring on exit."""
    overrides = {
        "stale_quote_ms": config.stale_quote_ms,
        "min_fill_ratio": config.min_fill_ratio,
    }
    saved = {k: getattr(settings, k) for k in overrides}
    try:
        for k, v in overrides.items():
            if v is not None:
                setattr(settings, k, v)
        yield
    finally:
        for k, v in saved.items():
            setattr(settings, k, v)


def _survives_latency_buffer(opp, qty: float, sigma: float, config: RunConfig) -> bool:
    """Almgren-Chriss gate, mirroring api.main._survives_latency_buffer but with a
    modeled production latency (replay has no real ws→decision delay)."""
    gross = (opp.sell_bid - opp.buy_ask) * qty
    fees = (
        calculate_fee(opp.buy_exchange, qty, opp.buy_ask, OrderSide.TAKER)
        + calculate_fee(opp.sell_exchange, qty, opp.sell_bid, OrderSide.TAKER)
    )
    depth = opp.available_qty
    slippage = (
        estimate_slippage(qty, opp.buy_ask, depth)
        + estimate_slippage(qty, opp.sell_bid, depth)
        if depth > 0
        else 0.0
    )
    return passes_latency_buffer(
        gross, fees, slippage, sigma, config.assumed_latency_ms, qty,
        k=config.latency_buffer_k,
    )


def run_replay(ticks: Iterable[BBO], config: RunConfig) -> list[Trade]:
    """Replay a recorded tick stream under one config and return every Trade the
    bot would have made — executed *and* rejected.

    Per tick the engine rebuilds in-memory BBO state, scans all pairs, ranks by
    latency-adjusted expected profit, and acts on the single best opportunity:
    it sizes via the QP sizer, applies the min-spread and latency-risk gates, then
    routes through the real ``simulate_execution`` (with ``persist=False`` — a
    backtest never touches the live trades table). Rejected attempts are returned
    too so downstream metrics can count the false positives each config filters.

    Determinism: the engine runs off the tick clock (each BBO's ``ws_received_at``),
    not wall time, so detection, staleness and P&L reproduce exactly across runs.
    Each trade's ``latency_ms`` is overwritten with the recorded parse latency
    (``normalized_at − ws_received_at``) — a real, recorded per-tick signal — while
    the Almgren-Chriss buffer uses the modeled production delay
    (``config.assumed_latency_ms``), since parse time understates ws→execution risk.
    """
    wallets: dict[Exchange, WalletBalance] = {
        ex: WalletBalance(
            exchange=ex,
            usdt=config.initial_usdt,
            btc=config.initial_btc,
            updated_at=datetime.now(timezone.utc),
        )
        for ex in Exchange
    }
    state: dict[Exchange, BBO] = {}
    vol = _SpreadVolTracker(config.vol_window)
    sizer = OptimalSizer(min_trade_size=config.min_trade_size_btc)
    trades: list[Trade] = []

    with _settings_override(config):
        for bbo in ticks:
            state[bbo.exchange] = bbo
            vol.update(state)
            if len(state) < 2:
                continue

            # Tick clock: the decision happens the instant this BBO arrives, so
            # staleness of the *other* legs is measured against a real timestamp
            # and detection is deterministic.
            now = bbo.ws_received_at
            recorded_latency_ms = (
                (bbo.normalized_at - bbo.ws_received_at).total_seconds() * 1000.0
                if bbo.normalized_at is not None
                else 0.0
            )

            opportunities = scan_for_opportunities(state, now=now)
            if not opportunities:
                continue

            # Ablate the micro-price signal by marking every opp confirmed, so the
            # scorer applies no micro-price penalty during ranking.
            if not config.enable_microprice:
                opportunities = [
                    o.model_copy(update={"microprice_confirms": True})
                    for o in opportunities
                ]

            ranked = rank_opportunities(opportunities, now=now, tau_ms=config.tau_ms)
            opp = ranked[0]

            # Primary precision gate: ignore thin edges below the floor.
            if opp.net_spread < config.min_net_spread_usd:
                continue

            balance = wallets[opp.buy_exchange].usdt
            try:
                qty = sizer.compute_optimal_qty(opp, balance)
            except InsufficientBalanceError:
                continue
            if qty < config.min_trade_size_btc:
                continue

            if config.apply_latency_buffer:
                sigma = vol.sigma(opp.buy_exchange, opp.sell_exchange)
                if not _survives_latency_buffer(opp, qty, sigma, config):
                    trades.append(
                        build_rejected_trade(
                            opp, qty, now, "REJECTED_LATENCY_RISK",
                            latency_ms=recorded_latency_ms,
                        )
                    )
                    continue

            trade = simulate_execution(opp, qty, wallets, state, now=now, persist=False)
            trades.append(trade.model_copy(update={"latency_ms": recorded_latency_ms}))

    return trades
