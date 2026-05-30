'use client'

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  useFunding,
  type CashCarryOpportunity,
  type CrossExchangeOpportunity,
  type FundingRate,
} from '@/hooks/useFunding'

// The three perpetual venues the backend poller covers, in a fixed display order.
const VENUES = ['binance', 'bybit', 'okx'] as const

function capitalize(s: string): string {
  if (!s) return s
  return s.charAt(0).toUpperCase() + s.slice(1)
}

// Backend rates/returns are fractions (0.0005 = 0.05%). Render as percentages.
function pct(frac: number, decimals = 2, signed = false): string {
  const value = frac * 100
  const sign = signed && value > 0 ? '+' : ''
  return `${sign}${value.toFixed(decimals)}%`
}

function humanizeDirection(direction: string): string {
  if (direction === 'long_spot_short_perp') return 'Long spot / Short perp'
  if (direction === 'short_spot_long_perp') return 'Short spot / Long perp'
  return direction
}

function FundingRateCard({ name, rate }: { name: string; rate: FundingRate | undefined }) {
  if (!rate) {
    return (
      <div className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
        <div className="text-sm font-medium text-gray-300">{capitalize(name)}</div>
        <div className="mt-2 text-xs text-gray-600">No feed</div>
      </div>
    )
  }

  const positive = rate.rate >= 0
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-300">{capitalize(name)}</span>
        <span className="font-mono text-[10px] text-gray-600">{rate.symbol}</span>
      </div>
      <div className={`mt-1 font-mono text-xl font-bold ${positive ? 'text-green-400' : 'text-red-400'}`}>
        {pct(rate.rate, 4, true)}
      </div>
      <div className="mt-0.5 text-xs text-gray-500">
        <span className="text-gray-600">8h ·</span>{' '}
        <span className={`font-mono ${positive ? 'text-green-400/80' : 'text-red-400/80'}`}>
          {pct(rate.annualized_rate, 1, true)} APR
        </span>
      </div>
    </div>
  )
}

function CrossExchangeTable({ opps }: { opps: CrossExchangeOpportunity[] }) {
  if (opps.length === 0) {
    return <p className="py-3 text-center text-xs text-gray-600">No cross-exchange funding spreads</p>
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-white/10">
      <Table>
        <TableHeader>
          <TableRow className="border-white/10 hover:bg-transparent">
            <TableHead className="text-xs uppercase tracking-wide text-gray-400">Long / Short</TableHead>
            <TableHead className="text-right text-xs uppercase tracking-wide text-gray-400">Spread</TableHead>
            <TableHead className="text-right text-xs uppercase tracking-wide text-gray-400">Annualized</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {opps.map((o) => (
            <TableRow
              key={`${o.long_exchange}-${o.short_exchange}`}
              className={o.profitable ? 'border-white/5 bg-green-500/[0.07]' : 'border-white/5 hover:bg-white/5 transition-colors'}
            >
              <TableCell className="whitespace-nowrap text-sm text-gray-200">
                <span className="text-green-400">{capitalize(o.long_exchange)}</span>
                <span className="text-gray-600"> / </span>
                <span className="text-red-400">{capitalize(o.short_exchange)}</span>
              </TableCell>
              <TableCell className="text-right font-mono text-sm text-gray-300">{pct(o.funding_spread, 4)}</TableCell>
              <TableCell className={`text-right font-mono text-sm font-semibold ${o.annualized_return >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {pct(o.annualized_return, 1, true)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function CashCarryTable({ opps }: { opps: CashCarryOpportunity[] }) {
  if (opps.length === 0) {
    return <p className="py-3 text-center text-xs text-gray-600">No cash-and-carry opportunities</p>
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-white/10">
      <Table>
        <TableHeader>
          <TableRow className="border-white/10 hover:bg-transparent">
            <TableHead className="text-xs uppercase tracking-wide text-gray-400">Exchange</TableHead>
            <TableHead className="text-xs uppercase tracking-wide text-gray-400">Direction</TableHead>
            <TableHead className="text-right text-xs uppercase tracking-wide text-gray-400">Annualized</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {opps.map((o) => (
            <TableRow
              key={o.exchange}
              className={o.profitable ? 'border-white/5 bg-green-500/[0.07]' : 'border-white/5 hover:bg-white/5 transition-colors'}
            >
              <TableCell className="whitespace-nowrap text-sm text-gray-200">{capitalize(o.exchange)}</TableCell>
              <TableCell className="whitespace-nowrap text-sm text-gray-400">{humanizeDirection(o.direction)}</TableCell>
              <TableCell className={`text-right font-mono text-sm font-semibold ${o.annualized_return >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {pct(o.annualized_return, 1, true)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

export function FundingPanel() {
  const data = useFunding()

  if (data === null) {
    return (
      <div className="rounded-lg border border-white/10 bg-gray-900 p-4">
        <h3 className="mb-3 text-sm font-medium uppercase tracking-wide text-gray-400">
          Funding Arbitrage
        </h3>
        <div className="flex flex-col items-center justify-center gap-2 py-10">
          <div className="h-2 w-2 animate-pulse rounded-full bg-gray-600" />
          <span className="text-xs text-gray-600">Waiting for funding data…</span>
        </div>
      </div>
    )
  }

  const best = data.best_annualized_return
  const bestPositive = best !== null && best > 0

  return (
    <div className="space-y-4 rounded-lg border border-white/10 bg-gray-900 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium uppercase tracking-wide text-gray-400">
          Funding Arbitrage
        </h3>
        <span className="text-xs text-gray-600">BTC perpetuals · 10s</span>
      </div>

      {/* Best annualized return — headline */}
      <div
        className={`rounded-lg border p-4 ${
          bestPositive ? 'border-green-500/40 bg-green-500/10' : 'border-white/10 bg-white/[0.02]'
        }`}
      >
        <div className="text-xs uppercase tracking-wide text-gray-400">Best Annualized Return</div>
        <div
          className={`mt-1 font-mono text-4xl font-bold ${
            best === null ? 'text-gray-600' : bestPositive ? 'text-green-400' : 'text-red-400'
          }`}
        >
          {best === null ? '—' : pct(best, 1, true)}
        </div>
        <div className="mt-1 text-xs text-gray-500">
          {bestPositive
            ? 'Net-positive carry available after fees'
            : 'No net-positive carry — fees exceed the edge'}
        </div>
      </div>

      {/* Live funding rates */}
      <div>
        <div className="mb-2 text-xs uppercase tracking-wide text-gray-500">Live Funding Rates</div>
        <div className="grid grid-cols-3 gap-2">
          {VENUES.map((venue) => (
            <FundingRateCard key={venue} name={venue} rate={data.funding_rates[venue]} />
          ))}
        </div>
      </div>

      {/* Cross-exchange funding */}
      <div>
        <div className="mb-2 text-xs uppercase tracking-wide text-gray-500">Cross-Exchange Funding</div>
        <CrossExchangeTable opps={data.cross_exchange} />
      </div>

      {/* Cash-and-carry */}
      <div>
        <div className="mb-2 text-xs uppercase tracking-wide text-gray-500">Cash &amp; Carry</div>
        <CashCarryTable opps={data.cash_and_carry} />
      </div>
    </div>
  )
}
