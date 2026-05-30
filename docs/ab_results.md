# A/B Test Results

Performance comparison of two bot configurations replayed over the **same** tick
dataset via `scripts/ab_test.py`. The variable under test is the **micro-price
signal** (`enable_microprice`): when on, the scorer penalizes opportunities whose
short-term order-book pressure is eroding the spread, changing which opportunity
the engine acts on each tick.

Two datasets are reported:
1. **Synthetic** — controlled dislocations engineered to clear fees, so the A/B
   actually produces trades. This is the demo comparison.
2. **Real market data (what-if)** — 50k real ticks under an explicitly relaxed,
   non-production cost model. Clearly labeled: the numbers are *not* achievable at
   live taker fees (see the note at the end).

---

## 1. Synthetic dataset (controlled dislocations)

```bash
python scripts/ab_test.py --synth 10000 \
  --config-a enable_microprice=false \
  --config-b enable_microprice=true
```

`10,000` ticks, seed 42 (deterministic). Both configs funded at 1,000,000 USDT /
20 BTC per venue.

| Metric            | A · micro-price OFF | B · micro-price ON | Winner |
|-------------------|--------------------:|-------------------:|:------:|
| Trades executed   |               1,141 |              1,140 |   A    |
| Precision         |              100.0% |             100.0% |   =    |
| P&L simulated     |         $61,544.46  |        $61,203.08  |   A    |
| True positives    |               1,141 |              1,140 |   A    |
| False positives   |                   0 |                  0 |   =    |
| FPs filtered      |                 296 |                297 |   B    |
| Latency p50 (ms)  |               1.627 |              1.627 |   =    |
| Latency p95 (ms)  |               2.868 |              2.868 |   =    |
| Total decisions   |               1,437 |              1,437 |   =    |

**Read:** both configs are 100% precise (every executed trade was profitable).
Enabling the micro-price signal (B) filters one extra false positive (297 vs 296)
and forgoes one marginal trade, trading ~$341 of headline P&L for that extra
caution — the signal behaving exactly as designed: a small precision/▲caution vs
throughput/▲P&L trade-off. On this clean synthetic data the effect is tiny because
there is little adverse book pressure to detect.

---

## 2. Real market data, VIP maker fees (what-if)

> ⚠️ **WHAT-IF — NOT A PRODUCTION RESULT.** This run applies a *relaxed* cost model
> to expose the pipeline's behaviour on real ticks. It assumes fees at **10% of
> real taker rates** (`fee_multiplier=0.1`, ~a deep VIP/maker rebate) and **no
> per-trade withdrawal cost** (`include_withdrawal=false`, i.e. an inventory model
> where withdrawals are amortized by the rebalancer). At live taker fees this
> dataset yields **zero** profitable trades — real BTC spatial spreads do not clear
> real costs. See `docs/changelog.md` / the diagnosis for the full cost breakdown.

```bash
# Shared what-if cost model applied to BOTH configs (they differ only on micro-price):
python scripts/ab_test.py \
  --dataset data/recordings/market_data.jsonl \
  --limit 50000 \
  --config-a enable_microprice=false fee_multiplier=0.1 include_withdrawal=false \
  --config-b enable_microprice=true  fee_multiplier=0.1 include_withdrawal=false
```

`50,000` real ticks (captured 2026-05-29/30, 6 venues, BTC top-of-book).

| Metric            | A · micro-price OFF | B · micro-price ON | Winner |
|-------------------|--------------------:|-------------------:|:------:|
| Trades executed   |                   0 |                  0 |   =    |
| Precision         |                0.0% |               0.0% |   =    |
| P&L simulated     |              $0.00  |             $0.00  |   =    |
| True positives    |                   0 |                  0 |   =    |
| False positives   |                   0 |                  0 |   =    |
| FPs filtered      |                   0 |                  0 |   =    |
| Latency p50 (ms)  |               0.000 |              0.000 |   =    |
| Latency p95 (ms)  |               0.000 |              0.000 |   =    |
| Total decisions   |                   0 |                  0 |   =    |

### Funnel (`--diagnose`) — where the candidates die

```
ticks consumed         : 50000
state >= 2 venues      : 49997
scanner found opps     : 838   (total opps: 1001)
passed min-spread gate : 838
sized to tradeable qty : 0     (insuff-balance: 0, qty<min: 838)
passed latency buffer  : 0
EXECUTED               : 0
```

**Read:** even at 10% of real fees with no withdrawal, the scanner *does* surface
**838 net-positive opportunities** — so the relaxed economics aren't trivially
free money. But **all 838 die at the sizer**: the QP-optimal trade size
(`q* = s / 2λ`, where `s` is the per-unit net edge and `λ` the market-impact
coefficient) falls **below the 0.001 BTC exchange minimum**. The real spreads are
*net-positive but too thin* to justify even a minimum-size order — the bot
correctly declines to trade. Because nothing executes, the micro-price toggle has
no effect here (A ≡ B).

This is the honest takeaway: real BTC top-of-book spatial arbitrage is not a
profitable strategy at these spreads, and the engine's risk controls (fee model →
scanner gate → impact-aware sizer) reflect that all the way down the funnel. The
synthetic dataset above is the appropriate vehicle for demoing the A/B mechanics.

---

*Reproduce:* both commands are deterministic. Synthetic uses seed 42; the real
dataset replays off the recorded tick clock (`ws_received_at`), so reruns are
byte-identical. Generated with `scripts/ab_test.py` (see `core/replay.py`,
`core/metrics_eval.py`).

---

## 3. Triangular USD≠USDT on real data (the spread spatial can't see)

Spatial arbitrage (same pair, two venues) is dead at real fees — both sections
above confirm it. But the system also runs **triangular** arbitrage
(`core/triangular.py`) over three *distinct* currency nodes (BTC, USD, USDT),
e.g. `USD→BTC→USDT→USD`. That cycle captures the **USDT/USD basis**, which spatial
arb structurally cannot. Analysis over all **454,474** recorded ticks:

```
=== TRIANGULAR FUNNEL · 454,474 real ticks ===
ticks consumed                         : 454,474
triangle feasible (USDT & USD venue)   : 454,471   (99.999%)
── real taker fees (0.1–0.6%) ──────────────────────────────
  ticks with a net-positive triangle   : 0
  total opportunity instances          : 0
── 0.02% active-account fees, stablecoin conv = 1bp ────────
  ticks net-positive (by net_profit_pct): 454,471   (100% of feasible)
  ticks net-positive AFTER withdrawal   : 454,454
  total opportunity instances           : 3,635,434
  best net_profit_pct  : min 7.1bp · median 9.7bp · max 16.3bp
  implied USDT/USD      : min 0.99806 · median 0.99864 · max 0.99887
```

**Q1 — how many at real taker fees?** **Zero.** Binance/OKX taker (0.1%) ×2 legs +
conversion already exceeds the ~13.6 bp basis. Same verdict as spatial.

**Q2 — how many at 0.02% active-account fees?** **All of them** — 454,471 / 454,471
feasible ticks net-positive (and 454,454 still positive after the BTC withdrawal
cost), median **9.7 bp** net per cycle.

**Q3 — the implied USDT/USD spread.** Median **0.99864** ⇒ USDT trades at a
persistent **~13.6 bp discount to USD**, in a very tight band (0.99806–0.99887
across 454k ticks). This is the real-2026 stablecoin basis, and it is exactly what
the triangle monetizes: buy BTC cheap on a USD venue (Kraken/Coinbase/Gemini/
Bitstamp), sell it richer on a USDT venue (Binance/OKX/Bybit), convert USDT→USD.

### The catch — sensitivity to USDT↔USD conversion cost

The headline above prices the stablecoin conversion at **1 bp**
(`DEFAULT_STABLECOIN_COST`). That is optimistic. Sweeping it (at 0.02% trade fees):

| USDT↔USD conversion cost | net-positive ticks / 454,471 | survival |
|--------------------------|-----------------------------:|---------:|
| 1 bp                     |                      454,471 |   100.0% |
| 5 bp                     |                      454,471 |   100.0% |
| 10 bp                    |                      392,676 |    86.4% |
| **13.6 bp (= the basis)**|                        1,330 |     0.3% |
| 20 bp                    |                            0 |     0.0% |

The opportunity collapses precisely when the modeled conversion cost reaches the
implied basis (~13.6 bp) — confirming the profit is, by construction,
`basis − conversion_cost`. So this is **real iff you can convert USDT↔USD below the
basis**: at a 1–5 bp stablecoin rail it's a fat ~9 bp edge on essentially every
tick; up to ~10 bp it still clears 86% of ticks; at the basis it nets out.

**Verdict.** Triangular USD/USDT *does* surface real opportunities the spatial
scanner cannot — the persistent ~13.6 bp USDT/USD basis — and they are net-positive
on 100% of ticks at active-account trading fees. Their realizability is gated not
by the trade fees (where spatial dies) but by the **stablecoin conversion rail**:
viable with a sub-10 bp USDT/USD path, marginal at the basis itself.

> Caveat: the "implied basis" is `aggregate USD-venue mid ÷ aggregate USDT-venue
> mid`, so it blends the true stablecoin basis with any structural cross-venue BTC
> pricing difference. Its tightness and stability argue for a genuine basis, but a
> direct same-venue USDT/USD quote (the detector accepts one via `stablecoin_cost`)
> would settle it. We don't record USDT/USD pairs yet — a worthwhile next capture.

---

## 4. Convex unification — validating `core/convex_arb.py`

Sections 1–3 use **separate** modules: the spatial scanner (`core/scanner.py`) and
the triangular detector (`core/triangular.py`), each finding *and then* sizing
opportunities in its own pass. `core/convex_arb.py` reformulates the whole thing
as **one convex program** (Angeris–Evans–Chitra–Boyd, *Optimal Routing for CFMMs*,
ACM EC 2022, specialised to limit order books): a single LP that, per tick, either
returns the optimal route **and** the exact per-leg quantities, or **certifies**
that no arbitrage exists (optimum = 0). `--strategy convex` replays the recorded
ticks and checks that claim three ways.

```bash
# real taker fees (the as-deployed cost model)
python scripts/ab_test.py --dataset data/recordings/market_data.jsonl \
  --strategy convex --limit 30000 --fee-multiplier 1.0

# 0.25× taker (a VIP/maker tier, below the ~13.6 bp USDT/USD basis — arb is dense)
python scripts/ab_test.py --dataset data/recordings/market_data.jsonl \
  --strategy convex --limit 30000 --fee-multiplier 0.25
```

The check is **independent**: against the convex LP we run a brute force over every
directed venue pair (with USD↔USDT par conversion) on the *identical* taker-fee +
stablecoin cost basis. Existence of any profitable single-BTC-hop cycle ⇔ the LP
optimum is > 0 (multi-venue routing changes the optimal *size*, never whether one
exists), so the two must agree on every tick. A genuine disagreement is a bug; the
script exits non-zero if it finds one (CI gate).

`30,000` real ticks per slice (replayed off the recorded tick clock; deterministic).

| Question                                   | ×1.0 real fees | ×0.25 VIP tier |
|--------------------------------------------|---------------:|---------------:|
| Decidable ticks (≥2 venues)                |         29,997 |         29,997 |
| **Both detect arbitrage**                  |              0 |         29,981 |
| **Both certify no-arbitrage**              |         29,997 |             16 |
| convex-only / classic-only (real)          |          0 / 0 |          0 / 0 |
| **Genuine mismatches**                     |          **0** |          **0** |
| **Detection consistency**                  |       **100%** |       **100%** |
| No-arb certificate: brute agrees           |  29,997/29,997 |        16/16   |
| Same best venue pair (where both detect)   |          — (0) |  23,730/29,981 (79.2%) |
| Convex solver latency p50 / p95 / mean (ms)| 9.06 / 10.29 / 9.55 | 9.73 / 10.63 / 10.14 |

**Q1 — does convex flag the same opportunities?** **Yes, exactly.** On both fee
tiers, every tick where the brute force finds a profitable cycle, the LP optimum is
> 0, and vice-versa — **0 genuine mismatches over ~60,000 ticks**, 100% detection
consistency. The "same best venue pair" being 79.2% (not 100%) at ×0.25 is **not**
error: where several venue pairs are near-tied or the higher-multiplier pair is
shallower, the LP (which maximizes absolute USD profit) and the brute force can pick
*different but equally valid* routes. The detection *decision* never differs.

**Q2 — is the "no arbitrage" certificate consistent?** **Yes.** Every tick the LP
certified `no arbitrage exists (convex optimum = 0)`, the brute force independently
confirmed no profitable cycle: 29,997/29,997 at real fees, 16/16 at ×0.25. At real
taker fees this is the *entire* dataset — the same verdict as the spatial scanner
(0 ticks) and the triangular detector (0 ticks) in §2–3: the ~13.6 bp USDT/USD
basis does not clear ~real round-trip taker fees. The convex program reaches that
conclusion as a *mathematical certificate*, not a heuristic miss.

**Q3 — what does the solver cost per tick?** **~10 ms** (p50 ≈ 9–10 ms, p95 ≈
10–11 ms, mean ≈ 10 ms, with a long tail to ~60 ms). This is the headline tradeoff:
the unified LP replaces the microsecond in-memory scanner with a per-tick conic
solve — three to four orders of magnitude slower. So `convex_arb` is **not** a
hot-path replacement; its value is offline/periodic — exact joint detection +
sizing + a no-arbitrage *proof*, and a single model that subsumes both the spatial
and triangular passes. (The live detection path stays in-memory per `CLAUDE.md`.)

> Numerical note: the LP is solved on **price-normalized** data (every BTC price
> divided by a representative ~$70k scale) so the constraint matrix is O(1); without
> it CLARABEL exhausts its iteration budget on the dense-arbitrage low-fee ticks.
> The solver escalates CLARABEL → CLARABEL(more iters) → SCS, so a single hard tick
> never aborts the replay (0 solver failures across all runs above).

> Production-context line: the report also tallies the **live** scanner/triangular
> at real fees (0/0 ticks here), to relate the validation to what the deployed
> system would flag — those modules additionally charge withdrawal/latency/slippage,
> so they are strictly stricter than the pure-price convex/triangular basis.

*Reproduce:* deterministic (tick-clock replay). Validation logic in
`core/convex_eval.py`; the solver in `core/convex_arb.py`. Covered by
`tests/sanity/test_convex_arb.py` (15) and `tests/sanity/test_convex_eval.py` (8).
