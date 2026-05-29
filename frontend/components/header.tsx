import { Badge } from '@/components/ui/badge'
import { type Metrics } from '@/lib/mock-data'

interface HeaderProps {
  metrics: Metrics
  latestLatencyMs?: number | null
  btcPrices?: Record<string, number>
}

const EXCHANGE_LABELS: Record<string, string> = {
  binance: 'Binance',
  kraken: 'Kraken',
  coinbase: 'Coinbase',
  okx: 'OKX',
}

function latencyColor(ms: number): string {
  if (ms < 50)  return 'text-green-400'
  if (ms < 150) return 'text-yellow-400'
  return 'text-red-400'
}

function formatPrice(usd: number): string {
  return usd.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

export function Header({ metrics, latestLatencyMs, btcPrices = {} }: HeaderProps) {
  return (
    <header className="bg-gray-900 border-b border-white/10 px-4 md:px-8 py-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold tracking-tight text-white">
            BTC Arbitrage Bot
          </span>
          <div className="flex items-center gap-2">
            {metrics.exchanges_connected.map((exchange) => {
              const label = EXCHANGE_LABELS[exchange?.toLowerCase()] ?? exchange
              const price = btcPrices[exchange?.toLowerCase()]
              return (
                <div
                  key={exchange}
                  className="flex flex-col items-center px-2.5 py-1 rounded-lg bg-white/10 min-w-[72px]"
                >
                  <span className="text-xs font-medium text-gray-300 leading-tight">
                    {label}
                  </span>
                  {price != null ? (
                    <span className="text-xs font-mono font-semibold text-white leading-tight">
                      ${formatPrice(price)}
                    </span>
                  ) : (
                    <span className="text-xs font-mono text-gray-600 leading-tight">—</span>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {latestLatencyMs != null && (
            <div
              className={`flex items-center gap-1 px-2 py-1 rounded bg-white/5 text-xs font-mono ${latencyColor(latestLatencyMs)}`}
              title="Last trade round-trip latency"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
              {latestLatencyMs.toFixed(1)}ms
            </div>
          )}

          <span className="text-xs text-gray-400 uppercase tracking-wide">
            Circuit Breaker:
          </span>
          <Badge
            variant="outline"
            className={
              metrics.circuit_breaker === 'CLOSED'
                ? 'border-green-500/50 text-green-400'
                : 'border-red-500/50 text-red-400'
            }
          >
            {metrics.circuit_breaker}
          </Badge>

          <div
            className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium ${
              metrics.bot_active
                ? 'bg-green-500/10 text-green-400'
                : 'bg-red-500/10 text-red-400'
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                metrics.bot_active
                  ? 'bg-green-400 animate-pulse'
                  : 'bg-red-400'
              }`}
            />
            {metrics.bot_active ? 'ACTIVE' : 'INACTIVE'}
          </div>
        </div>
      </div>
    </header>
  )
}
