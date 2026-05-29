'use client'

import { useEffect, useRef } from 'react'
import type { Metrics } from '@/lib/mock-data'

interface PriceTickerProps {
  metrics: Metrics
  btcPrices: Record<string, number>
  priceHistory: Record<string, number[]>
  latestLatencyMs?: number | null
  connected: boolean
  oppsPerMin?: number
  presentationMode?: boolean
  onTogglePresentation?: () => void
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
  oppsPerMin,
  presentationMode = false,
  onTogglePresentation,
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

      {/* Right side: opps/min + latency + active indicator */}
      <div className="flex items-center gap-3 flex-shrink-0 ml-2">
        {oppsPerMin != null && (
          <div
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-mono"
            style={{ background: '#0d1117', borderColor: '#1f2937', color: oppsPerMin > 0 ? '#a78bfa' : '#4b5563' }}
          >
            <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: oppsPerMin > 0 ? '#a78bfa' : '#4b5563' }} />
            <span>{oppsPerMin} opps/min</span>
          </div>
        )}
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

        {onTogglePresentation && (
          <button
            onClick={onTogglePresentation}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[10px] font-semibold uppercase tracking-widest transition-colors"
            style={{
              background: presentationMode ? 'rgba(99,102,241,0.20)' : '#0d1117',
              borderColor: presentationMode ? '#6366f1' : '#374151',
              color: presentationMode ? '#a5b4fc' : '#6b7280',
            }}
            title="Toggle presentation mode (P)"
          >
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              {presentationMode
                ? <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                : <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23-.693L5 14.5m14.8.8l1.402 1.402c1 1 .03 2.798-1.414 2.798H4.213c-1.444 0-2.414-1.799-1.414-2.798L4.2 15.3" />
              }
            </svg>
            {presentationMode ? 'Exit' : 'Present'}
          </button>
        )}
      </div>
    </div>
  )
}
