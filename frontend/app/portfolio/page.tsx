'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { supabase } from '@/lib/supabase'

interface PerformanceMetric {
  pnl_usd: number
  trades: number
  win_rate: number
  pct_of_month?: number
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
  fibonacci_zone: number
  rule_code: string | null
  status: string
  total_investment: number
  quantity: number
}

interface GlobalPortfolioData {
  daily: { pnl_usd: number; open_positions: number }
  summary: { total_pnl_usd: number; avg_roi_pct: number }
  markets: {
    crypto: { symbols: PortfolioSymbol[]; regime: string }
    forex: { symbols: PortfolioSymbol[]; regime: string }
    stocks: { symbols: PortfolioSymbol[]; regime: string }
  }
  recent_activity: any[]
}

export default function PortfolioPage() {
  const [perf, setPerf] = useState<PerformanceSummary | null>(null)
  const [global, setGlobal] = useState<GlobalPortfolioData | null>(null)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(0)
  const ITEMS_PER_PAGE = 10
  const MAX_HISTORY = 100

  useEffect(() => {
    fetchData()
    const channel = supabase.channel('portfolio-final-v2').on('postgres_changes', { event: '*', schema: 'public', table: 'market_snapshot' }, (p) => fetchData()).subscribe()
    return () => { supabase.removeChannel(channel) }
  }, [])

  async function fetchData() {
    try {
      const [pRes, gRes] = await Promise.all([fetch('/api/v1/portfolio/performance-summary'), fetch('/api/v1/portfolio/global')])
      if (pRes.ok) setPerf(await pRes.json())
      if (gRes.ok) setGlobal(await gRes.json())
    } catch (err) { console.error(err) } finally { setLoading(false) }
  }

  if (loading || !perf || !global) return <div className="min-h-screen bg-[#020205] flex items-center justify-center text-blue-500 font-black uppercase tracking-widest text-[0.6rem] animate-pulse">Sincronizando Sistema...</div>

  const activeCrypto = global?.markets?.crypto?.symbols?.filter(s => s.status === 'active') || []
  const activeForex  = global?.markets?.forex?.symbols?.filter(s => s.status === 'active') || []
  const activeStocks = global?.markets?.stocks?.symbols?.filter(s => s.status === 'active') || []

  return (
    <div className="min-h-screen bg-[#020208] text-slate-200 pb-40 selection:bg-blue-500/30">
      <div className="absolute top-0 left-0 w-full h-[600px] bg-gradient-to-b from-blue-600/10 to-transparent pointer-events-none" />
      
      <div className="max-w-7xl mx-auto px-6 pt-12 space-y-16 relative z-10">
        
        {/* HEADER */}
        <header className="flex justify-between items-center glass-card border-white/5 !p-10 shadow-3xl">
           <div className="space-y-2">
              <h1 className="text-3xl font-black italic tracking-tighter text-white uppercase leading-none">eTrader Terminal</h1>
              <p className="text-[0.6rem] font-black text-slate-500 uppercase tracking-[0.5em] opacity-80">Dashboard de Control Multimercado</p>
           </div>
           <div className="flex items-center gap-6">
              <div className="text-right hidden md:block">
                 <div className="text-[0.5rem] font-black text-slate-600 uppercase tracking-widest leading-none mb-1">Status de Conexión</div>
                 <div className="text-emerald-400 font-black text-xs">EN LÍNEA / SEGURO</div>
              </div>
              <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_10px_#10b981] animate-pulse" />
           </div>
        </header>

        {/* PERFORMANCE GRID */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
           <PerfCard title="PNL HOY (CONSOLIDADO)" val={perf?.today?.pnl_usd || 0} trades={perf?.today?.trades || 0} wr={perf?.today?.win_rate || 0} color="blue" />
           <PerfCard title="PNL SEMANA (CERRADO)" val={perf?.this_week?.pnl_usd || 0} trades={perf?.this_week?.trades || 0} wr={perf?.this_week?.win_rate || 0} color="emerald" />
           <PerfCard title="PNL MES (TOTAL)" val={perf?.this_month?.pnl_usd || 0} trades={perf?.this_month?.trades || 0} wr={perf?.this_month?.win_rate || 0} color="indigo" />
        </div>

        {/* HISTORICO SEMANAL */}
        <div className="space-y-6">
           <h3 className="section-label pl-2">Rendimiento Histórico Semanal</h3>
           <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
               {(perf?.weekly_breakdown || []).map((w, i) => (
                 <div key={i} className="glass-card flex flex-col items-center justify-center p-8 text-center border-white/5 hover:border-white/10 transition-colors">
                    <span className="text-[0.55rem] font-black text-slate-500 uppercase tracking-widest mb-4">SEMANA {w?.week_num || i}</span>
                    <span className={`text-2xl font-black italic tracking-tighter ${(w?.pnl_usd || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {(w?.pnl_usd || 0) >= 0 ? '+' : ''}${(w?.pnl_usd || 0).toFixed(2)}
                    </span>
                    <div className="mt-4 pt-4 border-t border-white/5 w-full text-[0.5rem] font-black text-slate-500 uppercase">
                       {w?.trades || 0} Trades <span className="opacity-30 mx-1">|</span> {w?.win_rate || 0}% Win
                    </div>
                 </div>
               ))}
           </div>
        </div>

        {/* SEGMENTOS DE MERCADO */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 pt-8">
           <MarketBox title="CRIPTO" icon="₿" data={perf?.by_market?.crypto} regime={global?.markets?.crypto?.regime} />
           <MarketBox title="FOREX" icon="¥" data={perf?.by_market?.forex} regime={global?.markets?.forex?.regime} />
           <MarketBox title="ACCIONES" icon="🏛️" data={perf?.by_market?.stocks || {}} regime="RIESGO CONTROLADO" locked={activeStocks.length === 0} />
        </div>

        {/* TABLAS DE EJECUCIÓN */}
        <div className="space-y-16 pt-10">
           <TableSection title="POSICIONES CRIPTOMONEDAS" symbols={activeCrypto} color="amber" />
           <TableSection title="POSICIONES FOREX (CURRENCIES)" symbols={activeForex} color="blue" />
           <TableSection title="POSICIONES ACCIONES (STOCKS)" symbols={activeStocks} color="emerald" />
        </div>

        {/* SUMMARY SUB-PANEL CONSOLIDADO */}
        <div className="pt-4">
           <div className="glass-card bg-gradient-to-r from-blue-600/10 to-emerald-600/10 border-white/10 shadow-3xl flex flex-col md:flex-row items-center justify-between gap-10 !p-12">
              <div className="flex items-center gap-8">
                 <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center text-3xl shadow-inner">📊</div>
                 <div>
                    <h3 className="text-xl font-black italic tracking-tighter text-white uppercase leading-none mb-2">Resumen Total de Portafolio</h3>
                    <p className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest">Consolidado Tiempo Real: Cripto + Forex + Acciones</p>
                 </div>
              </div>
              
              <div className="flex gap-16">
                 <div className="text-center md:text-left">
                    <div className="text-[0.55rem] font-black text-slate-500 uppercase tracking-[0.3em] mb-3">P&L TOTAL (ABIERTO)</div>
                    <div className={`text-4xl font-black italic tracking-tighter ${(global?.summary?.total_pnl_usd || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                       {(global?.summary?.total_pnl_usd || 0) >= 0 ? '+' : ''}${(global?.summary?.total_pnl_usd || 0).toFixed(2)}
                    </div>
                 </div>
                 
                 <div className="text-center md:text-left">
                    <div className="text-[0.55rem] font-black text-slate-500 uppercase tracking-[0.3em] mb-3">ROI GLOBAL PROMEDIO</div>
                    <div className={`text-4xl font-black italic tracking-tighter ${(global?.summary?.avg_roi_pct || 0) >= 0 ? 'text-blue-400' : 'text-rose-400'}`}>
                       {(global?.summary?.avg_roi_pct || 0) >= 0 ? '+' : ''}{(global?.summary?.avg_roi_pct || 0).toFixed(2)}%
                    </div>
                 </div>
              </div>
              
              <div className="hidden lg:block text-right">
                 <div className="text-[0.5rem] font-black text-slate-600 uppercase tracking-widest mb-1">MÉTRICA DE RIESGO</div>
                 <div className="text-blue-500 font-black text-xs italic">ESTABLE / DIVERSIFICADO</div>
              </div>
           </div>
        </div>

        {/* ACTIVIDAD RECIENTE - VISIBILIDAD MEJORADA */}
        <div className="space-y-8 pt-20 border-t border-white/5">
           <div className="flex justify-between items-center px-4">
              <h3 className="section-label">Actividad Reciente (Liquidaciones)</h3>
              <span className="text-[0.55rem] font-bold text-slate-600 uppercase">Historial (10 por página)</span>
           </div>
           <div className="glass-card !p-0 overflow-hidden border-white/5 shadow-2xl">
              <div className="overflow-x-auto">
                 <table className="w-full text-left">
                    <thead className="bg-white/[0.03] text-[0.55rem] text-slate-500 font-black uppercase tracking-[0.2em] border-b border-white/5">
                       <tr>
                          <th className="py-6 px-10">FECHA / HORA</th>
                          <th className="py-6">INSTRUMENTO</th>
                          <th className="py-6">PRECIO COMPRA</th>
                          <th className="py-6">CANTIDAD</th>
                          <th className="py-6">ESTRATEGIA</th>
                          <th className="py-6">ESTADO</th>
                          <th className="py-6 text-right px-10">IMPORTE</th>
                       </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                       {(global?.recent_activity || []).slice(0, MAX_HISTORY).slice(page * ITEMS_PER_PAGE, (page + 1) * ITEMS_PER_PAGE).map((a, i) => {
                          const isWin = (a?.pnl || 0) >= 0
                          return (
                            <tr key={i} className="hover:bg-white/[0.04] transition-colors group">
                               <td className="py-6 px-10">
                                  <div className="text-[0.6rem] font-black text-slate-500 uppercase leading-none mb-1">{a?.time ? new Date(a.time).toLocaleTimeString() : '--:--'}</div>
                                  <div className="text-[0.55rem] font-medium text-slate-700 uppercase tracking-widest">{a?.time ? new Date(a.time).toLocaleDateString() : '--/--'}</div>
                               </td>
                               <td className="font-black text-white italic uppercase tracking-tighter">{a?.symbol || '---'}</td>
                               <td className="font-mono text-[0.7rem] text-slate-400">
                                  ${a?.entry_price ? a.entry_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 }) : '---'}
                               </td>
                               <td className="font-mono text-[0.7rem] text-slate-400">
                                  {a?.quantity ? (a.quantity).toLocaleString('en-US', { minimumFractionDigits: 3, maximumFractionDigits: 3 }) : '---'}
                               </td>
                               <td className="font-mono text-[0.6rem] text-slate-500 font-bold uppercase">
                                  {a?.rule || 'S-01'}
                               </td>
                               <td>
                                  <span className={`px-3 py-1 rounded-full text-[0.55rem] font-black uppercase border italic ${
                                     a.reason && a.reason !== 'closed' ? 'text-blue-400 border-blue-400/20 bg-blue-400/5' :
                                     isWin ? 'text-emerald-400 border-emerald-400/20 bg-emerald-400/5' : 
                                     'text-rose-400 border-rose-400/20 bg-rose-400/5'
                                  }`}>
                                     {a.reason && a.reason !== 'closed' ? a.reason.replace(/_/g, ' ').toUpperCase() : (isWin ? 'Profit Consolidado' : 'Stop Ejecutado')}
                                  </span>
                               </td>
                               <td className="text-right px-10 font-mono font-black text-sm italic">
                                  <span style={{ color: isWin ? '#34d399' : '#fb7185' }}>
                                     {isWin ? '+' : ''}${(a?.pnl || 0).toFixed(2)}
                                  </span>
                               </td>
                            </tr>
                          )
                       })}
                    </tbody>
                 </table>
              </div>
           </div>

           {/* PAGINATION CONTROLS */}
           <div className="flex justify-center items-center gap-4 pt-4">
              <button 
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-6 py-3 rounded-xl bg-white/5 border border-white/5 text-[0.6rem] font-black uppercase tracking-widest hover:bg-white/10 disabled:opacity-20 transition-all">
                Anterior
              </button>
              <div className="flex gap-2">
                 {[...Array(Math.ceil(Math.min(global?.recent_activity?.length || 0, MAX_HISTORY) / ITEMS_PER_PAGE))].map((_, i) => (
                    <button 
                       key={i}
                       onClick={() => setPage(i)}
                       className={`w-8 h-8 rounded-lg text-[0.6rem] font-black flex items-center justify-center transition-all ${page === i ? 'bg-blue-600 text-white shadow-[0_0_15px_rgba(37,99,235,0.4)]' : 'bg-white/5 text-slate-500 hover:bg-white/10'}`}>
                       {i + 1}
                    </button>
                 ))}
              </div>
              <button 
                onClick={() => setPage(p => Math.min(Math.ceil(Math.min(global?.recent_activity?.length || 0, MAX_HISTORY) / ITEMS_PER_PAGE) - 1, p + 1))}
                disabled={page >= Math.ceil(Math.min(global?.recent_activity?.length || 0, MAX_HISTORY) / ITEMS_PER_PAGE) - 1}
                className="px-6 py-3 rounded-xl bg-white/5 border border-white/5 text-[0.6rem] font-black uppercase tracking-widest hover:bg-white/10 disabled:opacity-20 transition-all">
                Siguiente
              </button>
           </div>
        </div>

      </div>

      <style jsx>{`
        .glass-card {
          background: rgba(255, 255, 255, 0.02);
          backdrop-filter: blur(40px);
          -webkit-backdrop-filter: blur(40px);
          border-radius: 28px;
          padding: 32px;
          border: 1px solid rgba(255, 255, 255, 0.04);
          transition: all 0.4s ease;
        }
        .section-label {
          font-size: 0.6rem;
          font-weight: 900;
          color: rgba(255, 255, 255, 0.3);
          text-transform: uppercase;
          letter-spacing: 0.6em;
          font-style: italic;
        }
      `}</style>
    </div>
  )
}

function PerfCard({ title, val, trades, wr, color }: any) {
  const isPositive = val >= 0
  return (
    <div className="glass-card group relative overflow-hidden border-white/5">
       <div className={`absolute top-0 left-0 w-1 h-32 bg-${color}-500/10 group-hover:bg-${color}-500/40 transition-all`} />
       <div className="text-[0.6rem] font-black text-slate-500 uppercase tracking-[0.3em] mb-8">{title}</div>
       <div className={`text-4xl font-black italic tracking-tighter ${isPositive ? 'text-emerald-400 shadow-emerald-500/50' : 'text-rose-400'} mb-8`}>
          {isPositive ? '+' : ''}${val.toFixed(2)}
       </div>
       <div className="flex justify-between text-[0.55rem] font-black text-slate-400 uppercase border-t border-white/5 pt-5">
          <span className="opacity-80">Volumen: <span className="text-white italic">{trades} Trades</span></span>
          <span className={wr > 50 ? 'text-blue-400' : 'text-slate-400'}>{wr}% Win Rate</span>
       </div>
    </div>
  )
}

function MarketBox({ title, icon, data, regime, locked }: any) {
  const isPositive = (data?.pnl_usd || 0) >= 0
  return (
    <div className={`glass-card flex flex-col items-center gap-6 text-center ${locked ? 'opacity-30 grayscale' : 'hover:border-white/10'}`}>
       <div className="text-4xl bg-white/5 w-16 h-16 flex items-center justify-center rounded-2xl group-hover:scale-110 transition-transform">
          {icon}
       </div>
       <div className="space-y-1">
          <h4 className="text-[0.7rem] font-black italic uppercase text-white tracking-widest">{title}</h4>
          <span className="text-[0.5rem] font-black text-amber-500 uppercase tracking-[0.2em]">{regime || 'RIESGO MEDIO'}</span>
       </div>
       {!locked && (
         <div className="w-full pt-4 space-y-6">
            <div className="bg-white/[0.04] p-6 rounded-[20px] border border-white/5 flex flex-col items-center gap-2">
               <span className="text-[0.55rem] font-black text-slate-500 uppercase tracking-widest">P&L Mensual Contabilizado</span>
               <span className={`text-3xl font-black italic tracking-tighter ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                 ${(data?.pnl_usd || 0).toFixed(0)}
               </span>
            </div>
            <div className="flex justify-between text-[0.55rem] font-black text-slate-400 uppercase tracking-widest px-1">
               <span>{data.trades} Operaciones</span>
               <span className="text-blue-500">{data.win_rate}% WR</span>
            </div>
         </div>
       )}
    </div>
  )
}

function TableSection({ title, symbols, color }: any) {
  const totalPnl = symbols.reduce((acc: any, s: any) => acc + (s.unrealized_pnl_usd || 0), 0)
  const avgRoi = symbols.length ? symbols.reduce((acc: any, s: any) => acc + (s.unrealized_pnl_pct || 0), 0) / symbols.length : 0

  return (
    <div className="space-y-6">
       <h4 className="text-[0.7rem] font-black text-white uppercase tracking-[0.4em] flex items-center gap-3 pl-4">
          <div className={`w-2 h-2 rounded-full bg-${color}-500 shadow-[0_0_10px_${color}]`} />
          {title}
       </h4>
       <div className="glass-card !p-0 overflow-hidden border-white/5 shadow-2xl">
          <div className="overflow-x-auto">
             <table className="w-full text-left">
                <thead className="bg-white/[0.03] text-[0.6rem] text-slate-500 font-black uppercase tracking-[0.2em] border-b border-white/5">
                   <tr>
                      <th className="py-6 px-10">INSTRUMENTO</th>
                      <th className="py-6">ENTRADA</th>
                      <th className="py-6">ÚLTIMO PRECIO</th>
                      <th className="py-6">P&L ($)</th>
                      <th className="py-6 text-center">ROI (%)</th>
                      <th className="py-6 text-center">TOT INV</th>
                      <th className="py-6 text-center">CANT</th>
                      <th className="py-6 text-center">ZONA FIBO</th>
                      <th className="py-6 text-right px-10">ESTRATEGIA</th>
                   </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                   {symbols.length > 0 ? (
                     <>
                       {symbols.map((s: any) => {
                         const isLong = s.side === 'long'
                         return (
                           <tr key={s.symbol} className="hover:bg-white/[0.04] transition-all group font-medium">
                              <td className="py-8 px-10">
                                 <div className="flex items-center gap-6">
                                    <div className={`w-1 h-10 rounded-full ${isLong ? 'bg-emerald-500 shadow-[0_0_15px_#10b981]' : 'bg-rose-500 shadow-[0_0_15px_#f43f5e]'}`} />
                                    <div>
                                       <div className="text-sm font-black text-white uppercase">{s.symbol.replace('USDT','')}</div>
                                       <div className={`text-[0.55rem] font-black px-2 py-0.5 rounded mt-1 inline-block ${isLong ? 'text-emerald-400 bg-emerald-500/10' : 'text-rose-400 bg-rose-500/10'}`}>
                                          {isLong ? 'LONG / COMPRA' : 'SHORT / VENTA'}
                                       </div>
                                    </div>
                                 </div>
                              </td>
                              <td className="font-mono text-xs text-slate-500">${s.avg_entry_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</td>
                              <td className="font-mono text-xs text-white font-black">${s.current_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</td>
                              <td className="font-mono text-xs font-black drop-shadow-sm">
                                 <span style={{ color: s.unrealized_pnl_usd >= 0 ? '#34d399' : '#fb7185' }}>
                                    {s.unrealized_pnl_usd >= 0 ? '+' : ''}${s.unrealized_pnl_usd.toFixed(2)}
                                 </span>
                              </td>
                              <td className="text-center font-black text-xs italic drop-shadow-sm">
                                 <span style={{ color: s.unrealized_pnl_pct >= 0 ? '#34d399' : '#fb7185' }}>
                                    {s.unrealized_pnl_pct >= 0 ? '+' : ''}{s.unrealized_pnl_pct.toFixed(2)}%
                                 </span>
                              </td>
                              <td className="text-center font-mono text-xs text-slate-400">
                                 ${(s.total_investment || 0).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
                              </td>
                              <td className="text-center font-mono text-xs text-slate-400">
                                 {(s.quantity || 0).toLocaleString('en-US', { minimumFractionDigits: 3, maximumFractionDigits: 3 })}
                              </td>
                              <td className="text-center">
                                 <div className="flex flex-col items-center gap-1">
                                    <span className={`text-[0.65rem] font-black italic tracking-tighter ${
                                       s.fibonacci_zone > 0 ? 'text-emerald-400' : 
                                       s.fibonacci_zone < 0 ? 'text-rose-400' : 
                                       'text-slate-500'
                                    }`}>
                                       {s.fibonacci_zone > 0 ? `ZONA +${s.fibonacci_zone}` : 
                                        s.fibonacci_zone < 0 ? `ZONA ${s.fibonacci_zone}` : 
                                        'NEUTRAL (0)'}
                                    </span>
                                    <div className="flex gap-0.5">
                                       {[1,2,3,4,5,6].map(i => (
                                          <div key={i} className={`w-1 h-1 rounded-full ${
                                             Math.abs(s.fibonacci_zone) >= i 
                                             ? (s.fibonacci_zone > 0 ? 'bg-emerald-500 shadow-[0_0_5px_#10b981]' : 'bg-rose-500 shadow-[0_0_5px_#f43f5e]') 
                                             : 'bg-white/5'
                                          }`} />
                                        ))}
                                    </div>
                                 </div>
                              </td>
                              <td className="text-right px-10 font-mono text-[0.6rem] text-slate-600 font-bold uppercase">{s.rule_code || 'S-01'}</td>
                           </tr>
                         )
                       })}
                       {/* SUBTOTAL ROW */}
                       <tr className="bg-white/[0.02] border-t border-white/10 font-black italic">
                          <td colSpan={3} className="py-8 px-10 text-[0.7rem] text-slate-400 uppercase tracking-widest">SUBTOTAL MERCADO</td>
                          <td className="py-8 font-mono text-base">
                             <span style={{ color: totalPnl >= 0 ? '#34d399' : '#fb7185' }}>
                                {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}
                             </span>
                          </td>
                          <td className="py-8 text-center text-base">
                             <span style={{ color: avgRoi >= 0 ? '#34d399' : '#fb7185' }}>
                                {avgRoi >= 0 ? '+' : ''}{avgRoi.toFixed(2)}%
                             </span>
                          </td>
                          <td colSpan={4}></td>
                       </tr>
                     </>
                   ) : (
                      <tr><td colSpan={9} className="py-20 text-center text-slate-600 font-black uppercase text-[0.6rem] tracking-widest italic opacity-50">Sin posiciones activas en este sector</td></tr>
                   )}
                </tbody>
             </table>
          </div>
       </div>
    </div>
  )
}
