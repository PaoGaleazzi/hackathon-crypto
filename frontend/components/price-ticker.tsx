'use client'

import { useEffect, useRef } from 'react'
import type { Metrics } from '@/lib/mock-data'

interface PriceTickerProps {
  metrics: Metrics
  btcPrices: Record<string, number>
  priceHistory: Record<string, number[]>
  latestLatencyMs?: number | null
  connected: boolean
}

function Sparkline({ history, positive }: { history: number[]; positive: boolean }) {
  if (history.length < 2) {
    return <svg width={64} height={28} />
  }

  const min = Math.min(...history)
  const max = Math.max(...history)
  const range = max - min || 1

  const points = history
    .map((v, i) => {
      const x = (i / (history.length - 1)) * 60 + 2
      const y = 26 - ((v - min) / range) * 22
      return `${x},${y}`
    })
    .join(' ')

  const color = positive ? '#4ade80' : '#f87171'

  return (
    <svg width={64} height={28} className="overflow-visible">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity={0.85}
      />
    </svg>
  )
}

function latencyColor(ms: number | null | undefined): string {
  if (ms == null) return '#6b7280'
  if (ms < 50) return '#4ade80'
  if (ms < 150) return '#fbbf24'
  return '#f87171'
}

const EXCHANGE_LABELS: Record<string, string> = {
  binance: 'Binance',
  kraken: 'Kraken',
  coinbase: 'Coinbase',
  okx: 'OKX',
}

export function PriceTicker({
  metrics,
  btcPrices,
  priceHistory,
  latestLatencyMs,
  connected,
}: PriceTickerProps) {
  // Track previous prices to determine up/down tick
  const prevPricesRef = useRef<Record<string, number>>({})
  const tickDirectionRef = useRef<Record<string, 'up' | 'down' | 'flat'>>({})

  useEffect(() => {
    const next: Record<string, 'up' | 'down' | 'flat'> = {}
    for (const [ex, price] of Object.entries(btcPrices)) {
      const prev = prevPricesRef.current[ex]
      if (prev == null) {
        next[ex] = 'flat'
      } else if (price > prev) {
        next[ex] = 'up'
      } else if (price < prev) {
        next[ex] = 'down'
      } else {
        next[ex] = 'flat'
      }
    }
    tickDirectionRef.current = next
    prevPricesRef.current = { ...btcPrices }
  })

  const exchanges = metrics.exchanges_connected

  return (
    <div
      className="flex items-center gap-3 px-6 py-3 border-b flex-shrink-0 overflow-x-auto"
      style={{ background: '#080c16', borderColor: '#1f2937' }}
    >
      <span className="hidden sm:block text-[10px] uppercase tracking-widest text-gray-600 flex-shrink-0 mr-2">
        Live Prices
      </span>

      <div className="flex items-center gap-3 flex-1">
        {exchanges.map(ex => {
          const exKey = ex.toLowerCase()
          const price = btcPrices[exKey]
          const history = priceHistory[exKey] ?? []
          const dir = tickDirectionRef.current[exKey] ?? 'flat'

          const priceColor =
            dir === 'up' ? '#4ade80' : dir === 'down' ? '#f87171' : '#e5e7eb'

          const firstPrice = history[0]
          const lastPrice = history[history.length - 1]
          let pctChange: number | null = null
          if (firstPrice && lastPrice && firstPrice > 0) {
            pctChange = ((lastPrice - firstPrice) / firstPrice) * 100
          }
          const pctPositive = pctChange == null ? true : pctChange >= 0
          const pctColor = pctPositive ? '#4ade80' : '#f87171'

          return (
            <div
              key={exKey}
              className="flex items-center gap-2 px-3 py-2 rounded-xl border flex-shrink-0"
              style={{ background: '#111827', borderColor: '#1f2937' }}
            >
              <div>
                <p className="text-[10px] uppercase tracking-wide text-gray-500 leading-none mb-1">
                  {EXCHANGE_LABELS[exKey] ?? ex}
                </p>
                {price != null ? (
                  <p className="text-sm font-mono font-semibold leading-none" style={{ color: priceColor }}>
                    ${price.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                  </p>
                ) : (
                  <p className="text-sm font-mono text-gray-600 leading-none">—</p>
                )}
                {pctChange != null && (
                  <p className="text-[10px] font-mono mt-0.5" style={{ color: pctColor }}>
                    {pctChange >= 0 ? '+' : ''}{pctChange.toFixed(2)}%
                  </p>
                )}
              </div>
              <Sparkline history={history} positive={pctPositive} />
            </div>
          )
        })}
      </div>

      {/* Right side: latency + active indicator */}
      <div className="flex items-center gap-3 flex-shrink-0 ml-2">
        {latestLatencyMs != null && (
          <div
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-mono"
            style={{ background: '#0d1117', borderColor: '#1f2937', color: latencyColor(latestLatencyMs) }}
          >
            <span>{latestLatencyMs.toFixed(1)}ms</span>
          </div>
        )}
        <div
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[10px] font-medium uppercase tracking-wide"
          style={{
            background: '#0d1117',
            borderColor: connected ? 'rgba(74,222,128,0.25)' : '#1f2937',
            color: connected ? '#4ade80' : '#6b7280',
          }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: connected ? '#4ade80' : '#6b7280' }}
          />
          {connected ? 'Active' : 'Inactive'}
        </div>
      </div>
    </div>
  )
}
