export type Exchange = 'binance' | 'kraken' | 'coinbase' | 'okx'

export type OpportunityStatus =
  | 'EXECUTED'
  | 'REJECTED_NEGATIVE_NET'
  | 'ABORTED_STALE'
  | 'PENDING'

export type TradeStatus =
  | 'EXECUTED'
  | 'ABORTED_STALE'
  | 'SKIPPED_MIN_FILL'
  | 'REJECTED_INSUFFICIENT_BALANCE'
  | 'REJECTED_NEGATIVE_NET'
  | 'CIRCUIT_BREAKER_OPEN'

export interface Opportunity {
  id: string
  buy_exchange: Exchange
  sell_exchange: Exchange
  buy_ask: number
  sell_bid: number
  gross_spread: number
  net_spread: number
  score: number
  optimal_qty: number
  detected_at: string
  status: OpportunityStatus
}

export interface Trade {
  id: string
  buy_exchange: Exchange
  sell_exchange: Exchange
  qty: number
  buy_price: number
  sell_price: number
  fee_buy: number
  fee_sell: number
  slippage_est: number
  net_profit: number
  status: TradeStatus
  ws_received_at: string
  decision_at: string
  latency_ms: number
  executed_at: string
}

export interface PnlPoint {
  time: number
  value: number
}

export interface Metrics {
  total_pnl_usdt: number
  opportunities_today: number
  best_spread_pct: number
  p95_latency_ms: number
  circuit_breaker: 'OPEN' | 'CLOSED'
  bot_active: boolean
  exchanges_connected: Exchange[]
}

// Base timestamp: 4 hours ago from a fixed demo time
const NOW_MS = new Date('2026-05-29T20:00:00Z').getTime()

function tsAt(minutesAgo: number): string {
  return new Date(NOW_MS - minutesAgo * 60 * 1000).toISOString()
}

const BTC_BASE = 67_400

export const OPPORTUNITIES: Opportunity[] = [
  { id: 'opp-001', buy_exchange: 'binance',  sell_exchange: 'kraken',   buy_ask: BTC_BASE, sell_bid: 67_656, gross_spread: 255.92, net_spread: 168.69, score: 0.92, optimal_qty: 0.100, detected_at: tsAt(12),  status: 'EXECUTED' },
  { id: 'opp-002', buy_exchange: 'kraken',   sell_exchange: 'coinbase', buy_ask: BTC_BASE, sell_bid: 67_548, gross_spread:  88.16, net_spread:  47.06, score: 0.74, optimal_qty: 0.058, detected_at: tsAt(24),  status: 'EXECUTED' },
  { id: 'opp-003', buy_exchange: 'coinbase', sell_exchange: 'binance',  buy_ask: BTC_BASE, sell_bid: 67_434, gross_spread:  30.33, net_spread: -16.27, score: 0.18, optimal_qty: 0.090, detected_at: tsAt(37),  status: 'REJECTED_NEGATIVE_NET' },
  { id: 'opp-004', buy_exchange: 'binance',  sell_exchange: 'coinbase', buy_ask: BTC_BASE, sell_bid: 67_609, gross_spread: 186.11, net_spread: 122.46, score: 0.87, optimal_qty: 0.089, detected_at: tsAt(48),  status: 'EXECUTED' },
  { id: 'opp-005', buy_exchange: 'kraken',   sell_exchange: 'binance',  buy_ask: BTC_BASE, sell_bid: 67_521, gross_spread: 121.32, net_spread:  78.62, score: 0.65, optimal_qty: 0.107, detected_at: tsAt(61),  status: 'EXECUTED' },
  { id: 'opp-006', buy_exchange: 'binance',  sell_exchange: 'kraken',   buy_ask: BTC_BASE, sell_bid: 67_447, gross_spread:  47.18, net_spread: -11.92, score: 0.22, optimal_qty: 0.105, detected_at: tsAt(74),  status: 'REJECTED_NEGATIVE_NET' },
  { id: 'opp-007', buy_exchange: 'coinbase', sell_exchange: 'kraken',   buy_ask: BTC_BASE, sell_bid: 67_575, gross_spread: 150.83, net_spread:  97.43, score: 0.80, optimal_qty: 0.086, detected_at: tsAt(85),  status: 'EXECUTED' },
  { id: 'opp-008', buy_exchange: 'binance',  sell_exchange: 'coinbase', buy_ask: BTC_BASE, sell_bid: 67_494, gross_spread:  94.36, net_spread:  58.36, score: 0.55, optimal_qty: 0.104, detected_at: tsAt(98),  status: 'ABORTED_STALE' },
  { id: 'opp-009', buy_exchange: 'kraken',   sell_exchange: 'coinbase', buy_ask: BTC_BASE, sell_bid: 67_622, gross_spread: 198.45, net_spread: 129.95, score: 0.89, optimal_qty: 0.090, detected_at: tsAt(112), status: 'EXECUTED' },
  { id: 'opp-010', buy_exchange: 'coinbase', sell_exchange: 'binance',  buy_ask: BTC_BASE, sell_bid: 67_461, gross_spread:  60.66, net_spread:  -8.74, score: 0.30, optimal_qty: 0.100, detected_at: tsAt(127), status: 'REJECTED_NEGATIVE_NET' },
  { id: 'opp-011', buy_exchange: 'binance',  sell_exchange: 'kraken',   buy_ask: BTC_BASE, sell_bid: 67_596, gross_spread: 174.52, net_spread: 113.82, score: 0.83, optimal_qty: 0.089, detected_at: tsAt(140), status: 'EXECUTED' },
  { id: 'opp-012', buy_exchange: 'kraken',   sell_exchange: 'binance',  buy_ask: BTC_BASE, sell_bid: 67_427, gross_spread:  26.96, net_spread: -17.84, score: 0.11, optimal_qty: 0.100, detected_at: tsAt(155), status: 'REJECTED_NEGATIVE_NET' },
  { id: 'opp-013', buy_exchange: 'coinbase', sell_exchange: 'binance',  buy_ask: BTC_BASE, sell_bid: 67_541, gross_spread: 127.20, net_spread:  81.40, score: 0.71, optimal_qty: 0.090, detected_at: tsAt(168), status: 'EXECUTED' },
  { id: 'opp-014', buy_exchange: 'binance',  sell_exchange: 'coinbase', buy_ask: BTC_BASE, sell_bid: 67_508, gross_spread:  80.88, net_spread:  48.78, score: 0.59, optimal_qty: 0.075, detected_at: tsAt(182), status: 'ABORTED_STALE' },
  { id: 'opp-015', buy_exchange: 'kraken',   sell_exchange: 'coinbase', buy_ask: BTC_BASE, sell_bid: 67_629, gross_spread: 204.32, net_spread: 133.62, score: 0.91, optimal_qty: 0.090, detected_at: tsAt(195), status: 'EXECUTED' },
  { id: 'opp-016', buy_exchange: 'coinbase', sell_exchange: 'kraken',   buy_ask: BTC_BASE, sell_bid: 67_474, gross_spread:  74.14, net_spread:  44.64, score: 0.48, optimal_qty: 0.100, detected_at: tsAt(210), status: 'EXECUTED' },
  { id: 'opp-017', buy_exchange: 'binance',  sell_exchange: 'kraken',   buy_ask: BTC_BASE, sell_bid: 67_440, gross_spread:  36.22, net_spread: -16.48, score: 0.17, optimal_qty: 0.090, detected_at: tsAt(225), status: 'REJECTED_NEGATIVE_NET' },
  { id: 'opp-018', buy_exchange: 'kraken',   sell_exchange: 'binance',  buy_ask: BTC_BASE, sell_bid: 67_562, gross_spread: 144.72, net_spread:  93.72, score: 0.77, optimal_qty: 0.090, detected_at: tsAt(238), status: 'EXECUTED' },
  { id: 'opp-019', buy_exchange: 'coinbase', sell_exchange: 'binance',  buy_ask: BTC_BASE, sell_bid: 67_528, gross_spread: 108.12, net_spread:  67.92, score: 0.62, optimal_qty: 0.085, detected_at: tsAt(5),   status: 'PENDING' },
  { id: 'opp-020', buy_exchange: 'binance',  sell_exchange: 'coinbase', buy_ask: BTC_BASE, sell_bid: 67_588, gross_spread: 168.27, net_spread: 109.67, score: 0.85, optimal_qty: 0.089, detected_at: tsAt(2),   status: 'PENDING' },
]

export const TRADES: Trade[] = [
  { id: 'trd-001', buy_exchange: 'binance',  sell_exchange: 'kraken',   qty: 0.100, buy_price: 67_382.50, sell_price: 67_638.42, fee_buy: 26.94, fee_sell: 47.89, slippage_est: 12.40, net_profit: 168.69, status: 'EXECUTED', ws_received_at: tsAt(12),  decision_at: tsAt(12),  latency_ms: 42.3, executed_at: tsAt(12) },
  { id: 'trd-002', buy_exchange: 'kraken',   sell_exchange: 'coinbase', qty: 0.058, buy_price: 67_355.20, sell_price: 67_507.32, fee_buy: 11.52, fee_sell: 20.48, slippage_est:  9.10, net_profit:  47.06, status: 'EXECUTED', ws_received_at: tsAt(24),  decision_at: tsAt(24),  latency_ms: 38.1, executed_at: tsAt(24) },
  { id: 'trd-003', buy_exchange: 'binance',  sell_exchange: 'coinbase', qty: 0.089, buy_price: 67_391.10, sell_price: 67_599.38, fee_buy: 19.24, fee_sell: 34.21, slippage_est: 10.20, net_profit: 122.46, status: 'EXECUTED', ws_received_at: tsAt(48),  decision_at: tsAt(48),  latency_ms: 55.7, executed_at: tsAt(48) },
  { id: 'trd-004', buy_exchange: 'kraken',   sell_exchange: 'binance',  qty: 0.107, buy_price: 67_368.90, sell_price: 67_490.22, fee_buy: 12.71, fee_sell: 22.59, slippage_est:  7.40, net_profit:  78.62, status: 'EXECUTED', ws_received_at: tsAt(61),  decision_at: tsAt(61),  latency_ms: 31.8, executed_at: tsAt(61) },
  { id: 'trd-005', buy_exchange: 'coinbase', sell_exchange: 'kraken',   qty: 0.086, buy_price: 67_344.75, sell_price: 67_519.93, fee_buy: 15.70, fee_sell: 27.90, slippage_est:  9.80, net_profit:  97.43, status: 'EXECUTED', ws_received_at: tsAt(85),  decision_at: tsAt(85),  latency_ms: 47.2, executed_at: tsAt(85) },
  { id: 'trd-006', buy_exchange: 'kraken',   sell_exchange: 'coinbase', qty: 0.090, buy_price: 67_378.40, sell_price: 67_600.50, fee_buy: 20.48, fee_sell: 36.42, slippage_est: 11.60, net_profit: 129.95, status: 'EXECUTED', ws_received_at: tsAt(112), decision_at: tsAt(112), latency_ms: 29.6, executed_at: tsAt(112) },
  { id: 'trd-007', buy_exchange: 'binance',  sell_exchange: 'kraken',   qty: 0.089, buy_price: 67_362.80, sell_price: 67_558.52, fee_buy: 18.11, fee_sell: 32.19, slippage_est: 10.40, net_profit: 113.82, status: 'EXECUTED', ws_received_at: tsAt(140), decision_at: tsAt(140), latency_ms: 61.4, executed_at: tsAt(140) },
  { id: 'trd-008', buy_exchange: 'coinbase', sell_exchange: 'binance',  qty: 0.090, buy_price: 67_338.60, sell_price: 67_479.80, fee_buy: 13.36, fee_sell: 23.74, slippage_est:  8.70, net_profit:  81.40, status: 'EXECUTED', ws_received_at: tsAt(168), decision_at: tsAt(168), latency_ms: 44.9, executed_at: tsAt(168) },
  { id: 'trd-009', buy_exchange: 'kraken',   sell_exchange: 'coinbase', qty: 0.090, buy_price: 67_372.20, sell_price: 67_599.80, fee_buy: 21.10, fee_sell: 37.50, slippage_est: 12.10, net_profit: 133.62, status: 'EXECUTED', ws_received_at: tsAt(195), decision_at: tsAt(195), latency_ms: 33.5, executed_at: tsAt(195) },
  { id: 'trd-010', buy_exchange: 'coinbase', sell_exchange: 'kraken',   qty: 0.100, buy_price: 67_325.40, sell_price: 67_399.54, fee_buy:  8.10, fee_sell: 14.40, slippage_est:  7.00, net_profit:  44.64, status: 'SKIPPED_MIN_FILL', ws_received_at: tsAt(210), decision_at: tsAt(210), latency_ms: 28.3, executed_at: tsAt(210) },
  { id: 'trd-011', buy_exchange: 'kraken',   sell_exchange: 'binance',  qty: 0.090, buy_price: 67_348.10, sell_price: 67_512.82, fee_buy: 15.01, fee_sell: 26.69, slippage_est:  9.30, net_profit:  93.72, status: 'EXECUTED', ws_received_at: tsAt(238), decision_at: tsAt(238), latency_ms: 52.1, executed_at: tsAt(238) },
  { id: 'trd-012', buy_exchange: 'binance',  sell_exchange: 'coinbase', qty: 0.060, buy_price: 67_405.30, sell_price: 67_457.70, fee_buy:  6.55, fee_sell: 11.65, slippage_est:  6.10, net_profit:   7.14, status: 'SKIPPED_MIN_FILL', ws_received_at: tsAt(252), decision_at: tsAt(252), latency_ms: 67.8, executed_at: tsAt(252) },
  { id: 'trd-013', buy_exchange: 'kraken',   sell_exchange: 'coinbase', qty: 0.150, buy_price: 67_332.80, sell_price: 67_539.26, fee_buy: 29.30, fee_sell: 52.10, slippage_est: 15.30, net_profit: 212.99, status: 'EXECUTED', ws_received_at: tsAt(270), decision_at: tsAt(270), latency_ms: 39.2, executed_at: tsAt(270) },
  { id: 'trd-014', buy_exchange: 'coinbase', sell_exchange: 'binance',  qty: 0.080, buy_price: 67_358.90, sell_price: 67_458.24, fee_buy: 10.84, fee_sell: 19.26, slippage_est:  7.80, net_profit:  41.57, status: 'EXECUTED', ws_received_at: tsAt(289), decision_at: tsAt(289), latency_ms: 25.7, executed_at: tsAt(289) },
  { id: 'trd-015', buy_exchange: 'binance',  sell_exchange: 'kraken',   qty: 0.120, buy_price: 67_320.60, sell_price: 67_495.32, fee_buy: 19.84, fee_sell: 35.26, slippage_est: 11.90, net_profit: 142.66, status: 'EXECUTED', ws_received_at: tsAt(305), decision_at: tsAt(305), latency_ms: 48.6, executed_at: tsAt(305) },
  { id: 'trd-016', buy_exchange: 'kraken',   sell_exchange: 'binance',  qty: 0.075, buy_price: 67_388.20, sell_price: 67_496.54, fee_buy:  9.61, fee_sell: 17.09, slippage_est:  7.50, net_profit:  47.05, status: 'EXECUTED', ws_received_at: tsAt(322), decision_at: tsAt(322), latency_ms: 36.4, executed_at: tsAt(322) },
  { id: 'trd-017', buy_exchange: 'coinbase', sell_exchange: 'kraken',   qty: 0.110, buy_price: 67_310.50, sell_price: 67_498.92, fee_buy: 19.62, fee_sell: 34.88, slippage_est: 12.40, net_profit: 140.82, status: 'EXECUTED', ws_received_at: tsAt(340), decision_at: tsAt(340), latency_ms: 43.1, executed_at: tsAt(340) },
  { id: 'trd-018', buy_exchange: 'binance',  sell_exchange: 'coinbase', qty: 0.040, buy_price: 67_418.70, sell_price: 67_451.10, fee_buy:  3.53, fee_sell:  6.27, slippage_est:  5.20, net_profit:   3.24, status: 'SKIPPED_MIN_FILL', ws_received_at: tsAt(358), decision_at: tsAt(358), latency_ms: 71.5, executed_at: tsAt(358) },
  { id: 'trd-019', buy_exchange: 'kraken',   sell_exchange: 'coinbase', qty: 0.130, buy_price: 67_298.40, sell_price: 67_499.08, fee_buy: 24.66, fee_sell: 43.84, slippage_est: 13.70, net_profit: 178.69, status: 'EXECUTED', ws_received_at: tsAt(375), decision_at: tsAt(375), latency_ms: 34.8, executed_at: tsAt(375) },
  { id: 'trd-020', buy_exchange: 'coinbase', sell_exchange: 'binance',  qty: 0.090, buy_price: 67_365.00, sell_price: 67_498.20, fee_buy: 13.82, fee_sell: 24.58, slippage_est:  8.40, net_profit:  73.08, status: 'EXECUTED', ws_received_at: tsAt(393), decision_at: tsAt(393), latency_ms: 59.3, executed_at: tsAt(393) },
]

// 100 P&L points over 8 hours, cumulative curve from 0 to ~847
export const PNL_SERIES: PnlPoint[] = (() => {
  const eightHoursMs = 8 * 60 * 60 * 1000
  const startMs = NOW_MS - eightHoursMs
  const points: PnlPoint[] = []
  const totalPoints = 100
  let cumulative = 0

  const checkpoints: [number, number][] = [
    [0.05, 0],
    [0.08, 47],
    [0.12, 122],
    [0.16, 200],
    [0.20, 279],
    [0.25, 357],
    [0.30, 435],
    [0.35, 504],
    [0.40, 573],
    [0.45, 632],
    [0.50, 680],
    [0.55, 729],
    [0.60, 765],
    [0.65, 796],
    [0.70, 820],
    [0.75, 835],
    [0.80, 840],
    [0.85, 843],
    [0.90, 845],
    [0.95, 846],
    [1.00, 847.32],
  ]

  let checkIdx = 0

  for (let i = 0; i < totalPoints; i++) {
    const frac = i / (totalPoints - 1)
    const timeMs = startMs + frac * eightHoursMs

    while (
      checkIdx < checkpoints.length - 2 &&
      frac > checkpoints[checkIdx + 1][0]
    ) {
      checkIdx++
    }
    const [f0, v0] = checkpoints[checkIdx]
    const [f1, v1] = checkpoints[Math.min(checkIdx + 1, checkpoints.length - 1)]
    const t = f1 === f0 ? 1 : (frac - f0) / (f1 - f0)
    const noise = (Math.sin(i * 2.7) * 4 + Math.cos(i * 1.3) * 3)
    cumulative = Math.max(0, v0 + t * (v1 - v0) + noise)

    points.push({
      time: Math.floor(timeMs / 1000),
      value: Math.round(cumulative * 100) / 100,
    })
  }

  return points
})()

export const METRICS: Metrics = {
  total_pnl_usdt: 847.32,
  opportunities_today: 143,
  best_spread_pct: 0.38,
  p95_latency_ms: 47,
  circuit_breaker: 'CLOSED',
  bot_active: true,
  exchanges_connected: ['binance', 'kraken', 'coinbase'],
}

export interface SpreadCandle {
  time: number   // Unix seconds UTC
  open: number
  high: number
  low: number
  close: number
}

export const SPREAD_CANDLES: SpreadCandle[] = (() => {
  const startSec = Math.floor((NOW_MS - 8 * 60 * 60 * 1000) / 1000)
  const interval = 5 * 60 // 5 minutes in seconds
  const candles: SpreadCandle[] = []
  let prev = 140

  for (let i = 0; i < 96; i++) {
    const r1 = Math.abs(Math.sin(i * 127.1 + 49297) * 1e5) % 1
    const r2 = Math.abs(Math.sin(i * 217.3 + 13441) * 1e5) % 1
    const r3 = Math.abs(Math.sin(i * 91.7 + 72931) * 1e5) % 1
    const r4 = Math.abs(Math.sin(i * 163.9 + 28657) * 1e5) % 1

    const open = prev
    // Mean-revert toward 145 with ±25 USD variance
    const drift = (145 - open) * 0.05
    const close = open + drift + (r1 - 0.5) * 50
    const hi = Math.max(open, close) + r3 * 12
    const lo = Math.min(open, close) - r4 * 12

    candles.push({
      time: startSec + i * interval,
      open: Math.round(open * 100) / 100,
      high: Math.round(hi * 100) / 100,
      low: Math.round(Math.max(lo, 80) * 100) / 100,
      close: Math.round(close * 100) / 100,
    })
    // use r2 only to prevent lint warning — close is already deterministic
    prev = close + (r2 - 0.5) * 0.01
  }

  return candles
})()
