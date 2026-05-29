export type Exchange = 'Binance' | 'Kraken' | 'Coinbase'
export type OpportunityStatus =
  | 'EXECUTED'
  | 'REJECTED_NEGATIVE_NET'
  | 'ABORTED_STALE'
  | 'PENDING'
export type TradeStatus = 'EXECUTED' | 'PARTIAL_FILL' | 'ABORTED_STALE'

export interface Opportunity {
  id: string
  exchange_buy: Exchange
  exchange_sell: Exchange
  spread_pct: number
  gross_usdt: number
  fee_buy_usdt: number
  fee_sell_usdt: number
  slippage_usdt: number
  net_usdt: number
  score: number
  qty_btc: number
  timestamp: string
  status: OpportunityStatus
}

export interface Trade {
  id: string
  exchange_buy: Exchange
  exchange_sell: Exchange
  qty_btc: number
  price_buy: number
  price_sell: number
  gross_usdt: number
  fee_total_usdt: number
  slippage_usdt: number
  net_usdt: number
  fill_ratio: number
  timestamp: string
  status: TradeStatus
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
const FOUR_HOURS_MS = 4 * 60 * 60 * 1000

function tsAt(minutesAgo: number): string {
  return new Date(NOW_MS - minutesAgo * 60 * 1000).toISOString()
}

const EXCHANGES: Exchange[] = ['Binance', 'Kraken', 'Coinbase']
const BTC_BASE = 67_400

export const OPPORTUNITIES: Opportunity[] = [
  {
    id: 'opp-001',
    exchange_buy: 'Binance',
    exchange_sell: 'Kraken',
    spread_pct: 0.38,
    gross_usdt: 255.92,
    fee_buy_usdt: 33.73,
    fee_sell_usdt: 41.10,
    slippage_usdt: 12.40,
    net_usdt: 168.69,
    score: 0.92,
    qty_btc: 0.10,
    timestamp: tsAt(12),
    status: 'EXECUTED',
  },
  {
    id: 'opp-002',
    exchange_buy: 'Kraken',
    exchange_sell: 'Coinbase',
    spread_pct: 0.22,
    gross_usdt: 88.16,
    fee_buy_usdt: 14.20,
    fee_sell_usdt: 17.80,
    slippage_usdt: 9.10,
    net_usdt: 47.06,
    score: 0.74,
    qty_btc: 0.058,
    timestamp: tsAt(24),
    status: 'EXECUTED',
  },
  {
    id: 'opp-003',
    exchange_buy: 'Coinbase',
    exchange_sell: 'Binance',
    spread_pct: 0.05,
    gross_usdt: 30.33,
    fee_buy_usdt: 18.50,
    fee_sell_usdt: 19.20,
    slippage_usdt: 8.90,
    net_usdt: -16.27,
    score: 0.18,
    qty_btc: 0.09,
    timestamp: tsAt(37),
    status: 'REJECTED_NEGATIVE_NET',
  },
  {
    id: 'opp-004',
    exchange_buy: 'Binance',
    exchange_sell: 'Coinbase',
    spread_pct: 0.31,
    gross_usdt: 186.11,
    fee_buy_usdt: 24.55,
    fee_sell_usdt: 28.90,
    slippage_usdt: 10.20,
    net_usdt: 122.46,
    score: 0.87,
    qty_btc: 0.089,
    timestamp: tsAt(48),
    status: 'EXECUTED',
  },
  {
    id: 'opp-005',
    exchange_buy: 'Kraken',
    exchange_sell: 'Binance',
    spread_pct: 0.18,
    gross_usdt: 121.32,
    fee_buy_usdt: 15.80,
    fee_sell_usdt: 19.50,
    slippage_usdt: 7.40,
    net_usdt: 78.62,
    score: 0.65,
    qty_btc: 0.107,
    timestamp: tsAt(61),
    status: 'EXECUTED',
  },
  {
    id: 'opp-006',
    exchange_buy: 'Binance',
    exchange_sell: 'Kraken',
    spread_pct: 0.07,
    gross_usdt: 47.18,
    fee_buy_usdt: 22.10,
    fee_sell_usdt: 25.70,
    slippage_usdt: 11.30,
    net_usdt: -11.92,
    score: 0.22,
    qty_btc: 0.105,
    timestamp: tsAt(74),
    status: 'REJECTED_NEGATIVE_NET',
  },
  {
    id: 'opp-007',
    exchange_buy: 'Coinbase',
    exchange_sell: 'Kraken',
    spread_pct: 0.26,
    gross_usdt: 150.83,
    fee_buy_usdt: 19.90,
    fee_sell_usdt: 23.70,
    slippage_usdt: 9.80,
    net_usdt: 97.43,
    score: 0.80,
    qty_btc: 0.086,
    timestamp: tsAt(85),
    status: 'EXECUTED',
  },
  {
    id: 'opp-008',
    exchange_buy: 'Binance',
    exchange_sell: 'Coinbase',
    spread_pct: 0.14,
    gross_usdt: 94.36,
    fee_buy_usdt: 12.20,
    fee_sell_usdt: 15.60,
    slippage_usdt: 8.20,
    net_usdt: 58.36,
    score: 0.55,
    qty_btc: 0.104,
    timestamp: tsAt(98),
    status: 'ABORTED_STALE',
  },
  {
    id: 'opp-009',
    exchange_buy: 'Kraken',
    exchange_sell: 'Coinbase',
    spread_pct: 0.33,
    gross_usdt: 198.45,
    fee_buy_usdt: 26.10,
    fee_sell_usdt: 30.80,
    slippage_usdt: 11.60,
    net_usdt: 129.95,
    score: 0.89,
    qty_btc: 0.09,
    timestamp: tsAt(112),
    status: 'EXECUTED',
  },
  {
    id: 'opp-010',
    exchange_buy: 'Coinbase',
    exchange_sell: 'Binance',
    spread_pct: 0.09,
    gross_usdt: 60.66,
    fee_buy_usdt: 28.40,
    fee_sell_usdt: 31.90,
    slippage_usdt: 9.10,
    net_usdt: -8.74,
    score: 0.30,
    qty_btc: 0.10,
    timestamp: tsAt(127),
    status: 'REJECTED_NEGATIVE_NET',
  },
  {
    id: 'opp-011',
    exchange_buy: 'Binance',
    exchange_sell: 'Kraken',
    spread_pct: 0.29,
    gross_usdt: 174.52,
    fee_buy_usdt: 23.00,
    fee_sell_usdt: 27.30,
    slippage_usdt: 10.40,
    net_usdt: 113.82,
    score: 0.83,
    qty_btc: 0.089,
    timestamp: tsAt(140),
    status: 'EXECUTED',
  },
  {
    id: 'opp-012',
    exchange_buy: 'Kraken',
    exchange_sell: 'Binance',
    spread_pct: 0.04,
    gross_usdt: 26.96,
    fee_buy_usdt: 17.80,
    fee_sell_usdt: 20.10,
    slippage_usdt: 6.90,
    net_usdt: -17.84,
    score: 0.11,
    qty_btc: 0.10,
    timestamp: tsAt(155),
    status: 'REJECTED_NEGATIVE_NET',
  },
  {
    id: 'opp-013',
    exchange_buy: 'Coinbase',
    exchange_sell: 'Binance',
    spread_pct: 0.21,
    gross_usdt: 127.20,
    fee_buy_usdt: 16.70,
    fee_sell_usdt: 20.40,
    slippage_usdt: 8.70,
    net_usdt: 81.40,
    score: 0.71,
    qty_btc: 0.09,
    timestamp: tsAt(168),
    status: 'EXECUTED',
  },
  {
    id: 'opp-014',
    exchange_buy: 'Binance',
    exchange_sell: 'Coinbase',
    spread_pct: 0.16,
    gross_usdt: 80.88,
    fee_buy_usdt: 10.60,
    fee_sell_usdt: 13.90,
    slippage_usdt: 7.60,
    net_usdt: 48.78,
    score: 0.59,
    qty_btc: 0.075,
    timestamp: tsAt(182),
    status: 'ABORTED_STALE',
  },
  {
    id: 'opp-015',
    exchange_buy: 'Kraken',
    exchange_sell: 'Coinbase',
    spread_pct: 0.34,
    gross_usdt: 204.32,
    fee_buy_usdt: 26.90,
    fee_sell_usdt: 31.70,
    slippage_usdt: 12.10,
    net_usdt: 133.62,
    score: 0.91,
    qty_btc: 0.09,
    timestamp: tsAt(195),
    status: 'EXECUTED',
  },
  {
    id: 'opp-016',
    exchange_buy: 'Coinbase',
    exchange_sell: 'Kraken',
    spread_pct: 0.11,
    gross_usdt: 74.14,
    fee_buy_usdt: 9.70,
    fee_sell_usdt: 12.80,
    slippage_usdt: 7.00,
    net_usdt: 44.64,
    score: 0.48,
    qty_btc: 0.10,
    timestamp: tsAt(210),
    status: 'EXECUTED',
  },
  {
    id: 'opp-017',
    exchange_buy: 'Binance',
    exchange_sell: 'Kraken',
    spread_pct: 0.06,
    gross_usdt: 36.22,
    fee_buy_usdt: 20.30,
    fee_sell_usdt: 23.90,
    slippage_usdt: 8.50,
    net_usdt: -16.48,
    score: 0.17,
    qty_btc: 0.09,
    timestamp: tsAt(225),
    status: 'REJECTED_NEGATIVE_NET',
  },
  {
    id: 'opp-018',
    exchange_buy: 'Kraken',
    exchange_sell: 'Binance',
    spread_pct: 0.24,
    gross_usdt: 144.72,
    fee_buy_usdt: 19.00,
    fee_sell_usdt: 22.70,
    slippage_usdt: 9.30,
    net_usdt: 93.72,
    score: 0.77,
    qty_btc: 0.09,
    timestamp: tsAt(238),
    status: 'EXECUTED',
  },
  {
    id: 'opp-019',
    exchange_buy: 'Coinbase',
    exchange_sell: 'Binance',
    spread_pct: 0.19,
    gross_usdt: 108.12,
    fee_buy_usdt: 14.20,
    fee_sell_usdt: 17.90,
    slippage_usdt: 8.10,
    net_usdt: 67.92,
    score: 0.62,
    qty_btc: 0.085,
    timestamp: tsAt(5),
    status: 'PENDING',
  },
  {
    id: 'opp-020',
    exchange_buy: 'Binance',
    exchange_sell: 'Coinbase',
    spread_pct: 0.28,
    gross_usdt: 168.27,
    fee_buy_usdt: 22.10,
    fee_sell_usdt: 26.50,
    slippage_usdt: 10.00,
    net_usdt: 109.67,
    score: 0.85,
    qty_btc: 0.089,
    timestamp: tsAt(2),
    status: 'PENDING',
  },
]

export const TRADES: Trade[] = [
  {
    id: 'trd-001',
    exchange_buy: 'Binance',
    exchange_sell: 'Kraken',
    qty_btc: 0.10,
    price_buy: 67_382.50,
    price_sell: 67_638.42,
    gross_usdt: 255.92,
    fee_total_usdt: 74.83,
    slippage_usdt: 12.40,
    net_usdt: 168.69,
    fill_ratio: 1.0,
    timestamp: tsAt(12),
    status: 'EXECUTED',
  },
  {
    id: 'trd-002',
    exchange_buy: 'Kraken',
    exchange_sell: 'Coinbase',
    qty_btc: 0.058,
    price_buy: 67_355.20,
    price_sell: 67_507.32,
    gross_usdt: 88.16,
    fee_total_usdt: 32.00,
    slippage_usdt: 9.10,
    net_usdt: 47.06,
    fill_ratio: 1.0,
    timestamp: tsAt(24),
    status: 'EXECUTED',
  },
  {
    id: 'trd-003',
    exchange_buy: 'Binance',
    exchange_sell: 'Coinbase',
    qty_btc: 0.089,
    price_buy: 67_391.10,
    price_sell: 67_599.38,
    gross_usdt: 186.11,
    fee_total_usdt: 53.45,
    slippage_usdt: 10.20,
    net_usdt: 122.46,
    fill_ratio: 0.97,
    timestamp: tsAt(48),
    status: 'EXECUTED',
  },
  {
    id: 'trd-004',
    exchange_buy: 'Kraken',
    exchange_sell: 'Binance',
    qty_btc: 0.107,
    price_buy: 67_368.90,
    price_sell: 67_490.22,
    gross_usdt: 121.32,
    fee_total_usdt: 35.30,
    slippage_usdt: 7.40,
    net_usdt: 78.62,
    fill_ratio: 1.0,
    timestamp: tsAt(61),
    status: 'EXECUTED',
  },
  {
    id: 'trd-005',
    exchange_buy: 'Coinbase',
    exchange_sell: 'Kraken',
    qty_btc: 0.086,
    price_buy: 67_344.75,
    price_sell: 67_519.93,
    gross_usdt: 150.83,
    fee_total_usdt: 43.60,
    slippage_usdt: 9.80,
    net_usdt: 97.43,
    fill_ratio: 0.93,
    timestamp: tsAt(85),
    status: 'EXECUTED',
  },
  {
    id: 'trd-006',
    exchange_buy: 'Kraken',
    exchange_sell: 'Coinbase',
    qty_btc: 0.09,
    price_buy: 67_378.40,
    price_sell: 67_600.50,
    gross_usdt: 198.45,
    fee_total_usdt: 56.90,
    slippage_usdt: 11.60,
    net_usdt: 129.95,
    fill_ratio: 1.0,
    timestamp: tsAt(112),
    status: 'EXECUTED',
  },
  {
    id: 'trd-007',
    exchange_buy: 'Binance',
    exchange_sell: 'Kraken',
    qty_btc: 0.089,
    price_buy: 67_362.80,
    price_sell: 67_558.52,
    gross_usdt: 174.52,
    fee_total_usdt: 50.30,
    slippage_usdt: 10.40,
    net_usdt: 113.82,
    fill_ratio: 0.95,
    timestamp: tsAt(140),
    status: 'EXECUTED',
  },
  {
    id: 'trd-008',
    exchange_buy: 'Coinbase',
    exchange_sell: 'Binance',
    qty_btc: 0.09,
    price_buy: 67_338.60,
    price_sell: 67_479.80,
    gross_usdt: 127.20,
    fee_total_usdt: 37.10,
    slippage_usdt: 8.70,
    net_usdt: 81.40,
    fill_ratio: 1.0,
    timestamp: tsAt(168),
    status: 'EXECUTED',
  },
  {
    id: 'trd-009',
    exchange_buy: 'Kraken',
    exchange_sell: 'Coinbase',
    qty_btc: 0.09,
    price_buy: 67_372.20,
    price_sell: 67_599.80,
    gross_usdt: 204.32,
    fee_total_usdt: 58.60,
    slippage_usdt: 12.10,
    net_usdt: 133.62,
    fill_ratio: 1.0,
    timestamp: tsAt(195),
    status: 'EXECUTED',
  },
  {
    id: 'trd-010',
    exchange_buy: 'Coinbase',
    exchange_sell: 'Kraken',
    qty_btc: 0.10,
    price_buy: 67_325.40,
    price_sell: 67_399.54,
    gross_usdt: 74.14,
    fee_total_usdt: 22.50,
    slippage_usdt: 7.00,
    net_usdt: 44.64,
    fill_ratio: 0.88,
    timestamp: tsAt(210),
    status: 'PARTIAL_FILL',
  },
  {
    id: 'trd-011',
    exchange_buy: 'Kraken',
    exchange_sell: 'Binance',
    qty_btc: 0.09,
    price_buy: 67_348.10,
    price_sell: 67_512.82,
    gross_usdt: 144.72,
    fee_total_usdt: 41.70,
    slippage_usdt: 9.30,
    net_usdt: 93.72,
    fill_ratio: 1.0,
    timestamp: tsAt(238),
    status: 'EXECUTED',
  },
  {
    id: 'trd-012',
    exchange_buy: 'Binance',
    exchange_sell: 'Coinbase',
    qty_btc: 0.06,
    price_buy: 67_405.30,
    price_sell: 67_457.70,
    gross_usdt: 31.44,
    fee_total_usdt: 18.20,
    slippage_usdt: 6.10,
    net_usdt: 7.14,
    fill_ratio: 0.72,
    timestamp: tsAt(252),
    status: 'PARTIAL_FILL',
  },
  {
    id: 'trd-013',
    exchange_buy: 'Kraken',
    exchange_sell: 'Coinbase',
    qty_btc: 0.15,
    price_buy: 67_332.80,
    price_sell: 67_539.26,
    gross_usdt: 309.69,
    fee_total_usdt: 81.40,
    slippage_usdt: 15.30,
    net_usdt: 212.99,
    fill_ratio: 1.0,
    timestamp: tsAt(270),
    status: 'EXECUTED',
  },
  {
    id: 'trd-014',
    exchange_buy: 'Coinbase',
    exchange_sell: 'Binance',
    qty_btc: 0.08,
    price_buy: 67_358.90,
    price_sell: 67_458.24,
    gross_usdt: 79.47,
    fee_total_usdt: 30.10,
    slippage_usdt: 7.80,
    net_usdt: 41.57,
    fill_ratio: 0.91,
    timestamp: tsAt(289),
    status: 'EXECUTED',
  },
  {
    id: 'trd-015',
    exchange_buy: 'Binance',
    exchange_sell: 'Kraken',
    qty_btc: 0.12,
    price_buy: 67_320.60,
    price_sell: 67_495.32,
    gross_usdt: 209.66,
    fee_total_usdt: 55.10,
    slippage_usdt: 11.90,
    net_usdt: 142.66,
    fill_ratio: 1.0,
    timestamp: tsAt(305),
    status: 'EXECUTED',
  },
  {
    id: 'trd-016',
    exchange_buy: 'Kraken',
    exchange_sell: 'Binance',
    qty_btc: 0.075,
    price_buy: 67_388.20,
    price_sell: 67_496.54,
    gross_usdt: 81.25,
    fee_total_usdt: 26.70,
    slippage_usdt: 7.50,
    net_usdt: 47.05,
    fill_ratio: 0.97,
    timestamp: tsAt(322),
    status: 'EXECUTED',
  },
  {
    id: 'trd-017',
    exchange_buy: 'Coinbase',
    exchange_sell: 'Kraken',
    qty_btc: 0.11,
    price_buy: 67_310.50,
    price_sell: 67_498.92,
    gross_usdt: 207.72,
    fee_total_usdt: 54.50,
    slippage_usdt: 12.40,
    net_usdt: 140.82,
    fill_ratio: 1.0,
    timestamp: tsAt(340),
    status: 'EXECUTED',
  },
  {
    id: 'trd-018',
    exchange_buy: 'Binance',
    exchange_sell: 'Coinbase',
    qty_btc: 0.04,
    price_buy: 67_418.70,
    price_sell: 67_451.10,
    gross_usdt: 12.96,
    fee_total_usdt: 9.80,
    slippage_usdt: 5.20,
    net_usdt: 3.24,
    fill_ratio: 0.70,
    timestamp: tsAt(358),
    status: 'PARTIAL_FILL',
  },
  {
    id: 'trd-019',
    exchange_buy: 'Kraken',
    exchange_sell: 'Coinbase',
    qty_btc: 0.13,
    price_buy: 67_298.40,
    price_sell: 67_499.08,
    gross_usdt: 260.89,
    fee_total_usdt: 68.50,
    slippage_usdt: 13.70,
    net_usdt: 178.69,
    fill_ratio: 1.0,
    timestamp: tsAt(375),
    status: 'EXECUTED',
  },
  {
    id: 'trd-020',
    exchange_buy: 'Coinbase',
    exchange_sell: 'Binance',
    qty_btc: 0.09,
    price_buy: 67_365.00,
    price_sell: 67_498.20,
    gross_usdt: 119.88,
    fee_total_usdt: 38.40,
    slippage_usdt: 8.40,
    net_usdt: 73.08,
    fill_ratio: 0.94,
    timestamp: tsAt(393),
    status: 'EXECUTED',
  },
]

// 100 P&L points over 8 hours, cumulative curve from 0 to ~847
export const PNL_SERIES: PnlPoint[] = (() => {
  const eightHoursMs = 8 * 60 * 60 * 1000
  const startMs = NOW_MS - eightHoursMs
  const points: PnlPoint[] = []
  const totalPoints = 100
  let cumulative = 0

  // Net P&Ls from trades spread across 8h for realistic curve
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

    // Interpolate between checkpoints
    while (
      checkIdx < checkpoints.length - 2 &&
      frac > checkpoints[checkIdx + 1][0]
    ) {
      checkIdx++
    }
    const [f0, v0] = checkpoints[checkIdx]
    const [f1, v1] = checkpoints[Math.min(checkIdx + 1, checkpoints.length - 1)]
    const t = f1 === f0 ? 1 : (frac - f0) / (f1 - f0)
    // Small noise for realism
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
  exchanges_connected: ['Binance', 'Kraken', 'Coinbase'],
}
