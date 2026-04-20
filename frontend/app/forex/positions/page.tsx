'use client'
import { useState, useEffect } from 'react'
import ForexWelcomeScreen from '../WelcomeScreen'

interface ForexPosition {
  id: string
  symbol: string
  side: string
  lots: number
  entry_price: number
  sl_price: number | null
  tp_price: number | null
  opened_at: string
  rule_code: string
  current_price?: number
}

export default function ForexPositions() {
  const [connected, setConnected] = useState(false)
  const [loading, setLoading] = useState(true)
  const [positions, setPositions] = useState<ForexPosition[]>([])
  const [closedPositions, setClosedPositions] = useState<ForexPosition[]>([])
  const [snapshots, setSnapshots] = useState<any>({})
  const [activeTab, setActiveTab] = useState<'open' | 'closed'>('open')

  useEffect(() => {
    async function init() {
      try {
        const statusRes = await fetch('/api/v1/forex/status')
        const status = await statusRes.json()
        setConnected(status.connected)
        
        if (status.connected) {
          await fetchData()
        }
      } catch (err) {
        console.error("Error init forex positions:", err)
      } finally {
        setLoading(false)
      }
    }
    init()

    const interval = setInterval(() => {
        if (connected) fetchData()
    }, 5000)

    return () => clearInterval(interval)
  }, [connected])

  async function fetchData() {
    try {
      const [posRes, closedRes, snapRes] = await Promise.all([
        fetch('/api/v1/forex/positions?status=open'),
        fetch('/api/v1/forex/positions?status=closed'),
        fetch('/api/v1/forex/snapshots')
      ])
      
      if (posRes.ok) setPositions(await posRes.json())
      if (closedRes.ok) setClosedPositions(await closedRes.json())
      if (snapRes.ok) setSnapshots(await snapRes.json())
    } catch (err) {
      console.error("Error fetching data:", err)
    }
  }

  if (loading) return (
     <div className="min-h-screen bg-[#020205] flex items-center justify-center text-blue-500 font-black uppercase tracking-widest text-[0.6rem] animate-pulse">
        Sincronizando Órdenes Forex...
     </div>
  )

  if (!connected) return <ForexWelcomeScreen />

  return (
    <div className="min-h-screen bg-[#020208] text-slate-200 pb-40 relative selection:bg-blue-500/30">
      {/* GLOW DE FONDO */}
      <div className="absolute top-0 left-0 w-full h-[500px] bg-gradient-to-b from-blue-600/10 to-transparent pointer-events-none" />
      
      <div className="max-w-7xl mx-auto px-6 pt-12 space-y-12 relative z-10">
        
        {/* HEADER SECTION */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-6 mb-8">
           <div className="space-y-4">
              <div className="flex items-center gap-3">
                 <div className="w-2 h-2 rounded-full bg-blue-500 shadow-[0_0_10px_#3b82f6] animate-pulse" />
                 <span className="text-[0.6rem] font-black text-blue-400 uppercase tracking-[0.4em]">Configuración Forex activa</span>
              </div>
              <h1 className="text-4xl font-black italic tracking-tighter text-white uppercase leading-none">Positions</h1>
              <p className="text-slate-500 text-sm max-w-xl">Live trailing positions with cTrader API integration</p>
           </div>
        </div>

        {/* STATS CARDS like Crypto */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
            <div className="glass-card !p-6 border-white/5 shadow-xl">
                 <div className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest mb-1">Active Risk</div>
                 <div className="text-3xl font-black italic text-white mb-1">{positions.length}/{process.env.NEXT_PUBLIC_MAX_FX_MOD || '15'}</div>
                 <div className="text-[0.7rem] text-slate-500">Max open operations</div>
            </div>
            <div className="glass-card !p-6 border-white/5 shadow-xl">
                 <div className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest mb-1">Live PnL</div>
                 <div className={`text-3xl font-black italic mb-1 ${
                    positions.reduce((acc, p) => {
                        const snap = snapshots[p.symbol] || {}
                        const cur = parseFloat(snap.price || 0)
                        if (cur <= 0) return acc
                        const isLong = p.side.toLowerCase() === 'long' || p.side.toLowerCase() === 'buy'
                        const pipSize = p.symbol.includes('JPY') || p.symbol.includes('XAU') ? 0.01 : 0.0001
                        const pipVal = p.symbol.includes('JPY') || p.symbol.includes('XAU') ? 1.0 : 10.0
                        const pips = isLong ? (cur - p.entry_price) / pipSize : (p.entry_price - cur) / pipSize
                        return acc + (pips * pipVal * p.lots)
                    }, 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                 }`}>
                    {positions.reduce((acc, p) => {
                        const snap = snapshots[p.symbol] || {}
                        const cur = parseFloat(snap.price || 0)
                        if (cur <= 0) return acc
                        const isLong = p.side.toLowerCase() === 'long' || p.side.toLowerCase() === 'buy'
                        const pipSize = (p.symbol.includes('JPY') || p.symbol.includes('XAU')) ? 0.01 : 0.0001
                        const pipVal = (p.symbol.includes('JPY') || p.symbol.includes('XAU')) ? 1.0 : 10.0
                        const pips = isLong ? (cur - p.entry_price) / pipSize : (p.entry_price - cur) / pipSize
                        return acc + (pips * pipVal * p.lots)
                    }, 0) >= 0 ? '+' : '-'}${Math.abs(positions.reduce((acc, p) => {
                        const snap = snapshots[p.symbol] || {}
                        const cur = parseFloat(snap.price || 0)
                        if (cur <= 0) return acc
                        const isLong = p.side.toLowerCase() === 'long' || p.side.toLowerCase() === 'buy'
                        const pipSize = (p.symbol.includes('JPY') || p.symbol.includes('XAU')) ? 0.01 : 0.0001
                        const pipVal = (p.symbol.includes('JPY') || p.symbol.includes('XAU')) ? 1.0 : 10.0
                        const pips = isLong ? (cur - p.entry_price) / pipSize : (p.entry_price - cur) / pipSize
                        return acc + (pips * pipVal * p.lots)
                    }, 0)).toFixed(2)}
                 </div>
                 <div className="text-[0.7rem] text-slate-500">Unrealized aggregated (USD)</div>
            </div>
        </div>

        {/* TABLE SECTION */}
        <div className="glass-card !p-0 overflow-hidden border-white/10 shadow-3xl bg-white/[0.01] backdrop-blur-3xl rounded-[32px]">
           
           {/* TABS */}
           <div className="flex border-b border-white/5 bg-white/[0.02]">
              <button 
                onClick={() => setActiveTab('open')}
                className={`flex-1 py-6 text-[0.6rem] font-black uppercase tracking-[0.3em] transition-all ${activeTab === 'open' ? 'text-blue-400 bg-blue-500/5' : 'text-slate-500 hover:text-slate-300'}`}
              >
                Posiciones Abiertas ({positions.length})
                {activeTab === 'open' && <div className="h-0.5 w-12 bg-blue-500 mx-auto mt-2 rounded-full shadow-[0_0_10px_#3b82f6]" />}
              </button>
              <button 
                onClick={() => setActiveTab('closed')}
                className={`flex-1 py-6 text-[0.6rem] font-black uppercase tracking-[0.3em] transition-all ${activeTab === 'closed' ? 'text-blue-400 bg-blue-500/5' : 'text-slate-500 hover:text-slate-300'}`}
              >
                Closed History ({closedPositions.length})
                {activeTab === 'closed' && <div className="h-0.5 w-12 bg-blue-500 mx-auto mt-2 rounded-full shadow-[0_0_10px_#3b82f6]" />}
              </button>
           </div>

           <div className="overflow-x-auto">
              {activeTab === 'open' ? (
                <table className="w-full text-left">
                  <thead className="bg-white/[0.03] text-[0.6rem] text-slate-500 font-black uppercase tracking-[0.2em] border-b border-white/5">
                     <tr>
                        <th className="py-8 px-10">INSTRUMENTO</th>
                        <th className="py-8">APERTURA</th>
                        <th className="py-8">LOTAJE</th>
                        <th className="py-8">ENTRADA</th>
                        <th className="py-8">ACTUAL</th>
                        <th className="py-8">SL / TP</th>
                        <th className="py-8">PNL (PIPS)</th>
                        <th className="py-8 text-right px-10">ESTRATEGIA</th>
                     </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                     {positions.length > 0 ? (
                       positions.map((pos) => {
                         const snap = snapshots[pos.symbol] || {}
                         const curPrice = parseFloat(snap.price || 0)
                         const isLong = pos.side.toLowerCase() === 'long' || pos.side.toLowerCase() === 'buy'
                         
                         // Calculo simple de pips
                         const pipSize = pos.symbol.includes('JPY') ? 0.01 : 0.0001
                         const pips = curPrice > 0 ? (isLong ? (curPrice - pos.entry_price) / pipSize : (pos.entry_price - curPrice) / pipSize) : 0
                         
                         return (
                           <tr key={pos.id} className="hover:bg-white/[0.03] transition-all group">
                              <td className="py-8 px-10">
                                 <div className="flex items-center gap-6">
                                    <div className={`w-1 h-10 rounded-full ${isLong ? 'bg-emerald-500 shadow-[0_0_15px_#10b981]' : 'bg-rose-500 shadow-[0_0_15px_#f43f5e]'}`} />
                                    <div>
                                       <div className="text-base font-black text-white uppercase tracking-tighter italic">{pos.symbol}</div>
                                       <div className={`text-[0.55rem] font-black px-2 py-0.5 rounded mt-1 inline-block ${isLong ? 'text-emerald-400 bg-emerald-500/10' : 'text-rose-400 bg-rose-500/10'}`}>
                                          {isLong ? 'LONG / COMPRA' : 'SHORT / VENTA'}
                                       </div>
                                    </div>
                                 </div>
                              </td>
                              <td className="py-8">
                                 <span className="text-[0.65rem] font-bold text-slate-500 uppercase">{new Date(pos.opened_at).toLocaleTimeString()}</span>
                              </td>
                              <td className="py-8">
                                 <span className="font-mono text-sm text-white font-black">{pos.lots.toFixed(2)}</span>
                                 <span className="text-[0.5rem] font-black text-slate-700 ml-1">LOTS</span>
                              </td>
                              <td className="py-8 font-mono text-[0.8rem] text-slate-400">
                                 {pos.entry_price.toFixed(pos.symbol.includes('JPY') ? 3 : 5)}
                              </td>
                              <td className="py-8 font-mono text-[0.8rem] text-white font-black animate-pulse">
                                 {curPrice > 0 ? curPrice.toFixed(pos.symbol.includes('JPY') ? 3 : 5) : '---'}
                              </td>
                              <td className="py-8">
                                 <div className="space-y-1">
                                    <div className="text-[0.55rem] font-black text-rose-500/50 uppercase flex items-center gap-2">
                                       <span className="w-1.5 h-1.5 rounded-full bg-rose-500/30" /> SL: {pos.sl_price?.toFixed(pos.symbol.includes('JPY') ? 3 : 5) || '---'}
                                    </div>
                                    <div className="text-[0.55rem] font-black text-emerald-500/50 uppercase flex items-center gap-2">
                                       <span className="w-1.5 h-1.5 rounded-full bg-emerald-500/30" /> TP: {pos.tp_price?.toFixed(pos.symbol.includes('JPY') ? 3 : 5) || '---'}
                                    </div>
                                 </div>
                              </td>
                              <td className="py-8 font-mono font-black italic">
                                 <span className={`text-sm ${pips >= 0 ? 'text-emerald-400 shadow-emerald-500/50' : 'text-rose-400'}`}>
                                    {pips >= 0 ? '+' : ''}{pips.toFixed(1)}
                                    <span className="text-[0.6rem] ml-1 opacity-50">PIPS</span>
                                 </span>
                              </td>
                              <td className="py-8 text-right px-10">
                                 <span className="bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 px-4 py-2 rounded-2xl font-mono text-[0.7rem] font-black uppercase tracking-[0.2em] shadow-[0_0_15px_rgba(99,102,241,0.1)]">
                                    {pos.rule_code || 'FX-CORE'}
                                 </span>
                              </td>
                           </tr>
                         )
                       })
                     ) : (
                       <tr>
                          <td colSpan={8} className="py-32 text-center">
                             <div className="flex flex-col items-center gap-4 opacity-40">
                                <div className="text-4xl">🕳️</div>
                                <div className="text-[0.7rem] font-black text-slate-500 uppercase tracking-[0.5em] italic">Sin posiciones abiertas ahora mismo</div>
                             </div>
                          </td>
                       </tr>
                     )}
                  </tbody>
               </table>
              ) : (
                <table className="w-full text-left">
                  <thead className="bg-white/[0.01] text-[0.6rem] text-slate-500 font-black uppercase tracking-[0.2em] border-b border-white/5">
                    <tr>
                       <th className="py-8 px-10">INSTRUMENTO</th>
                       <th className="py-8">CERRADA EL</th>
                       <th className="py-8">LOTAJE</th>
                       <th className="py-8">ENTRADA</th>
                       <th className="py-8">CIERRE</th>
                       <th className="py-8">PNL (PIPS)</th>
                       <th className="py-8">RESULTADO</th>
                       <th className="py-8 text-right px-10">ESTRATEGIA</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {closedPositions.length > 0 ? (
                      closedPositions.map((pos: any) => {
                        const isLong = pos.side.toLowerCase() === 'long' || pos.side.toLowerCase() === 'buy'
                        const exitPrice = pos.exit_price || pos.close_price || pos.current_price || 0
                        const pips = pos.pips_profit !== undefined ? pos.pips_profit : (pos.realized_pips || 0)
                        const realPnl = parseFloat(pos.pnl_usd || 0)
                        const isWin = realPnl >= 0

                        return (
                          <tr key={pos.id} className="hover:bg-white/[0.03] transition-all group">
                             <td className="py-8 px-10">
                                <div className="flex items-center gap-6">
                                   <div className={`w-1 h-10 rounded-full ${isLong ? 'bg-emerald-500/20' : 'bg-rose-500/20'}`} />
                                   <div>
                                      <div className="text-base font-black text-white uppercase tracking-tighter italic opacity-60">{pos.symbol}</div>
                                      <div className={`text-[0.5rem] font-black px-1.5 py-0.5 rounded mt-1 inline-block ${isLong ? 'text-emerald-400/40 bg-emerald-500/5' : 'text-rose-400/40 bg-rose-500/5'}`}>
                                         {isLong ? 'LONG' : 'SHORT'}
                                      </div>
                                   </div>
                                </div>
                             </td>
                             <td className="py-8">
                                <div className="flex flex-col">
                                  <span className="text-[0.65rem] font-bold text-slate-400 uppercase">{new Date(pos.closed_at || pos.opened_at).toLocaleDateString()}</span>
                                  <span className="text-[0.55rem] font-medium text-slate-600 uppercase">{new Date(pos.closed_at || pos.opened_at).toLocaleTimeString()}</span>
                                </div>
                             </td>
                             <td className="py-8">
                                <span className="font-mono text-sm text-slate-400">{pos.lots.toFixed(2)}</span>
                             </td>
                             <td className="py-8 font-mono text-[0.8rem] text-slate-500">
                                {pos.entry_price.toFixed(pos.symbol.includes('JPY') ? 3 : 5)}
                             </td>
                             <td className="py-8 font-mono text-[0.8rem] text-slate-300 font-bold">
                                {exitPrice.toFixed(pos.symbol.includes('JPY') ? 3 : 5)}
                             </td>
                             <td className="py-8 font-mono font-black italic">
                                <div className="flex flex-col">
                                   <span className={`text-sm ${realPnl > 0 ? 'text-emerald-400' : realPnl < 0 ? 'text-rose-400' : 'text-slate-400'}`}>
                                      {realPnl > 0 ? '+' : realPnl < 0 ? '-' : ''}${Math.abs(realPnl).toFixed(2)}
                                   </span>
                                   <span className={`text-[0.6rem] opacity-50 ${isWin ? 'text-emerald-500/60' : 'text-rose-500/60'}`}>
                                      {isWin ? '+' : ''}{pips.toFixed(1)} PIPS
                                   </span>
                                </div>
                             </td>
                             <td className="py-8">
                                <span className={`text-[0.55rem] font-black px-3 py-1 rounded-full uppercase tracking-widest ${isWin ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 shadow-[0_0_10px_rgba(16,185,129,0.1)]' : 'bg-rose-500/10 text-rose-500 border border-rose-500/20 shadow-[0_0_10px_rgba(244,63,94,0.1)]'}`}>
                                   {pos.close_reason ? pos.close_reason.replace('_', ' ') : (isWin ? 'PROFIT' : 'LOSS')}
                                </span>
                             </td>
                             <td className="py-8 text-right px-10">
                                <span className="bg-slate-500/10 text-slate-400 border border-white/5 px-4 py-2 rounded-2xl font-mono text-[0.7rem] font-black uppercase tracking-[0.2em]">
                                   {pos.rule_code || 'S-01'}
                                </span>
                             </td>
                          </tr>
                        )
                      })
                    ) : (
                      <tr>
                         <td colSpan={8} className="py-32 text-center">
                            <div className="flex flex-col items-center gap-4 opacity-40">
                               <div className="text-4xl">📚</div>
                               <div className="text-[0.7rem] font-black text-slate-500 uppercase tracking-[0.5em] italic">No hay historial de posiciones cerradas</div>
                            </div>
                         </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              )}
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
        .shadow-3xl {
          box-shadow: 0 40px 100px -20px rgba(0, 0, 0, 0.5);
        }
      `}</style>
    </div>
  )
}
