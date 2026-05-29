'use client'

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { type TriangularOpportunity } from '@/hooks/useTriangular'

export interface TriangularPanelProps {
  opportunities: TriangularOpportunity[]
}

function capitalize(s: string): string {
  if (!s) return s
  return s.charAt(0).toUpperCase() + s.slice(1)
}

function formatUsd(value: number): string {
  const abs = Math.abs(value)
  const str = abs.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return value < 0 ? `-$${str}` : `$${str}`
}

function getBuyExchange(opp: TriangularOpportunity): string {
  const leg = opp.legs.find(l => l.action === 'BUY')
  return leg?.exchange ? capitalize(leg.exchange) : '—'
}

function getSellExchange(opp: TriangularOpportunity): string {
  const leg = opp.legs.find(l => l.action === 'SELL')
  return leg?.exchange ? capitalize(leg.exchange) : '—'
}

export function TriangularPanel({ opportunities }: TriangularPanelProps) {
  if (opportunities.length === 0) {
    return (
      <div className="rounded-lg border border-white/10 bg-gray-900">
        <p className="text-gray-500 text-sm text-center py-6">
          No triangular opportunities — monitoring 42 pairs
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-white/10 bg-gray-900 overflow-hidden">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="border-white/10 hover:bg-transparent">
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide">
                Triangle
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide">
                Buy on
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide">
                Sell on
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">
                Profit %
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">
                Net P&amp;L
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">
                Withdrawal
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {opportunities.map((opp) => {
              const isProfit = opp.net_profit > 0
              return (
                <TableRow
                  key={opp.path}
                  className={
                    isProfit
                      ? 'border-white/5 bg-green-500/[0.07]'
                      : 'border-white/5 hover:bg-white/5 transition-colors'
                  }
                >
                  <TableCell className="font-mono text-sm text-gray-200 whitespace-nowrap">
                    {opp.path}
                  </TableCell>
                  <TableCell className="text-sm text-gray-300 whitespace-nowrap">
                    {getBuyExchange(opp)}
                  </TableCell>
                  <TableCell className="text-sm text-gray-300 whitespace-nowrap">
                    {getSellExchange(opp)}
                  </TableCell>
                  <TableCell
                    className={`text-sm text-right font-mono ${
                      opp.net_profit_pct >= 0 ? 'text-green-400' : 'text-red-400'
                    }`}
                  >
                    {opp.net_profit_pct.toFixed(4)}%
                  </TableCell>
                  <TableCell
                    className={`text-sm text-right font-mono font-semibold ${
                      isProfit ? 'text-green-400' : 'text-red-400'
                    }`}
                  >
                    {formatUsd(opp.net_profit)}
                  </TableCell>
                  <TableCell className="text-sm text-right font-mono text-gray-500">
                    {formatUsd(opp.withdrawal_cost)}
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
