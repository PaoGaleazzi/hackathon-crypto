'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { Sidebar } from '@/components/sidebar'
import { PriceTicker } from '@/components/price-ticker'
import { MetricCards } from '@/components/metric-cards'
import { SpreadChart } from '@/components/spread-chart'
import { OpportunitiesTable } from '@/components/opportunities-table'
import { TradesTable } from '@/components/trades-table'
import { ZscorePanel } from '@/components/zscore-panel'
import { TriangularPanel } from '@/components/triangular-panel'
import { GrossNetPanel } from '@/components/gross-net-panel'
import { RebalanceStatus } from '@/components/rebalance-status'
import { CircuitBreakerPanel } from '@/components/circuit-breaker-panel'
import { WalletBalances } from '@/components/wallet-balances'
import { LatencyWaterfall } from '@/components/latency-waterfall'
import { METRICS, OPPORTUNITIES, PNL_SERIES, TRADES, SPREAD_CANDLES } from '@/lib/mock-data'
import type { Metrics } from '@/lib/mock-data'
import { useArbitrageData } from '@/hooks/useArbitrageData'
import { useMetrics } from '@/hooks/useMetrics'
import { useTriangular } from '@/hooks/useTriangular'
import { Separator } from '@/components/ui/separator'

export default function Page() {
  const ws = useArbitrageData()
  const rest = useMetrics()
  const triangularOpps = useTriangular()
  const [activeView, setActiveView] = useState('dashboard')
  const [cbOverride, setCbOverride] = useState<'OPEN' | 'CLOSED' | null>(null)
  const [presentationMode, setPresentationMode] = useState(false)

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== 'p' && e.key !== 'P') return
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      setPresentationMode(prev => !prev)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Track opps/min: record arrival time each time ws.opportunities[0] changes
  const oppArrivalsRef = useRef<number[]>([])
  const prevFirstIdRef = useRef<string | undefined>(undefined)
  const [oppsPerMin, setOppsPerMin] = useState(0)

  const firstOppId = ws.opportunities[0]?.id
  useEffect(() => {
    if (firstOppId && firstOppId !== prevFirstIdRef.current) {
      prevFirstIdRef.current = firstOppId
      oppArrivalsRef.current.push(Date.now())
    }
  }, [firstOppId])

  useEffect(() => {
    const id = setInterval(() => {
      const cutoff = Date.now() - 60_000
      oppArrivalsRef.current = oppArrivalsRef.current.filter(t => t >= cutoff)
      setOppsPerMin(oppArrivalsRef.current.length)
    }, 1000)
    return () => clearInterval(id)
  }, [])

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

  const spreadData = ws.spreadCandles.length > 0 ? ws.spreadCandles : SPREAD_CANDLES

  const baseMetrics = rest.metrics ?? METRICS
  const cbState = cbOverride ?? ws.circuitBreaker ?? baseMetrics.circuit_breaker
  const metrics: Metrics = { ...baseMetrics, circuit_breaker: cbState }

  const btcPrices = useMemo(() => {
    const prices: Record<string, number> = {}
    for (const opp of opportunities) {
      const buy = opp.buy_exchange.toLowerCase()
      const sell = opp.sell_exchange.toLowerCase()
      if (!(buy in prices)) prices[buy] = opp.buy_ask
      if (!(sell in prices)) prices[sell] = opp.sell_bid
    }
    Object.assign(prices, ws.btcPrices)
    return prices
  }, [opportunities, ws.btcPrices])

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: '#0a0e1a' }}>
      {!presentationMode && (
        <Sidebar
          activeView={activeView}
          onNavigate={setActiveView}
          circuitBreaker={cbState}
          botActive={metrics.bot_active}
        />
      )}

      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <PriceTicker
          metrics={metrics}
          btcPrices={btcPrices}
          priceHistory={ws.priceHistory}
          latestLatencyMs={ws.latestLatencyMs}
          connected={ws.connected}
          oppsPerMin={oppsPerMin}
          presentationMode={presentationMode}
          onTogglePresentation={() => setPresentationMode(prev => !prev)}
        />

        <main className="flex-1 overflow-y-auto p-6">
          {/* Presentation mode — clean focused layout */}
          {presentationMode && (
            <div className="space-y-6">
              <MetricCards metrics={metrics} large />

              <div
                className="rounded-xl border p-4"
                style={{ background: '#111827', borderColor: '#1f2937' }}
              >
                <SpreadChart spreadData={spreadData} pnlData={pnlSeries} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <ZscorePanel data={ws.zScore} history={ws.zScoreHistory} />
                <LatencyWaterfall
                  stages={rest.latencyStages}
                  p50_ms={rest.latencyP50Ms}
                  p95_ms={rest.latencyP95Ms}
                  sampleCount={rest.latencySampleCount}
                />
              </div>
            </div>
          )}

          {/* Dashboard view */}
          {!presentationMode && activeView === 'dashboard' && (
            <div className="space-y-6">
              <MetricCards metrics={metrics} />

              {/* Spread chart (candlestick + P&L) */}
              <div
                className="rounded-xl border p-4"
                style={{ background: '#111827', borderColor: '#1f2937' }}
              >
                <SpreadChart spreadData={spreadData} pnlData={pnlSeries} />
              </div>

              {/* Z-score + Triangular */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <ZscorePanel data={ws.zScore} history={ws.zScoreHistory} />
                <TriangularPanel opportunities={triangularOpps} />
              </div>

              {/* Gross vs Net filter panel */}
              <GrossNetPanel opportunities={opportunities} />

              {/* Wallets */}
              <div
                className="rounded-xl border p-4"
                style={{ background: '#111827', borderColor: '#1f2937' }}
              >
                <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-3">
                  Wallet Balances
                </h3>
                <WalletBalances trades={trades} />
              </div>

              {/* Rebalance status */}
              <RebalanceStatus trades={trades} />
            </div>
          )}

          {/* Opportunities view */}
          {!presentationMode && activeView === 'opportunities' && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-white">Opportunities</h2>
              <OpportunitiesTable opportunities={opportunities} />
              <Separator className="bg-white/10" />
              <section>
                <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wide mb-3">
                  Triangular Arbitrage
                </h2>
                <TriangularPanel opportunities={triangularOpps} />
              </section>
            </div>
          )}

          {/* Trades view */}
          {!presentationMode && activeView === 'trades' && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-white">Executed Trades</h2>
              <TradesTable trades={trades} />
            </div>
          )}

          {/* Analytics view */}
          {!presentationMode && activeView === 'analytics' && (
            <div className="space-y-6">
              <h2 className="text-lg font-semibold text-white">Analytics</h2>
              <LatencyWaterfall
                stages={rest.latencyStages}
                p50_ms={rest.latencyP50Ms}
                p95_ms={rest.latencyP95Ms}
                sampleCount={rest.latencySampleCount}
              />
              <CircuitBreakerPanel state={cbState} onStateChange={setCbOverride} />
            </div>
          )}

          {/* Settings view */}
          {!presentationMode && activeView === 'settings' && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-white">Configuration</h2>
              <div
                className="rounded-xl border p-6"
                style={{ background: '#111827', borderColor: '#1f2937' }}
              >
                <dl className="grid grid-cols-2 gap-4">
                  {(
                    [
                      ['Min Profit Threshold', '$1.00 USDT'],
                      ['Min Fill Ratio', '0.30'],
                      ['Stale Quote Timeout', '500ms'],
                      ['CB Loss Threshold', '0.05%'],
                      ['CB Cooldown', '30s'],
                      ['Min Trade Size', '0.001 BTC'],
                      ['Demo Mode', 'Active'],
                      ['Exchanges', 'Binance, Kraken, Coinbase, OKX'],
                    ] as [string, string][]
                  ).map(([k, v]) => (
                    <div key={k} className="col-span-1">
                      <dt className="text-xs text-gray-600 uppercase tracking-wide">{k}</dt>
                      <dd className="text-sm font-mono text-gray-200 mt-0.5">{v}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
