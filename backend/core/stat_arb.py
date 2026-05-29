from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from itertools import combinations

import numpy as np
from scipy import stats

from models.market import BBO, Exchange

# Defaults tuned for cross-exchange BTC spreads sampled on every BBO tick.
DEFAULT_WINDOW_SIZE = 200
DEFAULT_ENTRY_THRESHOLD = 2.0   # |z| above this = spread anomalously wide
DEFAULT_MIN_SAMPLES = 30        # below this the stats are too noisy to trade
_LN2 = np.log(2.0)


class SignalDirection(str, Enum):
    # Spread = mid_a - mid_b. CONVERGE_SHORT_A: spread too HIGH (a rich vs b),
    # expect mean reversion → short a / long b. CONVERGE_LONG_A: the mirror case.
    CONVERGE_SHORT_A = "CONVERGE_SHORT_A"
    CONVERGE_LONG_A = "CONVERGE_LONG_A"


@dataclass(frozen=True)
class SpreadStats:
    """Snapshot of the rolling spread distribution for one exchange pair."""

    mean: float
    std: float
    zscore: float
    half_life: float  # in ticks; np.inf when no mean reversion is detectable
    n_samples: int


@dataclass(frozen=True)
class StatArbSignal:
    exchange_a: Exchange
    exchange_b: Exchange
    spread: float
    mean: float
    std: float
    zscore: float
    half_life: float
    direction: SignalDirection
    detected_at: datetime


# ── pure numerical core (sanity-tested) ─────────────────────────────────────────

def compute_zscore(value: float, mean: float, std: float) -> float:
    """Standard score of `value`. Returns NaN when std == 0 (degenerate window)."""
    if std == 0:
        return np.nan
    return (value - mean) / std


def rolling_mean_std(series: np.ndarray) -> tuple[float, float]:
    """Sample mean and sample std (ddof=1) of the spread window.

    ddof=1 is the pairs-trading convention: the window is a sample of the
    spread process, not the whole population.
    """
    if series.size == 0:
        raise ValueError("cannot compute stats on empty series")
    if series.size == 1:
        return float(series[0]), 0.0
    return float(np.mean(series)), float(np.std(series, ddof=1))


def estimate_half_life(series: np.ndarray) -> float:
    """Mean-reversion half-life (in ticks) from the discretized OU model.

    Regress ΔX_t on X_{t-1}:  ΔX_t = a + b·X_{t-1} + ε.
    For an OU process b < 0, and half_life = -ln(2) / b.
    Returns np.inf when b >= 0 (no reversion) or the regression is degenerate.
    """
    if series.size < 3:
        return np.inf

    lagged = series[:-1]
    delta = np.diff(series)

    # A flat lag series carries no reversion information.
    if np.std(lagged) == 0:
        return np.inf

    result = stats.linregress(lagged, delta)
    b = result.slope
    if b >= 0:
        return np.inf
    return float(-_LN2 / b)


def estimate_ou_parameters(series: np.ndarray) -> SpreadStats:
    """Full OU-style summary of a spread window: mean, std, current z-score,
    half-life. The z-score is computed for the most recent observation."""
    if series.size == 0:
        raise ValueError("cannot estimate OU parameters on empty series")

    mean, std = rolling_mean_std(series)
    zscore = compute_zscore(float(series[-1]), mean, std)
    half_life = estimate_half_life(series)
    return SpreadStats(
        mean=mean,
        std=std,
        zscore=zscore,
        half_life=half_life,
        n_samples=int(series.size),
    )


# ── stateful detector ───────────────────────────────────────────────────────────

def _mid(bbo: BBO) -> float:
    return (bbo.bid + bbo.ask) / 2.0


def _canonical_pair(a: Exchange, b: Exchange) -> tuple[Exchange, Exchange]:
    """Order a pair deterministically by enum value so spread sign is stable."""
    return (a, b) if a.value < b.value else (b, a)


class StatArbDetector:
    """Tracks the rolling mid-price spread between every exchange pair and emits
    a statistical-arbitrage signal when the spread diverges beyond the entry
    threshold (an OU mean-reversion bet layered on top of spatial arbitrage).
    """

    def __init__(
        self,
        window_size: int = DEFAULT_WINDOW_SIZE,
        entry_threshold: float = DEFAULT_ENTRY_THRESHOLD,
        min_samples: int = DEFAULT_MIN_SAMPLES,
    ) -> None:
        if window_size < 2:
            raise ValueError(f"window_size must be >= 2, got {window_size}")
        if entry_threshold <= 0:
            raise ValueError(f"entry_threshold must be positive, got {entry_threshold}")
        if min_samples < 2:
            raise ValueError(f"min_samples must be >= 2, got {min_samples}")

        self.window_size = window_size
        self.entry_threshold = entry_threshold
        self.min_samples = min_samples
        self._windows: dict[tuple[Exchange, Exchange], deque[float]] = {}

    def update(
        self,
        bbos: dict[Exchange, BBO],
        now: datetime | None = None,
    ) -> list[StatArbSignal]:
        """Push the latest spreads and return any pairs that crossed the threshold."""
        _now = now if now is not None else datetime.now(timezone.utc)
        signals: list[StatArbSignal] = []

        for ex_a, ex_b in combinations(sorted(bbos, key=lambda e: e.value), 2):
            spread = _mid(bbos[ex_a]) - _mid(bbos[ex_b])
            window = self._windows.setdefault((ex_a, ex_b), deque(maxlen=self.window_size))
            window.append(spread)

            if len(window) < self.min_samples:
                continue

            stats_ = estimate_ou_parameters(np.array(window, dtype=float))
            signal = self._evaluate(ex_a, ex_b, spread, stats_, _now)
            if signal is not None:
                signals.append(signal)

        return signals

    def get_stats(self, ex_a: Exchange, ex_b: Exchange) -> SpreadStats | None:
        """Current spread stats for a pair, or None if not enough samples yet."""
        key = _canonical_pair(ex_a, ex_b)
        window = self._windows.get(key)
        if window is None or len(window) < self.min_samples:
            return None
        return estimate_ou_parameters(np.array(window, dtype=float))

    def current_zscores(self) -> list[dict]:
        """JSON-serializable z-score snapshot for every pair with enough samples.

        Used by REST (/api/status) and the WS z_score broadcast. half_life=inf is
        rendered as None so it survives JSON encoding.
        """
        out: list[dict] = []
        for (ex_a, ex_b), window in self._windows.items():
            if len(window) < self.min_samples:
                continue
            stats_ = estimate_ou_parameters(np.array(window, dtype=float))
            if np.isnan(stats_.zscore):
                continue
            out.append({
                "pair": f"{ex_a.value}/{ex_b.value}",
                "z_score": stats_.zscore,
                "spread": float(window[-1]),
                "mean": stats_.mean,
                "std": stats_.std,
                "half_life": stats_.half_life if np.isfinite(stats_.half_life) else None,
                "n_samples": stats_.n_samples,
            })
        return out

    def headline(self) -> dict | None:
        """The pair with the largest |z-score| right now, or None when no pair
        has enough samples. This is the spread most worth watching."""
        snapshot = self.current_zscores()
        if not snapshot:
            return None
        return max(snapshot, key=lambda d: abs(d["z_score"]))

    def _evaluate(
        self,
        ex_a: Exchange,
        ex_b: Exchange,
        spread: float,
        stats_: SpreadStats,
        now: datetime,
    ) -> StatArbSignal | None:
        if np.isnan(stats_.zscore) or abs(stats_.zscore) <= self.entry_threshold:
            return None

        direction = (
            SignalDirection.CONVERGE_SHORT_A
            if stats_.zscore > 0
            else SignalDirection.CONVERGE_LONG_A
        )
        return StatArbSignal(
            exchange_a=ex_a,
            exchange_b=ex_b,
            spread=spread,
            mean=stats_.mean,
            std=stats_.std,
            zscore=stats_.zscore,
            half_life=stats_.half_life,
            direction=direction,
            detected_at=now,
        )


def signal_to_dict(signal: StatArbSignal) -> dict:
    """JSON-serializable form of a signal (half_life=inf → None, enums → values)."""
    return {
        "pair": f"{signal.exchange_a.value}/{signal.exchange_b.value}",
        "exchange_a": signal.exchange_a.value,
        "exchange_b": signal.exchange_b.value,
        "spread": signal.spread,
        "mean": signal.mean,
        "std": signal.std,
        "z_score": signal.zscore,
        "half_life": signal.half_life if np.isfinite(signal.half_life) else None,
        "direction": signal.direction.value,
        "detected_at": signal.detected_at.isoformat(),
    }


# ── module-level singleton ────────────────────────────────────────────────────

_instance: StatArbDetector | None = None


def get_stat_arb_detector() -> StatArbDetector:
    global _instance
    if _instance is None:
        _instance = StatArbDetector()
    return _instance
