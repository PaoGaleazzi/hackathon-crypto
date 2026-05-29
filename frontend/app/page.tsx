'use client'

import { useMemo, useState } from 'react'
import { Header } from '@/components/header'
import { MetricCards } from '@/components/metric-cards'
import { PnlChart } from '@/components/pnl-chart'
import { OpportunitiesTable } from '@/components/opportunities-table'
import { TradesTable } from '@/components/trades-table'
import { ZscorePanel } from '@/components/zscore-panel'
import { CircuitBreakerPanel } from '@/components/circuit-breaker-panel'
import { WalletBalances } from '@/components/wallet-balances'
import { LatencyWaterfall } from '@/components/latency-waterfall'
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

  // Derive latest BTC price per exchange from most recent opportunity involving each exchange
  const btcPrices = useMemo(() => {
    const prices: Record<string, number> = {}
    // Iterate newest-first so the first hit per exchange wins
    for (const opp of opportunities) {
      const buy = opp.buy_exchange.toLowerCase()
      const sell = opp.sell_exchange.toLowerCase()
      if (!(buy in prices)) prices[buy] = opp.buy_ask
      if (!(sell in prices)) prices[sell] = opp.sell_bid
    }
    // Real-time WS prices override REST-derived prices
    Object.assign(prices, ws.btcPrices)
    return prices
  }, [opportunities, ws.btcPrices])

  return (
    <div className="flex flex-col min-h-screen">
      <Header metrics={metrics} latestLatencyMs={ws.latestLatencyMs} btcPrices={btcPrices} />

      <main className="flex-1 px-4 md:px-8 py-6 space-y-6">
        <MetricCards metrics={metrics} />

        {/* Pipeline latency breakdown */}
        <LatencyWaterfall
          stages={rest.latencyStages}
          p50_ms={rest.latencyP50Ms}
          p95_ms={rest.latencyP95Ms}
          sampleCount={rest.latencySampleCount}
        />

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
            <ZscorePanel data={ws.zScore} history={ws.zScoreHistory} />
          </div>
        </section>

        {/* Circuit breaker controls */}
        <CircuitBreakerPanel
          state={cbState}
          onStateChange={setCbOverride}
        />

        {/* Wallet balances */}
        <section>
          <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wide mb-3">
            Wallet Balances — simulated
          </h2>
          <WalletBalances trades={trades} />
        </section>

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
