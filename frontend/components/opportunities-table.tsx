'use client'

import { useEffect, useState } from 'react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { format, parseISO } from 'date-fns'
import { type Opportunity, type OpportunityStatus } from '@/lib/mock-data'

interface OpportunitiesTableProps {
  opportunities: Opportunity[]
}

const EXCHANGE_LABELS: Record<string, string> = {
  binance: 'Binance',
  kraken: 'Kraken',
  coinbase: 'Coinbase',
  okx: 'OKX',
}

const STATUS_STYLES: Record<OpportunityStatus, string> = {
  EXECUTED:             'bg-green-500/15 text-green-400 border-green-500/30',
  REJECTED_NEGATIVE_NET:'bg-red-500/15 text-red-400 border-red-500/30',
  ABORTED_STALE:        'bg-orange-500/15 text-orange-400 border-orange-500/30',
  PENDING:              'bg-blue-500/15 text-blue-400 border-blue-500/30',
}

const STATUS_LABELS: Record<OpportunityStatus, string> = {
  EXECUTED:             'Executed',
  REJECTED_NEGATIVE_NET:'Rejected',
  ABORTED_STALE:        'Stale',
  PENDING:              'Pending',
}

function spreadColor(pct: number): string {
  if (pct > 0.1) return 'text-green-400'
  if (pct >= 0.05) return 'text-yellow-400'
  return 'text-gray-400'
}

function netColor(value: number): string {
  return value >= 0 ? 'text-green-400' : 'text-red-400'
}

function formatUsd(value: number): string {
  const abs = Math.abs(value)
  const str = abs.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return value < 0 ? `-$${str}` : `$${str}`
}

function fmtEx(ex: string): string {
  return EXCHANGE_LABELS[ex?.toLowerCase()] ?? ex
}

function formatAge(detectedAt: string, now: number): string {
  const ms = now - new Date(detectedAt).getTime()
  if (ms < 0) return '0ms'
  if (ms < 1_000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1_000).toFixed(1)}s`
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m`
  return `${Math.floor(ms / 3_600_000)}h`
}

export function OpportunitiesTable({ opportunities }: OpportunitiesTableProps) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1_000)
    return () => clearInterval(id)
  }, [])

  const unique = Array.from(new Map(opportunities.map(o => [o.id, o])).values())
  const sorted = unique.sort(
    (a, b) => new Date(b.detected_at).getTime() - new Date(a.detected_at).getTime()
  )

  return (
    <div className="rounded-lg border border-white/10 overflow-hidden">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="border-white/10 hover:bg-transparent">
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide">Route</TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">Spread</TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">Gross</TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">Net</TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide">Score</TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">Qty BTC</TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">Time</TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">Age</TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((opp) => {
              const spreadPct = opp.buy_ask > 0
                ? (opp.sell_bid - opp.buy_ask) / opp.buy_ask * 100
                : 0
              const scoreWidth = Math.min(Math.max(opp.score * 100, 0), 100)

              return (
                <TableRow
                  key={opp.id}
                  className="border-white/5 hover:bg-white/5 transition-colors"
                >
                  <TableCell className="text-sm font-medium text-gray-200 whitespace-nowrap">
                    {fmtEx(opp.buy_exchange)}
                    <span className="text-gray-500 mx-1">→</span>
                    {fmtEx(opp.sell_exchange)}
                  </TableCell>
                  <TableCell className={`text-sm text-right font-mono ${spreadColor(spreadPct)}`}>
                    {spreadPct.toFixed(2)}%
                  </TableCell>
                  <TableCell className="text-sm text-right font-mono text-gray-300">
                    {formatUsd(opp.gross_spread)}
                  </TableCell>
                  <TableCell className={`text-sm text-right font-mono font-semibold ${netColor(opp.net_spread)}`}>
                    {formatUsd(opp.net_spread)}
                  </TableCell>
                  <TableCell className="min-w-[80px]">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full bg-blue-400"
                          style={{ width: `${scoreWidth}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-400 w-8 text-right">
                        {opp.score.toFixed(2)}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="text-sm text-right font-mono text-gray-300">
                    {opp.optimal_qty.toFixed(3)}
                  </TableCell>
                  <TableCell className="text-sm text-right font-mono text-gray-400 whitespace-nowrap">
                    {format(parseISO(opp.detected_at), 'HH:mm:ss')}
                  </TableCell>
                  <TableCell className="text-sm text-right font-mono text-gray-500 whitespace-nowrap">
                    {formatAge(opp.detected_at, now)}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className={`text-xs whitespace-nowrap ${STATUS_STYLES[opp.status]}`}
                    >
                      {STATUS_LABELS[opp.status]}
                    </Badge>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
