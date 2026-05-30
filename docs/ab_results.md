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
