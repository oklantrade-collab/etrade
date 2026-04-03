'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { supabase } from '@/lib/supabase'

interface PerformanceMetric {
  pnl_usd: number
  trades: number
  win_rate: number
  pct_of_month?: number
  best_week?: { week_num: number; pnl_usd: number }
}

interface PerformanceSummary {
  today: PerformanceMetric
  this_week: PerformanceMetric
  this_month: PerformanceMetric
  weekly_breakdown: any[]
  by_market: any
}

interface PortfolioSymbol {
  symbol: string
  side: 'long' | 'short' | null
  avg_entry_price: number
  current_price: number
  unrealized_pnl_usd: number
  unrealized_pnl_pct: number
  tp_partial_price: number
  fibonacci_zone: number
  rule_code: string | null
  sl_price: number
  ai_sentiment: string
  status: string
  trades_count: number
  bars_held: number
  max_bars: number
}

interface GlobalPortfolioData {
  daily: {
    pnl_usd: number
    win_rate: number
    open_positions: number
    risk_global: string
  }
  markets: {
    crypto: {
      status: string
      regime: string
      symbols: PortfolioSymbol[]
      pnl_usd: number
      positions: number
    }
    forex: any
    stocks: any
  }
  recent_activity: any[]
}

export default function PortfolioPage() {
  const [perf, setPerf] = useState<PerformanceSummary | null>(null)
  const [global, setGlobal] = useState<GlobalPortfolioData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchData()

    const channel = supabase
      .channel('portfolio-realtime-v2')
      .on('postgres_changes', { 
        event: '*', 
        schema: 'public', 
        table: 'market_snapshot' 
      }, (payload) => {
        const newData = payload.new as any
        handleRealtimePrice(newData.symbol, newData)
      })
      .subscribe()

    return () => { supabase.removeChannel(channel) }
  }, [])

  async function fetchData() {
    try {
      const [pRes, gRes] = await Promise.all([
        fetch('/api/v1/portfolio/performance-summary'),
        fetch('/api/v1/portfolio/global')
      ])
      if (pRes.ok) setPerf(await pRes.json())
      if (gRes.ok) setGlobal(await gRes.json())
    } catch (err) {
      console.error("Portfolio load error:", err)
    } finally {
      setLoading(false)
    }
  }

  const handleRealtimePrice = (symbol: string, newData: any) => {
    setGlobal(prev => {
      if (!prev) return prev
      const newSymbols = prev.markets.crypto.symbols.map(s => {
        if (s.symbol === symbol) {
          const newPrice = parseFloat(newData.price || s.current_price)
          const pnlPct = s.side === 'long' 
            ? ((newPrice - s.avg_entry_price) / s.avg_entry_price) * 100
            : ((s.avg_entry_price - newPrice) / s.avg_entry_price) * 100
          
          return {
            ...s,
            current_price: newPrice,
            fibonacci_zone: parseInt(newData.fibonacci_zone ?? s.fibonacci_zone),
            unrealized_pnl_pct: pnlPct,
            // Simple PnL USD recalculation if we had size, but let's just keep the fetch one or approximate
            unrealized_pnl_usd: s.unrealized_pnl_usd * (pnlPct / (s.unrealized_pnl_pct || 1))
          }
        }
        return s
      })
      return {
        ...prev,
        markets: {
          ...prev.markets,
          crypto: { ...prev.markets.crypto, symbols: newSymbols }
        }
      }
    })
  }

  if (loading || !perf || !global) return <div className="p-10 text-slate-500 italic">Cargando Portfolio Global v2...</div>

  return (
    <div className="space-y-12 pb-20">
      {/* HEADER — eTrader v4 */}
      <div className="flex justify-between items-center bg-[#1A1A2E] border border-slate-800/50 p-6 rounded-2xl">
         <div className="flex items-center gap-4">
            <h1 className="text-3xl font-black italic tracking-tighter text-white">eTrader v4</h1>
            <div className="w-px h-6 bg-slate-800" />
            <span className="text-xs font-black text-blue-400 tracking-widest uppercase">📄 Paper Trading</span>
         </div>
         <div className="text-right">
            <span className="text-xs font-black text-slate-500 uppercase tracking-[0.2em]">
              {new Date().toLocaleDateString('en-US', { day: '2-digit', month: 'short', year: 'numeric' }).toUpperCase()}
            </span>
         </div>
      </div>

      {/* SECCIÓN 1 — Performance Metrics */}
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
           <PeriodCard title="HOY" data={perf.today} />
           <PeriodCard title="SEMANA" data={perf.this_week} />
           <PeriodCard title="MES" data={perf.this_month} isMonth />
        </div>

        <div>
          <h3 className="text-[0.65rem] font-black text-slate-500 uppercase tracking-[0.3em] mb-4">Desglose Semanal del Mes</h3>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-6">
            {perf.weekly_breakdown.map((w, i) => (
              <WeeklyCard key={i} data={w} isCurrent={w.week_num === 2} /> // Hardcoded S2 as current for demo or logic
            ))}
          </div>
        </div>

        <div>
          <h3 className="text-[0.65rem] font-black text-slate-500 uppercase tracking-[0.3em] mb-4">Desglose por Mercado (Mes Actual)</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
             <MarketCard 
               title="CRYPTO" 
               color="text-amber-500" 
               icon="🟡" 
               data={perf.by_market.crypto} 
               regime={global.markets.crypto.regime}
             />
             <MarketCard title="FOREX" color="text-slate-500" icon="⚫" data={perf.by_market.forex} />
             <MarketCard title="BOLSA" color="text-slate-500" icon="⚫" data={perf.by_market.stocks} />
          </div>
        </div>
      </div>

      {/* SECCIÓN 2 — Bloque Crypto */}
      <div className="card glass-effect !p-0 overflow-hidden border-amber-500/20 shadow-[0_0_40px_rgba(245,158,11,0.05)]">
         <div className="px-8 py-5 border-b border-slate-800/50 flex justify-between items-center bg-slate-900/40">
            <div className="flex items-center gap-3">
               <span className="text-xl">🟡</span>
               <h2 className="text-xl font-black tracking-tight italic">CRYPTO — Binance Futures/Spot</h2>
            </div>
            <Link href="/dashboard" className="btn btn-ghost !text-[0.65rem] font-black !px-4 hover:bg-slate-800/40 tracking-widest text-blue-400">
               VER DETALLE →
            </Link>
         </div>

         <div className="p-8 space-y-8">
            {/* Resumen Superior */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-8 border-b border-slate-800/30 pb-8 text-center md:text-left">
               <div>
                  <label className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest block mb-1">Símbolos</label>
                  <span className="text-sm font-bold font-mono">BTC ETH SOL ADA</span>
               </div>
               <div>
                  <label className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest block mb-1">Posiciones</label>
                  <span className="text-sm font-bold">{global.daily.open_positions} abiertas</span>
               </div>
               <div>
                  <label className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest block mb-1">P&L HOY</label>
                  <span className={`text-sm font-bold ${global.daily.pnl_usd >=0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                    {global.daily.pnl_usd >=0 ? '+' : ''}${global.daily.pnl_usd.toFixed(2)}
                  </span>
               </div>
               <div>
                  <label className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest block mb-1">Régimen</label>
                  <span className={`text-sm font-bold uppercase ${getRegimeTextColor(global.markets.crypto.regime)}`}>
                    {global.markets.crypto.regime.replace('_', ' ')}
                  </span>
               </div>
               <div>
                  <label className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest block mb-1">Sentimiento</label>
                  <span className="text-sm font-bold">NEUTRAL 😐</span>
               </div>
            </div>

            {/* Barra de Riesgo y Sentimiento */}
            <div className="flex flex-col md:flex-row gap-4">
               <div className={`flex-1 flex items-center justify-center gap-4 py-3 rounded-xl border border-white/5 ${getRegimeBg(global.markets.crypto.regime)}`}>
                  <span className="text-[0.65rem] font-black text-white/60 uppercase tracking-widest">Riesgo Mercado Crypto:</span>
                  <div className="flex items-center gap-2">
                     <div className={`w-2 h-2 rounded-full ${getRegimeColor(global.markets.crypto.regime)} animate-pulse`} />
                     <span className={`text-sm font-black uppercase tracking-tighter ${getRegimeTextColor(global.markets.crypto.regime)}`}>
                       {getRegimeLabel(global.markets.crypto.regime)} — ACTIVO
                     </span>
                  </div>
               </div>
               <div className="flex-1 flex items-center justify-center gap-4 py-3 rounded-xl border border-white/5 bg-slate-900/60">
                  <span className="text-[0.65rem] font-black text-white/60 uppercase tracking-widest">Sentimiento:</span>
                  <div className="flex items-center gap-2">
                     <span className="text-lg">😐</span>
                     <span className="text-sm font-black uppercase tracking-tighter text-slate-400">NEUTRAL</span>
                  </div>
               </div>
            </div>

            {/* Tabla de Posiciones Abiertas */}
            <div className="space-y-4">
               <h3 className="text-[0.65rem] font-black text-slate-500 uppercase tracking-[0.2em]">Posiciones Abiertas</h3>
               <div className="table-container !bg-transparent !p-0">
                  <table className="w-full text-left">
                     <thead>
                        <tr className="text-[0.6rem] text-slate-500 uppercase tracking-widest border-b border-slate-800/50">
                           <th className="pb-4">SÍMBOLO</th>
                           <th className="pb-4">ENTRADA</th>
                           <th className="pb-4">ÚLTIMO</th>
                           <th className="pb-4">P&L ($)</th>
                           <th className="pb-4 text-center">EST. CIERRE</th>
                           <th className="pb-4 text-center">% P&L</th>
                           <th className="pb-4 text-center">ZONA</th>
                           <th className="pb-4 text-right">ESTRAT.</th>
                        </tr>
                     </thead>
                     <tbody className="divide-y divide-slate-800/30">
                        {global.markets.crypto.symbols.filter(s => s.status === 'active').map(s => (
                           <tr key={s.symbol} className="hover:bg-white/5 transition-colors group">
                              <td className="py-5">
                                 <div className="flex items-center gap-2">
                                    <span className={`text-xs ${s.unrealized_pnl_pct >= 0 ? 'text-[#00C896]' : 'text-[#FF4757]'}`} style={{ fontWeight: 'bold' }}>
                                      {s.side === 'long' ? '▲' : '▼'}
                                    </span>
                                    <span className="font-black text-sm tracking-tighter">{s.symbol.replace('USDT','')}</span>
                                 </div>
                              </td>
                              <td className="font-mono text-xs text-slate-400">${s.avg_entry_price.toLocaleString()}</td>
                              <td className="font-mono text-xs text-white">${s.current_price.toLocaleString()}</td>
                              <td className={`font-mono text-xs font-bold ${s.unrealized_pnl_usd >=0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                                 {s.unrealized_pnl_usd >= 0 ? '+' : ''}${s.unrealized_pnl_usd.toFixed(2)}
                              </td>
                              <td className="text-center font-mono text-xs text-blue-400/80">${s.tp_partial_price.toLocaleString()}</td>
                              <td className={`text-center font-mono text-xs font-black ${s.unrealized_pnl_pct >=0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                                 {s.unrealized_pnl_pct >= 0 ? '+' : ''}{s.unrealized_pnl_pct.toFixed(2)}%
                              </td>
                              <td className="text-center">
                                 <span className={`text-[0.65rem] font-bold ${s.fibonacci_zone > 0 ? 'text-emerald-400' : s.fibonacci_zone < 0 ? 'text-rose-400' : 'text-slate-500'}`}>
                                    {s.fibonacci_zone > 0 ? `+${s.fibonacci_zone}` : s.fibonacci_zone}
                                 </span>
                              </td>
                              <td className="text-right">
                                 <span className="text-[0.65rem] font-mono text-slate-500 group-hover:text-blue-400 transition-colors uppercase">{s.rule_code}</span>
                              </td>
                           </tr>
                        ))}
                     </tbody>
                  </table>
               </div>
            </div>
         </div>
      </div>

      {/* Actividad Recientemente Cerrada */}
      <div className="card glass-effect !p-0 overflow-hidden opacity-80 border-slate-800/50">
         <div className="px-8 py-4 border-b border-slate-800/50 bg-slate-900/40">
            <h3 className="text-[0.65rem] font-black text-slate-500 uppercase tracking-widest">Actividad Reciente (Posiciones Cerradas)</h3>
         </div>
         <div className="table-container !bg-transparent !p-0">
            <table className="w-full text-left">
               <thead>
                  <tr className="text-[0.6rem] text-slate-500 uppercase tracking-widest border-b border-slate-800/50">
                     <th className="pb-4 px-8">Fecha / Hora</th>
                     <th className="pb-4">Simbolo</th>
                     <th className="pb-4">Dir</th>
                     <th className="pb-4 text-center">Estrategia</th>
                     <th className="pb-4">Motivo</th>
                     <th className="pb-4 text-right px-8">P&L ($)</th>
                  </tr>
               </thead>
               <tbody className="divide-y divide-slate-800/30">
                  {global.recent_activity.map((a, i) => (
                     <tr key={i} className="hover:bg-white/5 transition-colors group">
                        <td className="py-4 px-8">
                           <div className="text-[0.7rem] font-mono text-white font-bold">{new Date(a.time).toLocaleTimeString()}</div>
                           <div className="text-[0.55rem] font-mono text-slate-500">{new Date(a.time).toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' })}</div>
                        </td>
                        <td className="font-bold text-sm tracking-tighter">{a.symbol.replace('USDT', '')}</td>
                        <td>
                           <span className={`text-[0.65rem] font-black uppercase ${a.dir === 'long' ? 'text-emerald-500' : 'text-rose-500'}`}>{a.dir}</span>
                        </td>
                        <td className="text-center">
                           <span className="text-[0.65rem] font-mono text-blue-400 font-bold group-hover:text-blue-300 transition-colors uppercase tracking-widest">
                             {a.rule || '—'}
                           </span>
                        </td>
                        <td>
                           <span className="badge badge-blue text-[0.6rem] uppercase tracking-tighter font-bold">{a.status}</span>
                        </td>
                        <td className={`text-right px-8 font-mono font-bold text-xs ${a.pnl >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                           {a.pnl >= 0 ? '+' : ''}${a.pnl.toFixed(2)}
                        </td>
                     </tr>
                  ))}
               </tbody>
            </table>
         </div>
      </div>

      <style jsx>{`
        .glass-effect {
          background: rgba(26, 26, 46, 0.4);
          backdrop-filter: blur(20px);
          -webkit-backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 1.5rem;
        }
      `}</style>
    </div>
  )
}

function PeriodCard({ title, data, isMonth = false }: { title: string, data: PerformanceMetric, isMonth?: boolean }) {
  const isPositive = data.pnl_usd >= 0
  return (
    <div className="card glass-effect border-slate-800/50 p-8 hover:border-slate-700 transition-colors">
      <span className="text-[0.65rem] font-black text-slate-500 uppercase tracking-[.3em] block mb-6">{title}</span>
      <div className={`text-4xl font-black italic tracking-tighter mb-4 ${isPositive ? 'text-[#00C896]' : 'text-[#FF4757]'}`}>
        {isPositive ? '+' : ''}${data.pnl_usd.toFixed(2)}
      </div>
      <div className="space-y-2">
         <div className="flex justify-between text-[0.65rem] font-bold text-slate-400 uppercase tracking-widest">
            <span>Trades:</span>
            <span className="text-white">{data.trades} cerrados</span>
         </div>
         <div className="flex justify-between text-[0.65rem] font-bold text-slate-400 uppercase tracking-widest">
            <span>Win Rate:</span>
            <span className="text-indigo-400">{data.win_rate}%</span>
         </div>
         {isMonth && data.best_week ? (
            <div className="pt-4 border-t border-slate-800/50 mt-4">
               <span className="text-[0.6rem] text-slate-500 font-black uppercase block mb-1">Mejor Semana: S{data.best_week.week_num}</span>
               <span className="text-xs font-black text-emerald-400">${data.best_week.pnl_usd.toFixed(2)}</span>
            </div>
         ) : (
            <div className="flex justify-between text-[0.65rem] font-bold text-slate-400 uppercase tracking-widest">
               <span>% del Mes:</span>
               <span className="text-blue-400">{data.pct_of_month}%</span>
            </div>
         )}
      </div>
    </div>
  )
}

function WeeklyCard({ data, isCurrent }: { data: any, isCurrent: boolean }) {
  const isPositive = data.pnl_usd >= 0
  return (
    <div className={`p-6 rounded-2xl border transition-all ${isCurrent ? 'bg-amber-500/5 border-amber-500/40 shadow-[0_0_20px_rgba(245,158,11,0.1)]' : 'bg-slate-900/40 border-slate-800/50'}`}>
      <span className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest block mb-4">SEMANA {data.week_num}</span>
      <div className={`text-xl font-black tracking-tight mb-3 ${isPositive ? 'text-emerald-500' : 'text-rose-500'}`}>
        {isPositive ? '+' : ''}${data.pnl_usd.toFixed(2)}
      </div>
      <div className="grid grid-cols-2 gap-y-2 text-[0.6rem] font-bold text-slate-400 uppercase tracking-tighter">
         <span>{data.trades} trades</span>
         <span className="text-right">WR: {data.win_rate}%</span>
         <span>{data.pct_of_month}% del mes</span>
      </div>
    </div>
  )
}

function MarketCard({ title, color, icon, data, regime }: { title: string, color: string, icon: string, data: any, regime?: string }) {
  const isActive = data.status === 'active'
  return (
    <div className={`card glass-effect border-slate-800/50 transition-all ${!isActive ? 'opacity-50 grayscale hover:grayscale-0 hover:opacity-100' : 'border-amber-500/20'}`}>
       <div className="flex justify-between items-center mb-6">
          <div className="flex items-center gap-2">
             <span className="text-lg">{isActive ? (regime?.includes('riesgo_medio') ? '🟡' : '🟢') : icon}</span>
             <span className={`text-sm font-black tracking-widest ${isActive ? 'text-white' : 'text-slate-500'}`}>{title}</span>
          </div>
          {isActive ? (
             <span className="badge badge-green text-[0.55rem] font-black tracking-widest">ACTIVE</span>
          ) : (
             <span className="text-[0.55rem] font-black text-slate-600 uppercase tracking-widest">Sprint {data.sprint}</span>
          )}
       </div>
       {isActive ? (
          <div className="space-y-2">
             <div className="flex justify-between text-[0.65rem] font-bold text-slate-400 uppercase tracking-widest">
                <span>P&L Mes:</span>
                <span className="text-emerald-400 font-mono">+${data.pnl_usd?.toFixed(2)}</span>
             </div>
             <div className="flex justify-between text-[0.65rem] font-bold text-slate-400 uppercase tracking-widest">
                <span>Trades:</span>
                <span>{data.trades} cerrados</span>
             </div>
             <div className="flex justify-between text-[0.65rem] font-bold text-slate-400 uppercase tracking-widest">
                <span>Win Rate:</span>
                <span>{data.win_rate}%</span>
             </div>
          </div>
       ) : (
          <div className="text-[0.6rem] text-slate-500 italic">
             Módulo en desarrollo para Sprint {data.sprint}.
          </div>
       )}
    </div>
  )
}

function getRegimeLabel(regime: string) {
  const r = regime?.toLowerCase() || ''
  if (r.includes('bajo') || r === 'low') return 'LOW'
  if (r.includes('medio') || r === 'medium') return 'MEDIUM'
  if (r.includes('alto') || r === 'high') return 'HIGH'
  return 'UNKNOWN'
}

function getRegimeBg(regime: string) {
  switch (regime) {
    case 'bajo_riesgo': return 'bg-emerald-500/10'
    case 'riesgo_medio': return 'bg-amber-500/10'
    case 'alto_riesgo': return 'bg-rose-500/10'
    default: return 'bg-slate-900/60'
  }
}

function getRegimeColor(regime: string) {
  switch (regime) {
    case 'bajo_riesgo': return 'bg-emerald-500'
    case 'riesgo_medio': return 'bg-amber-500'
    case 'alto_riesgo': return 'bg-rose-500'
    default: return 'bg-slate-600'
  }
}

function getRegimeTextColor(regime: string) {
  switch (regime) {
    case 'bajo_riesgo': return 'text-emerald-500'
    case 'riesgo_medio': return 'text-amber-500'
    case 'alto_riesgo': return 'text-rose-500'
    default: return 'text-slate-400'
  }
}
