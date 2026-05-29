from __future__ import annotations

import pytest

from core.risk_buffer import K_DEFAULT_95, latency_risk_buffer, passes_latency_buffer


# ── latency_risk_buffer: known-answer cases (computed by hand) ───────────────────
# buffer = k · σ · sqrt(latency_ms / 1000) · qty

def test_latency_risk_buffer_known_answer():
    # 1.64 · 10 · sqrt(250/1000)=0.5 · 0.5 = 4.1
    result = latency_risk_buffer(sigma=10.0, latency_ms=250.0, qty=0.5, k=1.64)
    assert result == pytest.approx(4.1)


def test_latency_risk_buffer_unit_latency_known_answer():
    # 2.0 · 20 · sqrt(1000/1000)=1.0 · 1.0 = 40.0
    result = latency_risk_buffer(sigma=20.0, latency_ms=1000.0, qty=1.0, k=2.0)
    assert result == pytest.approx(40.0)


def test_latency_risk_buffer_zero_latency_is_zero():
    assert latency_risk_buffer(sigma=10.0, latency_ms=0.0, qty=0.5, k=1.64) == 0.0


def test_latency_risk_buffer_zero_sigma_is_zero():
    assert latency_risk_buffer(sigma=0.0, latency_ms=250.0, qty=0.5, k=1.64) == 0.0


def test_latency_risk_buffer_scales_with_sqrt_latency():
    # Quadrupling latency doubles the buffer (sqrt scaling).
    base = latency_risk_buffer(sigma=10.0, latency_ms=250.0, qty=1.0, k=1.0)
    quad = latency_risk_buffer(sigma=10.0, latency_ms=1000.0, qty=1.0, k=1.0)
    assert quad == pytest.approx(2.0 * base)


def test_latency_risk_buffer_raises_on_negative_sigma():
    with pytest.raises(ValueError, match="sigma must be >= 0"):
        latency_risk_buffer(sigma=-1.0, latency_ms=250.0, qty=0.5)


def test_latency_risk_buffer_raises_on_negative_latency():
    with pytest.raises(ValueError, match="latency_ms must be >= 0"):
        latency_risk_buffer(sigma=10.0, latency_ms=-1.0, qty=0.5)


def test_latency_risk_buffer_raises_on_zero_qty():
    with pytest.raises(ValueError, match="qty must be positive"):
        latency_risk_buffer(sigma=10.0, latency_ms=250.0, qty=0.0)


def test_latency_risk_buffer_raises_on_negative_k():
    with pytest.raises(ValueError, match="k must be >= 0"):
        latency_risk_buffer(sigma=10.0, latency_ms=250.0, qty=0.5, k=-1.0)


# ── passes_latency_buffer: gate decision (threshold = fees + slippage + buffer) ──
# With σ=10, latency=250ms, qty=0.5, k=1.64 → buffer=4.1.
# threshold = fees(10) + slippage(2) + 4.1 = 16.1

def test_passes_latency_buffer_true_when_gross_clears_threshold():
    assert passes_latency_buffer(
        gross_profit=20.0, fees=10.0, slippage=2.0,
        sigma=10.0, latency_ms=250.0, qty=0.5, k=1.64,
    ) is True


def test_passes_latency_buffer_false_when_gross_below_threshold():
    assert passes_latency_buffer(
        gross_profit=15.0, fees=10.0, slippage=2.0,
        sigma=10.0, latency_ms=250.0, qty=0.5, k=1.64,
    ) is False


def test_passes_latency_buffer_false_exactly_at_threshold():
    # gross == threshold (16.1) → strict inequality rejects.
    assert passes_latency_buffer(
        gross_profit=16.1, fees=10.0, slippage=2.0,
        sigma=10.0, latency_ms=250.0, qty=0.5, k=1.64,
    ) is False


def test_passes_latency_buffer_reduces_to_net_check_when_sigma_zero():
    # σ=0 → buffer 0 → gate is gross > fees + slippage.
    assert passes_latency_buffer(
        gross_profit=13.0, fees=10.0, slippage=2.0,
        sigma=0.0, latency_ms=250.0, qty=0.5, k=1.64,
    ) is True


def test_passes_latency_buffer_high_latency_can_flip_to_reject():
    # Same opportunity that passes at low latency fails once latency grows the
    # buffer past the remaining edge. gross=20, fees=10, slip=2 → edge over costs=8.
    # buffer at 250ms = 4.1 (< 8, passes); at 4000ms: 1.64·10·2·0.5 = 16.4 (> 8, fails).
    low = passes_latency_buffer(20.0, 10.0, 2.0, 10.0, 250.0, 0.5, k=1.64)
    high = passes_latency_buffer(20.0, 10.0, 2.0, 10.0, 4000.0, 0.5, k=1.64)
    assert low is True
    assert high is False


def test_k_default_is_95_percent_one_sided_quantile():
    # 1.6449 ≈ Φ⁻¹(0.95); the documented protection level.
    assert K_DEFAULT_95 == pytest.approx(1.6449, abs=1e-3)
