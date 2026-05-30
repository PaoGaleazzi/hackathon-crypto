#!/usr/bin/env python3
"""A/B-test two arbitrage-bot configs over one recorded tick dataset.

Replays the SAME JSONL tick stream under config A and config B, then prints a
side-by-side metrics table (precision, simulated P&L, false positives filtered,
latency p50/p95, trades executed).

    # against a recording produced by core.replay.TickRecorder
    python scripts/ab_test.py --dataset ticks.jsonl

    # no recording handy? synthesize a deterministic dataset
    python scripts/ab_test.py --synth 2000

    # define the two configs from the command line (KEY=VALUE per knob)
    python scripts/ab_test.py --dataset data/recordings/market_data.jsonl \\
        --config-a enable_microprice=false \\
        --config-b enable_microprice=true

Any RunConfig knob is overridable: enable_microprice, apply_latency_buffer,
min_net_spread_usd, assumed_latency_ms, latency_buffer_k, tau_ms, stale_quote_ms,
min_fill_ratio, vol_window, min_trade_size_btc, initial_usdt, initial_btc, name.
With no --config-a/--config-b the built-in "wide-open" vs "strict" preset is used.

    # validate the unified convex detector (core.convex_arb.solve_arbitrage)
    # against the separate scanner+triangular path, over the same ticks
    python scripts/ab_test.py --dataset data/recordings/market_data.jsonl \\
        --strategy convex --limit 20000 --fee-multiplier 0.3

The --strategy convex mode answers: does the one convex program flag the same
opportunities, does its "no arbitrage" certificate stay consistent, and what does
the LP solve cost per tick. --fee-multiplier scales taker fees to model a
maker/VIP tier (real fees rarely cross on top-of-book, so nothing trades at 1.0)."""

from __future__ import annotations

import argparse
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from itertools import islice
from pathlib import Path
from random import Random

# Make `backend/` importable when run as a standalone script from the repo root.
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.convex_arb import DEFAULT_MIN_PROFIT_USD  # noqa: E402
from core.convex_eval import compare_strategies, render_comparison  # noqa: E402
from core.metrics_eval import RunMetrics, evaluate_run  # noqa: E402
from core.replay import (  # noqa: E402
    ReplayStats,
    RunConfig,
    load_ticks,
    replay_ticks,
    run_replay,
)
from core.triangular import DEFAULT_STABLECOIN_COST  # noqa: E402
from models.market import BBO, Exchange  # noqa: E402


# ── configs under test ───────────────────────────────────────────────────────


def build_configs() -> tuple[RunConfig, RunConfig]:
    """The A vs B hypothesis. A trades every positive edge; B adds a $5 net-spread
    floor and the latency-risk gate — expected to lift precision and filter more
    false positives at the cost of fewer trades."""
    # Funded generously so the wallet (not the strategy) isn't what limits trades.
    funded = dict(initial_usdt=1_000_000.0, initial_btc=20.0)
    config_a = RunConfig(
        name="A: wide-open",
        min_net_spread_usd=0.0,
        apply_latency_buffer=False,
        **funded,
    )
    config_b = RunConfig(
        name="B: strict",
        min_net_spread_usd=5.0,
        apply_latency_buffer=True,
        assumed_latency_ms=50.0,
        **funded,
    )
    return config_a, config_b


# Wallets funded generously so the strategy, not the balance, drives the result.
_FUNDED = dict(initial_usdt=1_000_000.0, initial_btc=20.0)

# Override-able RunConfig knobs grouped by how to coerce the string CLI value.
_BOOL_KNOBS = frozenset(
    {"apply_latency_buffer", "enable_microprice", "include_withdrawal"}
)
_INT_KNOBS = frozenset({"vol_window", "stale_quote_ms"})
_FLOAT_KNOBS = frozenset(
    {
        "min_net_spread_usd", "min_trade_size_btc", "tau_ms", "latency_buffer_k",
        "assumed_latency_ms", "min_fill_ratio", "initial_usdt", "initial_btc",
        "fee_multiplier",
    }
)
_STR_KNOBS = frozenset({"name"})


def _to_bool(raw: str) -> bool:
    low = raw.strip().lower()
    if low in ("true", "1", "yes", "on"):
        return True
    if low in ("false", "0", "no", "off"):
        return False
    raise SystemExit(f"ab_test: cannot read {raw!r} as a boolean")


def _coerce(key: str, raw: str):
    """Coerce a CLI KEY=VALUE string to the type RunConfig expects for that knob."""
    if key in _BOOL_KNOBS:
        return _to_bool(raw)
    if key in _STR_KNOBS:
        return raw
    if key in _INT_KNOBS:
        return None if raw.lower() == "none" else int(raw)
    if key in _FLOAT_KNOBS:
        return None if raw.lower() == "none" else float(raw)
    raise SystemExit(
        f"ab_test: unknown config knob {key!r} "
        f"(known: {', '.join(sorted(_BOOL_KNOBS | _INT_KNOBS | _FLOAT_KNOBS | _STR_KNOBS))})"
    )


def make_config(letter: str, overrides: list[str]) -> RunConfig:
    """Build one RunConfig from a funded base plus CLI KEY=VALUE overrides.

    The config's name defaults to the override summary (e.g. "A: enable_microprice
    =false") so it reads clearly as a column header, unless name= is set explicitly."""
    coerced: dict = {}
    for pair in overrides:
        key, sep, val = pair.partition("=")
        key = key.strip()
        if not sep or not key:
            raise SystemExit(f"ab_test: bad override {pair!r}, expected KEY=VALUE")
        coerced[key] = _coerce(key, val.strip())

    kwargs = {**_FUNDED, **coerced}
    if "name" not in coerced:
        kwargs["name"] = f"{letter}: " + " ".join(overrides) if overrides else letter
    return RunConfig(**kwargs)


@contextmanager
def _quiet_solver():
    """Silence native (C-extension) stdout from the QP solver at the fd level."""
    saved = os.dup(1)
    devnull = os.open(os.devnull, os.O_WRONLY)
    sys.stdout.flush()
    os.dup2(devnull, 1)
    try:
        yield
    finally:
        sys.stdout.flush()
        os.dup2(saved, 1)
        os.close(saved)
        os.close(devnull)


# ── synthetic dataset ────────────────────────────────────────────────────────


def synth_ticks(n: int, seed: int = 42) -> list[BBO]:
    """Deterministic BTC tick stream across 4 venues with occasional real
    dislocations (true arbs) and thin noise crosses (false positives), so the
    gates have something to separate. Seeded — same n+seed ⇒ same dataset."""
    rng = Random(seed)
    exchanges = [Exchange.BINANCE, Exchange.KRAKEN, Exchange.COINBASE, Exchange.OKX]
    base = 70_000.0
    t0 = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
    ticks: list[BBO] = []
    for i in range(n):
        ex = exchanges[i % len(exchanges)]
        mid = base + rng.gauss(0.0, 5.0)
        spread = rng.uniform(0.5, 2.5)
        roll = rng.random()
        # Dislocations must clear round-trip taker fees (~140+ USD/BTC) to matter.
        if roll < 0.08:                      # fat dislocation → clear, real arb
            mid += rng.choice((-1, 1)) * rng.uniform(200.0, 500.0)
        elif roll < 0.22:                    # marginal cross → straddles the gates
            mid += rng.choice((-1, 1)) * rng.uniform(120.0, 200.0)
        ws = t0 + timedelta(milliseconds=i * 100)
        norm = ws + timedelta(milliseconds=rng.uniform(0.2, 3.0))
        ticks.append(
            BBO(
                exchange=ex,
                bid=mid - spread / 2,
                ask=mid + spread / 2,
                bid_qty=rng.uniform(0.5, 3.0),
                ask_qty=rng.uniform(0.5, 3.0),
                ws_received_at=ws,
                normalized_at=norm,
            )
        )
    return ticks


# ── table rendering ──────────────────────────────────────────────────────────

# (label, accessor, formatter, "higher is better" | "lower" | None)
_ROWS: list[tuple] = [
    ("Trades executed",  lambda m: m.trades_executed,          "{:d}".format,    "up"),
    ("Precision",        lambda m: m.precision,                "{:.1%}".format,  "up"),
    ("P&L simulated",    lambda m: m.pnl_simulated,            "${:,.2f}".format, "up"),
    ("True positives",   lambda m: m.true_positives,           "{:d}".format,    "up"),
    ("False positives",  lambda m: m.false_positives,          "{:d}".format,    "down"),
    ("FPs filtered",     lambda m: m.false_positives_filtered, "{:d}".format,    "up"),
    ("Latency p50 (ms)", lambda m: m.latency_p50_ms,           "{:.3f}".format,  "down"),
    ("Latency p95 (ms)", lambda m: m.latency_p95_ms,           "{:.3f}".format,  "down"),
    ("Total decisions",  lambda m: m.n_trades,                 "{:d}".format,    None),
]


def _winner(a_val: float, b_val: float, better: str | None) -> str:
    if better is None or a_val == b_val:
        return "="
    if better == "up":
        return "A" if a_val > b_val else "B"
    return "A" if a_val < b_val else "B"


def render_table(a: RunMetrics, b: RunMetrics) -> str:
    headers = ("Metric", a.label, b.label, "Win")
    rows = [headers]
    for name, get, fmt, better in _ROWS:
        av, bv = get(a), get(b)
        rows.append((name, fmt(av), fmt(bv), _winner(av, bv, better)))

    widths = [max(len(r[c]) for r in rows) for c in range(4)]
    sep = "─┼─".join("─" * w for w in widths)

    def line(cells: tuple[str, ...]) -> str:
        return " │ ".join(cell.ljust(widths[c]) for c, cell in enumerate(cells))

    out = [line(headers), sep]
    out += [line(r) for r in rows[1:]]
    return "\n".join(out)


# ── main ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--dataset", type=Path, help="JSONL tick recording to replay")
    src.add_argument("--synth", type=int, metavar="N", help="synthesize N ticks instead")
    parser.add_argument("--seed", type=int, default=42, help="seed for --synth")
    parser.add_argument(
        "--config-a", nargs="*", metavar="KEY=VAL", default=None,
        help="config A knobs, e.g. enable_microprice=false",
    )
    parser.add_argument(
        "--config-b", nargs="*", metavar="KEY=VAL", default=None,
        help="config B knobs, e.g. enable_microprice=true",
    )
    parser.add_argument(
        "--limit", type=int, default=None, metavar="N",
        help="replay only the first N ticks of --dataset (handy for huge files)",
    )
    parser.add_argument(
        "--diagnose", action="store_true",
        help="print the per-stage funnel (where candidates die) for each config",
    )
    parser.add_argument(
        "--strategy", choices=("classic", "convex"), default="classic",
        help="classic = scanner+scorer+sizer A/B table (default); convex = "
             "validate the unified core.convex_arb solver against scanner+triangular",
    )
    parser.add_argument(
        "--fee-multiplier", type=float, default=1.0, metavar="M",
        help="[convex] scale taker fees to model a maker/VIP tier (default 1.0)",
    )
    parser.add_argument(
        "--stablecoin-cost", type=float, default=DEFAULT_STABLECOIN_COST, metavar="C",
        help="[convex] USD↔USDT par-conversion spread per leg",
    )
    parser.add_argument(
        "--min-profit-usd", type=float, default=DEFAULT_MIN_PROFIT_USD, metavar="U",
        help="[convex] optimum below this is certified as no arbitrage",
    )
    args = parser.parse_args(argv)

    if args.dataset is not None:
        ticks = _load_dataset(args.dataset, args.limit)
        source = f"{args.dataset} ({len(ticks)} ticks{' [limited]' if args.limit else ''})"
    else:
        ticks = synth_ticks(args.synth, seed=args.seed)
        source = f"synthetic ({len(ticks)} ticks, seed={args.seed})"

    if args.strategy == "convex":
        with _quiet_solver():  # mute the cvxpy/CLARABEL native chatter from the LP
            cmp = compare_strategies(
                ticks,
                fee_multiplier=args.fee_multiplier,
                stablecoin_cost=args.stablecoin_cost,
                min_profit_usd=args.min_profit_usd,
            )
        print()
        print(render_comparison(cmp, source=source))
        # Exit non-zero if convex and the classic detector genuinely disagree, so
        # the validation can gate CI.
        return 1 if cmp.mismatches else 0

    if args.config_a is not None or args.config_b is not None:
        config_a = make_config("A", args.config_a or [])
        config_b = make_config("B", args.config_b or [])
    else:
        config_a, config_b = build_configs()

    stats_a, stats_b = ReplayStats(), ReplayStats()
    with _quiet_solver():  # mute the cvxpy/OSQP native chatter from the QP sizer
        metrics_a = evaluate_run(run_replay(ticks, config_a, stats_a), label=config_a.name)
        metrics_b = evaluate_run(run_replay(ticks, config_b, stats_b), label=config_b.name)

    print(f"\nDataset: {source}\n")
    print(render_table(metrics_a, metrics_b))
    print()
    if args.diagnose:
        for cfg, stat in ((config_a, stats_a), (config_b, stats_b)):
            print(f"── funnel · {cfg.name} "
                  f"(fee_multiplier={cfg.fee_multiplier}, "
                  f"include_withdrawal={cfg.include_withdrawal}) ──")
            print(stat.funnel())
            print()
    return 0


def _load_dataset(path: Path, limit: int | None) -> list[BBO]:
    """Load a recording, optionally only its first ``limit`` ticks."""
    if limit is None:
        return load_ticks(path)
    return list(islice(replay_ticks(path), limit))


if __name__ == "__main__":
    raise SystemExit(main())
