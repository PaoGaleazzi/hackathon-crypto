#!/usr/bin/env python3
"""
Lead-lag exploratory analysis between exchanges (cross-correlation with lag).

NOT production. Pure analysis on recorded market data. The question we answer:
when exchange A's mid-price moves, does exchange B move in the same direction a
few ms/seconds later (and vice-versa)? If so, who leads whom, by how long, and
how strong is the relationship?

Method (standard cross-correlation lead-lag):
  1. Per exchange, build mid-price = (bid+ask)/2 with timestamps.
  2. Resample each series onto a regular grid (default 100ms), forward-fill.
  3. Compute returns (log-returns) per series.
  4. For each ordered pair, compute Pearson correlation of A_returns[t] vs
     B_returns[t - lag] across a lag window (default -5s..+5s, 100ms steps).
  5. The lag maximizing |correlation| says who leads:
       lag > 0  -> A leads B by that many ms
       lag < 0  -> B leads A
  6. Report the correlation at the optimal lag.

IMPORTANT CAVEAT (reported honestly): timestamps are `ws_received_at`, i.e. when
*our* client received each update. So a measured lead is a mix of (a) genuine
price-discovery lead and (b) differential network/feed latency from each venue to
us. We flag this in the interpretation rather than overclaiming.

Usage:
    python scripts/leadlag_analysis.py
    python scripts/leadlag_analysis.py --resample-ms 100 --max-lag-s 5
"""
from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

DATA_PATH = Path("data/recordings/market_data.jsonl")


def load_mids(path: Path) -> pd.DataFrame:
    """Stream the jsonl and return a long DataFrame: [ts, exchange, mid]."""
    rows_ts: list[np.datetime64] = []
    rows_ex: list[str] = []
    rows_mid: list[float] = []
    bad = 0
    with path.open("r") as f:
        for line in f:
            if not line:
                continue
            try:
                r = json.loads(line)
                bid = r["bid"]
                ask = r["ask"]
                if bid is None or ask is None or bid <= 0 or ask <= 0:
                    bad += 1
                    continue
                rows_ts.append(np.datetime64(r["ws_received_at"].rstrip("Z")))
                rows_ex.append(r["exchange"])
                rows_mid.append((bid + ask) / 2.0)
            except (KeyError, ValueError, json.JSONDecodeError):
                bad += 1
                continue
    if bad:
        print(f"[load] skipped {bad} malformed/invalid rows", file=sys.stderr)
    df = pd.DataFrame({"ts": rows_ts, "exchange": rows_ex, "mid": rows_mid})
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def build_grid(df: pd.DataFrame, resample_ms: int):
    """
    Resample each exchange's mid onto a common regular grid.

    Returns (returns_df, coverage) where returns_df columns are exchanges and
    rows are log-returns per bin; coverage[ex] is the fraction of bins that had a
    real update (low coverage => ffill-dominated => unreliable).
    """
    rule = f"{resample_ms}ms"
    price_cols = {}
    coverage = {}
    grid_start = df["ts"].min().floor(rule)
    grid_end = df["ts"].max().ceil(rule)
    full_index = pd.date_range(grid_start, grid_end, freq=rule)

    for ex, g in df.groupby("exchange"):
        s = g.set_index("ts")["mid"].sort_index()
        # last observation within each bin
        binned = s.resample(rule).last()
        binned = binned.reindex(full_index)
        real = binned.notna().sum()
        coverage[ex] = real / len(full_index)
        price_cols[ex] = binned.ffill()

    prices = pd.DataFrame(price_cols, index=full_index)
    # log returns; first row NaN -> 0
    returns = np.log(prices).diff().fillna(0.0)
    return returns, coverage


def lagged_corr(a: np.ndarray, b: np.ndarray, max_lag: int):
    """
    Pearson correlation of a[t] vs b[t-lag] for lag in [-max_lag, max_lag].

    lag > 0 means b is shifted so that a is compared against b's *past* — i.e. a
    leads b. Returns (lags, corrs).
    """
    lags = np.arange(-max_lag, max_lag + 1)
    corrs = np.empty(lags.shape, dtype=float)
    n = len(a)
    for i, lag in enumerate(lags):
        if lag > 0:
            x = a[lag:]
            y = b[: n - lag]
        elif lag < 0:
            x = a[: n + lag]
            y = b[-lag:]
        else:
            x = a
            y = b
        if len(x) < 10 or np.std(x) == 0 or np.std(y) == 0:
            corrs[i] = np.nan
            continue
        corrs[i] = np.corrcoef(x, y)[0, 1]
    return lags, corrs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=DATA_PATH)
    ap.add_argument("--resample-ms", type=int, default=100,
                    help="grid bin size in ms (default 100)")
    ap.add_argument("--max-lag-s", type=float, default=5.0,
                    help="max lag to scan, seconds (default 5)")
    ap.add_argument("--min-coverage", type=float, default=0.05,
                    help="drop exchanges with real-update coverage below this")
    args = ap.parse_args()

    if not args.data.exists():
        print(f"ERROR: {args.data} not found", file=sys.stderr)
        return 1

    print(f"Loading {args.data} ...")
    df = load_mids(args.data)
    span = (df["ts"].max() - df["ts"].min()).total_seconds()
    print(f"Loaded {len(df):,} ticks over {span/60:.1f} min, "
          f"{df['exchange'].nunique()} exchanges\n")

    returns, coverage = build_grid(df, args.resample_ms)
    max_lag = int(round(args.max_lag_s * 1000 / args.resample_ms))

    print(f"Grid: {args.resample_ms}ms bins, {len(returns):,} bins. "
          f"Lag scan: +/-{args.max_lag_s}s ({max_lag} steps each side)\n")

    print("Per-exchange coverage (fraction of bins with a real update):")
    for ex in sorted(coverage, key=lambda e: -coverage[e]):
        flag = "  <-- SPARSE, unreliable" if coverage[ex] < args.min_coverage else ""
        print(f"  {ex:10s} {coverage[ex]*100:6.2f}%{flag}")
    print()

    usable = [ex for ex in returns.columns if coverage[ex] >= args.min_coverage]
    dropped = [ex for ex in returns.columns if ex not in usable]
    if dropped:
        print(f"Dropping sparse exchanges from pairwise analysis: {dropped}\n")

    results = []
    for a_ex, b_ex in combinations(sorted(usable), 2):
        a = returns[a_ex].to_numpy()
        b = returns[b_ex].to_numpy()
        lags, corrs = lagged_corr(a, b, max_lag)
        if np.all(np.isnan(corrs)):
            continue
        best_i = int(np.nanargmax(np.abs(corrs)))
        best_lag_steps = int(lags[best_i])
        best_lag_ms = best_lag_steps * args.resample_ms
        best_corr = float(corrs[best_i])
        zero_corr = float(corrs[max_lag])  # lag 0 (contemporaneous)
        # who leads
        if best_lag_ms > 0:
            leader, follower, lead_ms = a_ex, b_ex, best_lag_ms
        elif best_lag_ms < 0:
            leader, follower, lead_ms = b_ex, a_ex, -best_lag_ms
        else:
            leader, follower, lead_ms = "(simultaneous)", "", 0
        results.append({
            "a": a_ex, "b": b_ex,
            "leader": leader, "follower": follower, "lead_ms": lead_ms,
            "best_corr": best_corr, "zero_corr": zero_corr,
            "lift_over_zero": abs(best_corr) - abs(zero_corr),
        })

    if not results:
        print("No usable pairs. Aborting.")
        return 0

    res = pd.DataFrame(results)

    print("=" * 78)
    print("PAIRWISE LEAD-LAG (sorted by correlation strength at optimal lag)")
    print("=" * 78)
    print(f"{'pair':24s} {'leader':10s} {'lead(ms)':>9s} "
          f"{'corr@opt':>9s} {'corr@0':>8s} {'lift':>7s}")
    print("-" * 78)
    for _, r in res.sort_values("best_corr", key=lambda s: s.abs(),
                                ascending=False).iterrows():
        pair = f"{r['a']}<->{r['b']}"
        leader = r["leader"] if r["leader"] != "(simultaneous)" else "tie@0"
        print(f"{pair:24s} {leader:10s} {r['lead_ms']:9.0f} "
              f"{r['best_corr']:9.3f} {r['zero_corr']:8.3f} "
              f"{r['lift_over_zero']:7.3f}")
    print()

    # Directed lead matrix
    exs = sorted(usable)
    print("Lead matrix: cell[row,col] = ms by which ROW leads COL "
          "(blank if col leads row or tie):")
    header = "          " + "".join(f"{e[:8]:>10s}" for e in exs)
    print(header)
    for r_ex in exs:
        cells = []
        for c_ex in exs:
            if r_ex == c_ex:
                cells.append(f"{'--':>10s}")
                continue
            row = res[((res.a == r_ex) & (res.b == c_ex)) |
                      ((res.a == c_ex) & (res.b == r_ex))]
            if row.empty or row.iloc[0]["leader"] != r_ex:
                cells.append(f"{'':>10s}")
            else:
                cells.append(f"{row.iloc[0]['lead_ms']:>10.0f}")
        print(f"{r_ex[:9]:9s} " + "".join(cells))
    print()

    # Explotability assessment
    print("=" * 78)
    print("EXPLOITABILITY ASSESSMENT")
    print("=" * 78)
    EXEC_LATENCY_MS = 5  # stated <5ms execution latency
    CORR_STRONG = 0.30   # threshold for a "tradeable" predictive signal
    LAG_MIN_MS = EXEC_LATENCY_MS * 2  # need lead comfortably above our latency

    strong = res[(res.best_corr.abs() >= CORR_STRONG) &
                 (res.lead_ms >= LAG_MIN_MS)]
    weakcorr = res[res.best_corr.abs() < CORR_STRONG]
    shortlag = res[(res.best_corr.abs() >= CORR_STRONG) &
                   (res.lead_ms < LAG_MIN_MS)]

    print(f"Criteria: |corr| >= {CORR_STRONG}, lead >= {LAG_MIN_MS}ms "
          f"(2x the <{EXEC_LATENCY_MS}ms exec latency)\n")

    if not strong.empty:
        print("EXPLOITABLE candidates (strong corr AND lead beats latency):")
        for _, r in strong.sort_values("best_corr", key=lambda s: s.abs(),
                                       ascending=False).iterrows():
            print(f"  {r['leader']} leads {r['follower']} by {r['lead_ms']:.0f}ms "
                  f"@ corr {r['best_corr']:.3f}")
    else:
        print("NO pairs meet both thresholds. Nothing cleanly exploitable.")

    if not shortlag.empty:
        print("\nStrong correlation but lead too short to execute "
              f"(< {LAG_MIN_MS}ms):")
        for _, r in shortlag.iterrows():
            tie = "contemporaneous" if r["lead_ms"] == 0 else f"{r['lead_ms']:.0f}ms"
            print(f"  {r['a']}<->{r['b']}: corr {r['best_corr']:.3f}, lead {tie} "
                  f"-> moves are effectively simultaneous, not predictive")

    if not weakcorr.empty:
        print(f"\nWeak/no relationship (|corr| < {CORR_STRONG}): "
              + ", ".join(f"{r.a}<->{r.b}({r.best_corr:.2f})"
                          for _, r in weakcorr.iterrows()))

    print("\n" + "=" * 78)
    print("CAVEATS")
    print("=" * 78)
    print(
        "- Timestamps are ws_received_at (our client receive time). A measured\n"
        "  'lead' conflates true price-discovery lead with differential feed/\n"
        "  network latency per venue. Cannot separate the two from this data.\n"
        "- ffill on quiet bins injects zero-returns; lag-0 correlation can be\n"
        "  inflated by simultaneous bins. We report lift over lag-0 to control.\n"
        "- A lead at the grid resolution (one 100ms bin) is at the edge of\n"
        "  measurability and likely reflects timestamp jitter, not alpha.\n"
        "- Sparse venues (low coverage above) are excluded; their returns are\n"
        "  mostly ffill artifacts."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
