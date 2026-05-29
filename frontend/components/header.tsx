import { Badge } from '@/components/ui/badge'
import { type Metrics } from '@/lib/mock-data'

interface HeaderProps {
  metrics: Metrics
  latestLatencyMs?: number | null
}

function latencyColor(ms: number): string {
  if (ms < 50)  return 'text-green-400'
  if (ms < 150) return 'text-yellow-400'
  return 'text-red-400'
}

export function Header({ metrics, latestLatencyMs }: HeaderProps) {
  return (
    <header className="bg-gray-900 border-b border-white/10 px-4 md:px-8 py-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold tracking-tight text-white">
            BTC Arbitrage Bot
          </span>
          <div className="flex items-center gap-1.5">
            {metrics.exchanges_connected.map((exchange) => (
              <span
                key={exchange}
                className="text-xs font-medium px-2 py-0.5 rounded-full bg-white/10 text-gray-300"
              >
                {exchange}
              </span>
            ))}
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
