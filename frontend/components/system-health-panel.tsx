'use client'

import type { SystemHealth } from '@/hooks/useSystemHealth'

interface SystemHealthPanelProps {
  health: SystemHealth
  tradesExecuted: number
  p50Ms: number
}

const EXCHANGE_LABELS: Record<string, string> = {
  binance:  'Binance',
  kraken:   'Kraken',
  coinbase: 'Coinbase',
  okx:      'OKX',
  bybit:    'Bybit',
  bitstamp: 'Bitstamp',
  gemini:   'Gemini',
}

const LIQ_COLORS: Record<string, { text: string; dot: string }> = {
  HEALTHY:  { text: '#4ade80', dot: '#22c55e' },
  DEGRADED: { text: '#fbbf24', dot: '#f59e0b' },
  UNKNOWN:  { text: '#6b7280', dot: '#374151' },
}

function formatUptime(s: number): string {
  if (s <= 0) return '—'
  if (s < 60) return `${Math.floor(s)}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${Math.floor(s % 60)}s`
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
}

export function SystemHealthPanel({ health, tradesExecuted, p50Ms }: SystemHealthPanelProps) {
  return (
    <div
      className="rounded-xl border p-4"
      style={{ background: '#111827', borderColor: '#1f2937' }}
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide">
          System Health
        </h3>
        <span className="text-[10px] font-mono text-gray-600 border rounded px-1.5 py-0.5" style={{ borderColor: '#1f2937' }}>
          5s poll
        </span>
      </div>

      {/* Exchange rows */}
      <div className="space-y-1.5 mb-3">
        {health.exchanges.map(ex => {
          const liqKey = ex.liquidityStatus ?? 'UNKNOWN'
          const liqColor = LIQ_COLORS[liqKey] ?? LIQ_COLORS.UNKNOWN
          return (
            <div
              key={ex.key}
              className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs"
              style={{ background: '#0d1117' }}
            >
              {/* Exchange name */}
              <span className="w-16 font-medium text-gray-300 flex-shrink-0">
                {EXCHANGE_LABELS[ex.key] ?? ex.key}
              </span>

              {/* WS status */}
              <span className="flex items-center gap-1 flex-shrink-0">
                <span
                  className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                  style={{ background: ex.connected ? '#22c55e' : '#ef4444' }}
                />
                <span
                  className="font-mono text-[10px] w-14"
                  style={{ color: ex.connected ? '#4ade80' : '#f87171' }}
                >
                  {ex.connected ? 'LIVE' : 'OFFLINE'}
                </span>
              </span>

              {/* Depth / liquidity */}
              <span className="flex items-center gap-1.5 ml-auto">
                {ex.liquidityStatus ? (
                  <>
                    <span
                      className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                      style={{ background: liqColor.dot }}
                    />
                    <span className="font-mono text-[10px]" style={{ color: liqColor.text }}>
                      {ex.liquidityStatus}
                    </span>
                    {ex.levelCount != null && (
                      <span className="text-[10px] text-gray-600">
                        ({ex.levelCount} lvl)
                      </span>
                    )}
                  </>
                ) : (
                  <span className="text-[10px] text-gray-700 font-mono">no depth</span>
                )}
              </span>
            </div>
          )
        })}
      </div>

      {/* Footer stats */}
      <div
        className="grid grid-cols-2 gap-2 pt-3 border-t"
        style={{ borderColor: '#1f2937' }}
      >
        <div>
          <p className="text-[10px] uppercase tracking-wide text-gray-600 mb-0.5">Uptime</p>
          <p className="text-xs font-mono text-gray-300">{formatUptime(health.uptimeS)}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-gray-600 mb-0.5">Trades hoy</p>
          <p className="text-xs font-mono text-gray-300">{tradesExecuted}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-gray-600 mb-0.5">Depth feeds</p>
          <p className="text-xs font-mono text-gray-300">
            {health.depthWithData}/{health.exchanges.length}
          </p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-gray-600 mb-0.5">Latencia p50</p>
          <p
            className="text-xs font-mono"
            style={{ color: p50Ms < 50 ? '#4ade80' : p50Ms < 150 ? '#fbbf24' : '#f87171' }}
          >
            {p50Ms > 0 ? `${p50Ms.toFixed(1)}ms` : '—'}
          </p>
        </div>
      </div>
    </div>
  )
}
