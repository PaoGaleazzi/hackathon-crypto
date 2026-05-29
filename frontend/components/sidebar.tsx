'use client'

import {
  LayoutDashboard,
  TrendingUp,
  ArrowLeftRight,
  BarChart3,
  Settings,
  Zap,
} from 'lucide-react'

interface SidebarProps {
  activeView: string
  onNavigate: (view: string) => void
  circuitBreaker: 'OPEN' | 'CLOSED' | null
  botActive: boolean
}

const NAV_ITEMS = [
  { id: 'dashboard',     label: 'Dashboard',      Icon: LayoutDashboard },
  { id: 'opportunities', label: 'Opportunities',   Icon: TrendingUp },
  { id: 'trades',        label: 'Trades',          Icon: ArrowLeftRight },
  { id: 'analytics',    label: 'Analytics',       Icon: BarChart3 },
  { id: 'settings',     label: 'Settings',        Icon: Settings },
]

export function Sidebar({ activeView, onNavigate, circuitBreaker, botActive }: SidebarProps) {
  const cbOpen = circuitBreaker === 'OPEN'

  return (
    <aside
      className="flex flex-col flex-shrink-0 w-56 h-full border-r"
      style={{ background: '#0d1117', borderColor: '#1f2937' }}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 border-b" style={{ borderColor: '#1f2937' }}>
        <div
          className="flex items-center justify-center w-9 h-9 rounded-lg flex-shrink-0"
          style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)' }}
        >
          <Zap className="w-5 h-5 text-white" />
        </div>
        <div>
          <p className="text-sm font-bold text-white tracking-wide">ARB BOT</p>
          <p className="text-[10px] text-gray-500 leading-tight">BTC Multi-Exchange</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {NAV_ITEMS.map(({ id, label, Icon }) => {
          const isActive = activeView === id
          return (
            <button
              key={id}
              onClick={() => onNavigate(id)}
              className="relative flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm transition-colors text-left"
              style={
                isActive
                  ? { background: 'rgba(99,102,241,0.12)', color: '#a5b4fc' }
                  : undefined
              }
              onMouseEnter={e => {
                if (!isActive) {
                  ;(e.currentTarget as HTMLButtonElement).style.color = '#d1d5db'
                  ;(e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.05)'
                }
              }}
              onMouseLeave={e => {
                if (!isActive) {
                  ;(e.currentTarget as HTMLButtonElement).style.color = ''
                  ;(e.currentTarget as HTMLButtonElement).style.background = ''
                }
              }}
            >
              {isActive && (
                <span
                  className="absolute left-2 top-1/2 -translate-y-1/2 w-1 h-1 rounded-full"
                  style={{ background: '#818cf8' }}
                />
              )}
              <Icon
                className="w-4 h-4 flex-shrink-0"
                style={isActive ? { color: '#818cf8' } : { color: '#6b7280' }}
              />
              <span style={isActive ? {} : { color: '#6b7280' }}>{label}</span>
            </button>
          )
        })}
      </nav>

      {/* Footer indicators */}
      <div className="px-4 py-4 border-t space-y-2" style={{ borderColor: '#1f2937' }}>
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-wide text-gray-600">Bot status</span>
          <span
            className="flex items-center gap-1.5 text-[10px] font-medium"
            style={{ color: botActive ? '#4ade80' : '#6b7280' }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: botActive ? '#4ade80' : '#6b7280' }}
            />
            {botActive ? 'ACTIVE' : 'INACTIVE'}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-wide text-gray-600">Circuit breaker</span>
          <span
            className="flex items-center gap-1.5 text-[10px] font-medium"
            style={{ color: cbOpen ? '#f87171' : '#4ade80' }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: cbOpen ? '#f87171' : '#4ade80' }}
            />
            {cbOpen ? 'OPEN' : 'CLOSED'}
          </span>
        </div>
      </div>
    </aside>
  )
}
