'use client'

import { useState } from 'react'
import { Header } from '@/components/header'
import { MetricCards } from '@/components/metric-cards'
import { PnlChart } from '@/components/pnl-chart'
import { OpportunitiesTable } from '@/components/opportunities-table'
import { TradesTable } from '@/components/trades-table'
import { ZscorePanel } from '@/components/zscore-panel'
import { CircuitBreakerPanel } from '@/components/circuit-breaker-panel'
import { METRICS, OPPORTUNITIES, PNL_SERIES, TRADES } from '@/lib/mock-data'
import type { Metrics } from '@/lib/mock-data'
import { Separator } from '@/components/ui/separator'
import { useArbitrageData } from '@/hooks/useArbitrageData'
import { useMetrics } from '@/hooks/useMetrics'

export default function Page() {
  const ws = useArbitrageData()
  const rest = useMetrics()

  // Live CB state: WS broadcast takes priority over polled REST
  const [cbOverride, setCbOverride] = useState<'OPEN' | 'CLOSED' | null>(null)

  // Priority: WS live data > REST polled data > mock fallback
  const opportunities =
    ws.connected && ws.opportunities.length > 0
      ? ws.opportunities
      : rest.opportunities.length > 0
        ? rest.opportunities
        : OPPORTUNITIES

  const trades =
    ws.connected && ws.trades.length > 0
      ? ws.trades
      : rest.trades.length > 0
        ? rest.trades
        : TRADES

  const pnlSeries =
    ws.connected && ws.pnlPoints.length > 0 ? ws.pnlPoints : PNL_SERIES

  const baseMetrics = rest.metrics ?? METRICS

  // CB state: manual override > WS event > REST poll > mock
  const cbState: Metrics['circuit_breaker'] =
    cbOverride ?? ws.circuitBreaker ?? baseMetrics.circuit_breaker

  const metrics: Metrics = { ...baseMetrics, circuit_breaker: cbState }

  return (
    <div className="flex flex-col min-h-screen">
      <Header metrics={metrics} latestLatencyMs={ws.latestLatencyMs} />

      <main className="flex-1 px-4 md:px-8 py-6 space-y-6">
        <MetricCards metrics={metrics} />

        {/* P&L chart + Z-score side by side */}
        <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wide mb-3">
              Cumulative P&amp;L — last 8 hours
            </h2>
            <div className="rounded-lg border border-white/10 bg-gray-900 p-4">
              <PnlChart data={pnlSeries} />
            </div>
          </div>

          <div>
            <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wide mb-3">
              Statistical Arbitrage
            </h2>
            <ZscorePanel data={ws.zScore} />
          </div>
        </section>

        {/* Circuit breaker controls */}
        <CircuitBreakerPanel
          state={cbState}
          onStateChange={setCbOverride}
        />

        <Separator className="bg-white/10" />

        <section>
          <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wide mb-3">
            Opportunities detected — last 20
          </h2>
          <OpportunitiesTable opportunities={opportunities} />
        </section>

        <Separator className="bg-white/10" />

        <section>
          <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wide mb-3">
            Trades executed — last 20
          </h2>
          <TradesTable trades={trades} />
        </section>
      </main>
    </div>
  )
}
