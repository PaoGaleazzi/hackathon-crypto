from __future__ import annotations

import math

# One-sided 95% normal quantile: P(Z < 1.6449) ≈ 0.95. The buffer guards against
# an adverse spread move at this confidence over the detection→execution delay.
K_DEFAULT_95 = 1.6448536269514722


def latency_risk_buffer(
    sigma: float,
    latency_ms: float,
    qty: float,
    k: float = K_DEFAULT_95,
) -> float:
    """Almgren-Chriss adverse-selection buffer, in USD.

        buffer = k · σ · sqrt(latency_ms / 1000) · qty

    σ is the short-term volatility of the cross-exchange spread (USD per BTC,
    e.g. the rolling std of mid_a − mid_b). The sqrt(t) factor is the random-walk
    diffusion of price over the latency window; multiplying by qty converts the
    per-BTC price risk into a notional USD figure. k sets the protection level
    (1.645 ≈ 95% one-sided).
    """
    if sigma < 0:
        raise ValueError(f"sigma must be >= 0, got {sigma}")
    if latency_ms < 0:
        raise ValueError(f"latency_ms must be >= 0, got {latency_ms}")
    if qty <= 0:
        raise ValueError(f"qty must be positive, got {qty}")
    if k < 0:
        raise ValueError(f"k must be >= 0, got {k}")
    return k * sigma * math.sqrt(latency_ms / 1000.0) * qty


def passes_latency_buffer(
    gross_profit: float,
    fees: float,
    slippage: float,
    sigma: float,
    latency_ms: float,
    qty: float,
    k: float = K_DEFAULT_95,
) -> bool:
    """Execution gate (Almgren-Chriss latency-risk framework).

    Execute only when the gross spread P&L clears every deterministic cost PLUS
    the latency risk buffer:

        gross_profit > fees + slippage + k·σ·√(latency_s)·qty

    Equivalent to requiring the net-of-cost edge to exceed the buffer. Strict
    inequality: an opportunity exactly at the threshold is rejected.
    """
    threshold = fees + slippage + latency_risk_buffer(sigma, latency_ms, qty, k)
    return gross_profit > threshold
