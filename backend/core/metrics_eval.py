from __future__ import annotations

from dataclasses import asdict, dataclass

from models.trade import Trade

__all__ = ["RunMetrics", "evaluate_run", "percentile"]

# Statuses that mean "the bot looked at a candidate and declined it". These are
# the false positives the system filtered out before they cost money — the value
# the gates (stale-quote, min-fill, latency-risk, balance, breaker) add.
_FILTERED_STATUSES = frozenset(
    {
        "ABORTED_STALE",
        "SKIPPED_MIN_FILL",
        "REJECTED_INSUFFICIENT_BALANCE",
        "REJECTED_NEGATIVE_NET",
        "REJECTED_LATENCY_RISK",
        "CIRCUIT_BREAKER_OPEN",
    }
)


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolated percentile (q in [0, 100]), matching numpy's default.

    Pure-python and deterministic so the eval has no heavy dependency and gives
    identical numbers across runs. Returns 0.0 for an empty input."""
    if not values:
        return 0.0
    if not 0.0 <= q <= 100.0:
        raise ValueError(f"q must be in [0, 100], got {q}")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (q / 100.0) * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


@dataclass(frozen=True)
class RunMetrics:
    """Performance summary of a single backtest run (one config over one dataset).

    Classification convention, over the Trades a run emitted:
      - true positive  : EXECUTED and net_profit > 0   (a real, profitable trade)
      - false positive : EXECUTED and net_profit <= 0  (a bad trade that slipped
                          past the gates — what precision punishes)
      - filtered FP    : a candidate a gate rejected before execution
    precision = TP / executed: of the trades we actually took, the share that paid.
    """

    label: str
    n_trades: int                 # total decisions (executed + filtered)
    trades_executed: int
    true_positives: int
    false_positives: int          # executed but unprofitable
    false_positives_filtered: int
    precision: float
    pnl_simulated: float          # sum of net_profit over EXECUTED trades (USD)
    latency_p50_ms: float
    latency_p95_ms: float

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_run(trades: list[Trade], label: str = "") -> RunMetrics:
    """Compute the A/B performance metrics for one run's trades.

    Latency percentiles are taken over *all* decisions (every trade — executed or
    rejected — carries a measured latency), so they describe how fast the config
    decides regardless of outcome."""
    executed = [t for t in trades if t.status == "EXECUTED"]
    filtered = [t for t in trades if t.status in _FILTERED_STATUSES]

    true_positives = sum(1 for t in executed if t.net_profit > 0)
    false_positives = len(executed) - true_positives
    precision = true_positives / len(executed) if executed else 0.0
    pnl = sum(t.net_profit for t in executed)

    latencies = [t.latency_ms for t in trades]

    return RunMetrics(
        label=label,
        n_trades=len(trades),
        trades_executed=len(executed),
        true_positives=true_positives,
        false_positives=false_positives,
        false_positives_filtered=len(filtered),
        precision=precision,
        pnl_simulated=pnl,
        latency_p50_ms=percentile(latencies, 50.0),
        latency_p95_ms=percentile(latencies, 95.0),
    )
