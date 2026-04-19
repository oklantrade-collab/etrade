'use client'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { logoutUser } from '@/lib/api-client'
import toast from 'react-hot-toast'
import { useState, useEffect } from 'react'


export default function Sidebar({ isOpen, onClose }: { isOpen?: boolean, onClose?: () => void }) {
  const pathname = usePathname()
  const [forexConnected, setForexConnected] = useState(false)

  useEffect(() => {
    fetch('/api/v1/forex/status')
      .then(r => r.json())
      .then(d => setForexConnected(d.connected))
  }, [])

  const sections = [
    {
      title: 'GLOBAL',
      items: [
        { href: '/portfolio', icon: '🏠', label: 'Portfolio' },
      ],
    },
    {
      title: 'CRYPTO',
      items: [
        { href: '/dashboard',   icon: '📊', label: 'Command Center' },
        { href: '/strategies',  icon: '🧠', label: 'Strategies' },
        { href: '/market',      icon: '📈', label: 'Market' },
        { href: '/performance', icon: '🏆', label: 'Performance' },
        { href: '/signals',     icon: '📡', label: 'Signals' },
        { href: '/positions',   icon: '📂', label: 'Positions' },
        { href: '/orders',      icon: '📋', label: 'Orders' },
        { href: '/backtesting', icon: '🔬', label: 'Backtesting' },
        { href: '/risk',        icon: '🛡️', label: 'Risk' },
      ],
    },
    {
      title: 'FOREX',
      items: [
        { href: '/forex/dashboard', icon: '📊', label: 'Command Center', disabled: !forexConnected },
        { href: '/forex/strategies', icon: '🧠', label: 'Strategies', disabled: !forexConnected },
        { href: '/forex/market', icon: '📈', label: 'Market', disabled: !forexConnected },
        { href: '/forex/signals', icon: '⚡', label: 'Signals', disabled: !forexConnected },
        { href: '/forex/positions', icon: '📋', label: 'Positions', disabled: !forexConnected },
        { href: '/forex/orders', icon: '📝', label: 'Orders', disabled: !forexConnected },
      ],
    },
    {
      title: 'BOLSA (Sprint 5)',
      items: [
        { href: '/stocks/dashboard',   icon: '📊', label: 'Command Center' },
        { href: '/stocks/universe',    icon: '🔍', label: 'Universe' },
        { href: '/stocks/opportunities', icon: '💡', label: 'Opportunities' },
        { href: '/stocks/positions',   icon: '📋', label: 'Positions' },
        { href: '/stocks/orders',      icon: '🎫', label: 'Orders' },
        { href: '/stocks/strategies',  icon: '🧠', label: 'Strategies' },
        { href: '/stocks/journal',     icon: '📓', label: 'Journal' },
        { href: '/stocks/performance', icon: '📈', label: 'Performance' },
        { href: '/stocks/backtesting', icon: '🔬', label: 'Backtesting' },
      ],
    },
    {
      title: 'OPCIONES (Sprint 10+)',
      items: [
        { href: '/options', icon: '🎯', label: 'Options Dashboard' },
      ],
    },
    {
      title: 'SISTEMA',
      items: [
        { href: '/settings', icon: '⚙️', label: 'Settings' },
        { href: '/logs',     icon: '📋', label: 'System Logs' },
      ],
    },
  ]

  return (
    <aside className={`sidebar overflow-y-auto ${isOpen ? 'mobile-open' : ''}`}>
      <div className="sidebar-logo flex items-center justify-between">
        <div>
          <h1 className="text-xl font-black italic tracking-tighter">eTrader</h1>
          <span className="text-[0.6rem] uppercase tracking-widest font-bold text-slate-500">Multimarket v4.5</span>
        </div>
        {onClose && (
          <button onClick={onClose} className="md:hidden p-2 text-slate-400 hover:text-white">
            ✕
          </button>
        )}
      </div>
      
      <nav className="sidebar-nav pt-4 pb-10">
        {sections.map((section, sidx) => (
          <div key={sidx} className="mb-6">
            <h3 className="px-5 mb-2 text-[0.6rem] font-black text-slate-500 uppercase tracking-[0.2em]">
              {section.title}
            </h3>
            <div className={`space-y-0.5 ${section.disabled ? 'opacity-40 cursor-not-allowed' : ''}`}>
              {section.items.map((item: any) => {
                const isDisabled = section.disabled || item.disabled;
                return (
                  <Link
                    key={item.href}
                    href={isDisabled ? '#' : item.href}
                    onClick={() => { if (onClose) onClose(); }}
                    title={section.disabled ? section.tooltip : (item.disabled ? 'Conectar IC Markets para activar' : '')}
                    className={`nav-link ${pathname === item.href ? 'active' : ''} ${isDisabled ? 'pointer-events-none opacity-50 grayscale' : ''}`}
                  >
                    <span className="nav-icon opacity-70">{item.icon}</span>
                    <span className="font-semibold">{item.label}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="mt-auto border-t border-slate-800 p-5 bg-slate-900/40">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[0.65rem] font-bold text-slate-400 uppercase tracking-widest">
              System Live
            </span>
          </div>
        </div>
        
        <button 
          onClick={async () => {
            try {
              await logoutUser()
              toast.success('Sesión cerrada')
              window.location.href = '/login'
            } catch (err) {
              window.location.href = '/login'
            }
          }}
          className="w-full py-2.5 rounded-lg border border-rose-500/20 bg-rose-500/5 hover:bg-rose-500 text-rose-500 hover:text-white text-[10px] font-black uppercase tracking-widest transition-all"
        >
          Cerrar Sesión
        </button>
      </div>
    </aside>
  )
}
