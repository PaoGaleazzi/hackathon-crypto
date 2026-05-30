'use client'

import { useEffect, useState } from 'react'

export interface FundingRate {
  exchange: string
  symbol: string
  rate: number            // per 8h funding period, as a fraction (0.0005 = 0.05%)
  annualized_rate: number // rate * 3 * 365, as a fraction
  mark_price: number
  index_price: number
  next_funding_time: string
  timestamp: string
}

export interface CashCarryOpportunity {
  exchange: string
  symbol: string
  direction: string       // "long_spot_short_perp" | "short_spot_long_perp"
  funding_rate: number
  funding_capture: number
  total_fees: number
  net_after_fees: number
  annualized_return: number
  profitable: boolean
}

export interface CrossExchangeOpportunity {
  symbol: string
  long_exchange: string
  short_exchange: string
  funding_spread: number
  total_fees: number
  net_after_fees: number
  annualized_return: number
  profitable: boolean
}

export interface FundingData {
  funding_rates: Record<string, FundingRate>
  cash_and_carry: CashCarryOpportunity[]
  cross_exchange: CrossExchangeOpportunity[]
  best_annualized_return: number | null
}

const BASE = 'http://localhost:8000'
// Funding only updates every 8h and the backend poller refreshes every 10s, so
// matching that cadence here keeps the panel fresh without redundant requests.
const POLL_MS = 10_000

async function fetchFunding(): Promise<FundingData | null> {
  try {
    const res = await fetch(`${BASE}/api/funding`, { cache: 'no-store' })
    if (!res.ok) return null
    return (await res.json()) as FundingData
  } catch {
    return null
  }
}

export function useFunding(): FundingData | null {
  const [data, setData] = useState<FundingData | null>(null)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      const next = await fetchFunding()
      if (!cancelled && next !== null) setData(next)
    }

    void poll()
    const id = setInterval(() => { void poll() }, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  return data
}
