import { Badge } from '@/components/ui/badge'
import { type Metrics } from '@/lib/mock-data'

interface HeaderProps {
  metrics: Metrics
}

export function Header({ metrics }: HeaderProps) {
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

        <div className="flex items-center gap-2">
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
