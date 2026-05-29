'use client'

import type { Trade } from '@/lib/mock-data'

interface Props {
  trades: Trade[]
}

const EXCHANGES = ['binance', 'kraken', 'coinbase', 'okx'] as const
const LABELS: Record<string, string> = {
  binance: 'Binance',
  kraken: 'Kraken',
  coinbase: 'Coinbase',
  okx: 'OKX',
}
const INITIAL_USDT = 10_000
const INITIAL_BTC = 0.5

interface ExchangeState {
  key: string
  label: string
  btc: number
  usdt: number
  btcDevPct: number
  usdtDevPct: number
  maxDevPct: number
  tier: 'green' | 'yellow' | 'red'
}

function computeState(trades: Trade[]): ExchangeState[] {
  const usdt: Record<string, number> = {}
  const btc: Record<string, number> = {}
  for (const ex of EXCHANGES) {
    usdt[ex] = INITIAL_USDT
    btc[ex] = INITIAL_BTC
  }
  for (const t of trades) {
    if (t.status !== 'EXECUTED') continue
    const buy = t.buy_exchange.toLowerCase()
    const sell = t.sell_exchange.toLowerCase()
    if (buy in usdt) {
      usdt[buy] -= t.buy_price * t.qty + t.fee_buy
      btc[buy] += t.qty
    }
    if (sell in btc) {
      btc[sell] -= t.qty
      usdt[sell] += t.sell_price * t.qty - t.fee_sell
    }
  }

  return EXCHANGES.map(ex => {
    const btcDev = ((btc[ex] - INITIAL_BTC) / INITIAL_BTC) * 100
    const usdtDev = ((usdt[ex] - INITIAL_USDT) / INITIAL_USDT) * 100
    const maxDev = Math.max(Math.abs(btcDev), Math.abs(usdtDev))
    const tier: ExchangeState['tier'] = maxDev >= 30 ? 'red' : maxDev >= 10 ? 'yellow' : 'green'
    return { key: ex, label: LABELS[ex], btc: btc[ex], usdt: usdt[ex], btcDevPct: btcDev, usdtDevPct: usdtDev, maxDevPct: maxDev, tier }
  })
}

const TIER_COLORS = {
  green:  { dot: '#22c55e', bg: '#0d1a12', border: '#14532d', text: '#4ade80', label: 'Balanced' },
  yellow: { dot: '#f59e0b', bg: '#1a1505', border: '#78350f', text: '#fbbf24', label: 'Attention' },
  red:    { dot: '#ef4444', bg: '#1a0d0d', border: '#7f1d1d', text: '#f87171', label: 'Rebalance' },
} as const

function DeviationBar({ pct, max = 40 }: { pct: number; max?: number }) {
  const clipped = Math.min(Math.abs(pct), max)
  const width = (clipped / max) * 50
  const isExcess = pct > 0
  return (
    <div className="flex items-center h-2 w-full gap-0.5">
      {/* Left half — deficit fills right-to-left */}
      <div className="flex-1 h-full rounded-l-full overflow-hidden flex justify-end" style={{ background: '#1f2937' }}>
        {!isExcess && (
          <div className="h-full rounded-l-full" style={{ width: `${width * 2}%`, background: '#ef4444' }} />
        )}
      </div>
      {/* Center tick */}
      <div className="w-px h-3 shrink-0" style={{ background: '#374151' }} />
      {/* Right half — excess fills left-to-right */}
      <div className="flex-1 h-full rounded-r-full overflow-hidden" style={{ background: '#1f2937' }}>
        {isExcess && (
          <div className="h-full rounded-r-full" style={{ width: `${width * 2}%`, background: '#f59e0b' }} />
        )}
      </div>
    </div>
  )
}

function DevLabel({ pct }: { pct: number }) {
  const sign = pct > 0 ? '+' : ''
  const color = pct > 0 ? '#f59e0b' : pct < 0 ? '#ef4444' : '#6b7280'
  return (
    <span className="text-xs font-mono font-semibold" style={{ color }}>
      {sign}{pct.toFixed(1)}%
    </span>
  )
}

export function RebalanceStatus({ trades }: Props) {
  const states = computeState(trades)
  const worstTier = states.some(s => s.tier === 'red')
    ? 'red'
    : states.some(s => s.tier === 'yellow')
    ? 'yellow'
    : 'green'
  const overallColors = TIER_COLORS[worstTier]
  const needCount = states.filter(s => s.tier !== 'green').length

  return (
    <div
      className="rounded-xl border p-5"
      style={{ background: '#111827', borderColor: '#1f2937' }}
    >
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wide">
          Rebalance Status
        </h3>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full" style={{ background: overallColors.dot }} />
          <span className="text-xs font-semibold" style={{ color: overallColors.text }}>
            {needCount === 0 ? 'All balanced' : `${needCount} exchange${needCount > 1 ? 's' : ''} need rebalancing`}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {states.map(s => {
          const c = TIER_COLORS[s.tier]
          return (
            <div
              key={s.key}
              className="rounded-lg border p-3"
              style={{ background: c.bg, borderColor: c.border }}
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-2.5">
                <span className="text-xs font-semibold text-gray-300">{s.label}</span>
                <div className="flex items-center gap-1.5">
                  <div className="w-1.5 h-1.5 rounded-full" style={{ background: c.dot }} />
                  <span className="text-[10px] font-semibold uppercase" style={{ color: c.text }}>
                    {c.label}
                  </span>
                </div>
              </div>

              {/* BTC row */}
              <div className="mb-2">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] text-gray-500 uppercase tracking-wide">BTC</span>
                  <DevLabel pct={s.btcDevPct} />
                </div>
                <DeviationBar pct={s.btcDevPct} />
                <div className="flex justify-between mt-0.5">
                  <span className="text-[10px] text-gray-600 font-mono">{s.btc.toFixed(4)}</span>
                  <span className="text-[10px] text-gray-600">
                    {s.btcDevPct > 0 ? '↑ excess' : s.btcDevPct < 0 ? '↓ deficit' : '—'}
                  </span>
                </div>
              </div>

              {/* USDT row */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] text-gray-500 uppercase tracking-wide">USDT</span>
                  <DevLabel pct={s.usdtDevPct} />
                </div>
                <DeviationBar pct={s.usdtDevPct} max={60} />
                <div className="flex justify-between mt-0.5">
                  <span className="text-[10px] text-gray-600 font-mono">
                    {s.usdt.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                  </span>
                  <span className="text-[10px] text-gray-600">
                    {s.usdtDevPct > 0 ? '↑ excess' : s.usdtDevPct < 0 ? '↓ deficit' : '—'}
                  </span>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-3 pt-3 border-t" style={{ borderColor: '#1f2937' }}>
        <span className="text-[10px] text-gray-600 uppercase tracking-wide">Target:</span>
        <span className="text-[10px] font-mono text-gray-500">BTC {INITIAL_BTC} / exchange</span>
        <span className="text-[10px] font-mono text-gray-500">USDT {INITIAL_USDT.toLocaleString()} / exchange</span>
        <div className="flex items-center gap-3 ml-auto">
          {(['green', 'yellow', 'red'] as const).map(t => (
            <div key={t} className="flex items-center gap-1">
              <div className="w-1.5 h-1.5 rounded-full" style={{ background: TIER_COLORS[t].dot }} />
              <span className="text-[10px] text-gray-600">
                {t === 'green' ? '<10%' : t === 'yellow' ? '10–30%' : '>30%'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
