import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  TrendingUp,
  Search,
  BarChart2,
  Zap,
} from 'lucide-react'
import { type Metrics } from '@/lib/mock-data'

interface MetricCardsProps {
  metrics: Metrics
}

function formatCurrency(value: number): string {
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function latencyColor(ms: number): string {
  if (ms < 100) return 'text-green-400'
  if (ms < 500) return 'text-yellow-400'
  return 'text-red-400'
}

export function MetricCards({ metrics }: MetricCardsProps) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <Card className="bg-gray-900 border-white/10">
        <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
          <CardTitle className="text-xs font-medium text-gray-400 uppercase tracking-wide">
            Total P&amp;L
          </CardTitle>
          <TrendingUp className="h-4 w-4 text-gray-500" />
        </CardHeader>
        <CardContent>
          <div
            className={`text-2xl font-bold ${
              metrics.total_pnl_usdt >= 0 ? 'text-green-400' : 'text-red-400'
            }`}
          >
            {formatCurrency(metrics.total_pnl_usdt)}
          </div>
          <p className="text-xs text-gray-500 mt-1">Cumulative net profit</p>
        </CardContent>
      </Card>

      <Card className="bg-gray-900 border-white/10">
        <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
          <CardTitle className="text-xs font-medium text-gray-400 uppercase tracking-wide">
            Opportunities Today
          </CardTitle>
          <Search className="h-4 w-4 text-gray-500" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-white">
            {metrics.opportunities_today.toLocaleString('en-US')}
          </div>
          <p className="text-xs text-gray-500 mt-1">Detected today</p>
        </CardContent>
      </Card>

      <Card className="bg-gray-900 border-white/10">
        <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
          <CardTitle className="text-xs font-medium text-gray-400 uppercase tracking-wide">
            Best Spread
          </CardTitle>
          <BarChart2 className="h-4 w-4 text-gray-500" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-white">
            {metrics.best_spread_pct.toFixed(2)}%
          </div>
          <p className="text-xs text-gray-500 mt-1">Maximum spread seen</p>
        </CardContent>
      </Card>

      <Card className="bg-gray-900 border-white/10">
        <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
          <CardTitle className="text-xs font-medium text-gray-400 uppercase tracking-wide">
            Latency p95
          </CardTitle>
          <Zap className="h-4 w-4 text-gray-500" />
        </CardHeader>
        <CardContent>
          <div className={`text-2xl font-bold ${latencyColor(metrics.p95_latency_ms)}`}>
            {metrics.p95_latency_ms.toLocaleString('en-US')}
            <span className="text-sm font-normal ml-1">ms</span>
          </div>
          <p className="text-xs text-gray-500 mt-1">95th percentile</p>
        </CardContent>
      </Card>
    </div>
  )
}
