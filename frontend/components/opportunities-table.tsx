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

const STATUS_STYLES: Record<OpportunityStatus, string> = {
  EXECUTED: 'bg-green-500/15 text-green-400 border-green-500/30',
  REJECTED_NEGATIVE_NET: 'bg-red-500/15 text-red-400 border-red-500/30',
  ABORTED_STALE: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  PENDING: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
}

const STATUS_LABELS: Record<OpportunityStatus, string> = {
  EXECUTED: 'Executed',
  REJECTED_NEGATIVE_NET: 'Rejected',
  ABORTED_STALE: 'Stale',
  PENDING: 'Pending',
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
  const str = abs.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return value < 0 ? `-$${str}` : `$${str}`
}

export function OpportunitiesTable({ opportunities }: OpportunitiesTableProps) {
  const sorted = [...opportunities].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  )

  return (
    <div className="rounded-lg border border-white/10 overflow-hidden">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="border-white/10 hover:bg-transparent">
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide">
                Route
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">
                Spread
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">
                Gross
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">
                Net
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide">
                Score
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">
                Qty BTC
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">
                Time
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide">
                Status
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((opp) => (
              <TableRow
                key={opp.id}
                className="border-white/5 hover:bg-white/5 transition-colors"
              >
                <TableCell className="text-sm font-medium text-gray-200 whitespace-nowrap">
                  {opp.exchange_buy}{' '}
                  <span className="text-gray-500 mx-1">→</span>{' '}
                  {opp.exchange_sell}
                </TableCell>
                <TableCell className={`text-sm text-right font-mono ${spreadColor(opp.spread_pct)}`}>
                  {opp.spread_pct.toFixed(2)}%
                </TableCell>
                <TableCell className="text-sm text-right font-mono text-gray-300">
                  {formatUsd(opp.gross_usdt)}
                </TableCell>
                <TableCell className={`text-sm text-right font-mono font-semibold ${netColor(opp.net_usdt)}`}>
                  {formatUsd(opp.net_usdt)}
                </TableCell>
                <TableCell className="min-w-[80px]">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full bg-blue-400"
                        style={{ width: `${opp.score * 100}%` }}
                      />
                    </div>
                    <span className="text-xs text-gray-400 w-8 text-right">
                      {opp.score.toFixed(2)}
                    </span>
                  </div>
                </TableCell>
                <TableCell className="text-sm text-right font-mono text-gray-300">
                  {opp.qty_btc.toFixed(3)}
                </TableCell>
                <TableCell className="text-sm text-right font-mono text-gray-400 whitespace-nowrap">
                  {format(parseISO(opp.timestamp), 'HH:mm:ss')}
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
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
