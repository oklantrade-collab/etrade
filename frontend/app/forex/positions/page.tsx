'use client'
import { useState, useEffect, useRef } from 'react'
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
  const [closedPage, setClosedPage] = useState(0)
  const ITEMS_PER_PAGE = 10
  const [showChart, setShowChart] = useState(false)
  const [selectedTicker, setSelectedTicker] = useState('')



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

  // Función auxiliar para calcular Pips y PnL USD
  const calculatePnL = (pos: any, currentPrice: number) => {
    if (!currentPrice || currentPrice <= 0) return { pips: 0, usd: 0, pct: 0 }
    
    const isLong = pos.side.toLowerCase() === 'long' || pos.side.toLowerCase() === 'buy'
    const isJPY = pos.symbol.includes('JPY')
    const isXAU = pos.symbol.includes('XAU')
    
    // Tamaño del pip
    const pipSize = (isJPY || isXAU) ? 0.01 : 0.0001
    
    // Cálculo de pips
    const pips = isLong ? (currentPrice - pos.entry_price) / pipSize : (pos.entry_price - currentPrice) / pipSize
    
    // Valor del pip (Estándar para 0.01 lotes)
    let pipValue = 10.0 // Default 1.0 lote = $10/pip
    if (isXAU) pipValue = 1.0
    if (isJPY) pipValue = 6.5
    
    const usd = pips * pipValue * Math.abs(pos.lots)
    
    // Porcentaje de ganancia/pérdida relativo al precio de entrada
    const pct = (isLong ? (currentPrice - pos.entry_price) : (pos.entry_price - currentPrice)) / pos.entry_price * 100
    
    return { pips, usd, pct }
  }

  const totalUnrealized = positions.reduce((acc, p) => {
    const snap = snapshots[p.symbol] || {}
    const cur = parseFloat(snap.price || 0)
    return acc + calculatePnL(p, cur).usd
  }, 0)

  return (
    <div className="min-h-screen bg-[#020208] text-slate-200 pb-40 relative selection:bg-blue-500/30">
      <div className="absolute top-0 left-0 w-full h-[500px] bg-gradient-to-b from-blue-600/10 to-transparent pointer-events-none" />
      
      <div className="max-w-7xl mx-auto px-6 pt-12 space-y-12 relative z-10">
        
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

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
            <div className="glass-card !p-6 border-white/5 shadow-xl">
                 <div className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest mb-1">Active Risk</div>
                 <div className="text-3xl font-black italic text-white mb-1">{positions.length}/{process.env.NEXT_PUBLIC_MAX_FX_MOD || '15'}</div>
                 <div className="text-[0.7rem] text-slate-500">Max open operations</div>
            </div>
            <div className="glass-card !p-6 border-white/5 shadow-xl">
                 <div className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest mb-1">Live PnL</div>
                 <div className={`text-3xl font-black italic mb-1 ${totalUnrealized >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {totalUnrealized >= 0 ? '+' : '-'}${Math.abs(totalUnrealized).toFixed(2)}
                 </div>
                 <div className="text-[0.7rem] text-slate-500">Unrealized aggregated (USD)</div>
            </div>
        </div>

        <div className="glass-card !p-0 overflow-hidden border-white/10 shadow-3xl bg-white/[0.01] backdrop-blur-3xl rounded-[32px]">
           <div className="flex border-b border-white/5 bg-white/[0.02]">
              <button 
                onClick={() => { setActiveTab('open'); setClosedPage(0); }}
                className={`flex-1 py-6 text-[0.6rem] font-black uppercase tracking-[0.3em] transition-all ${activeTab === 'open' ? 'text-blue-400 bg-blue-500/5' : 'text-slate-500 hover:text-slate-300'}`}
              >
                Posiciones Abiertas ({positions.length})
                {activeTab === 'open' && <div className="h-0.5 w-12 bg-blue-500 mx-auto mt-2 rounded-full shadow-[0_0_10px_#3b82f6]" />}
              </button>
              <button 
                onClick={() => { setActiveTab('closed'); setClosedPage(0); }}
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
                        <th className="py-8">RESULTADO</th>
                        <th className="py-8 text-right px-10">ESTRATEGIA</th>
                     </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                     {positions.length > 0 ? (
                       positions.map((pos) => {
                         const snap = snapshots[pos.symbol] || {}
                         const curPrice = parseFloat(snap.price || 0)
                         const pnl = calculatePnL(pos, curPrice)
                         const isLong = pos.side.toLowerCase() === 'long' || pos.side.toLowerCase() === 'buy'
                         
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
                                 <span className={`font-mono text-sm font-black ${pos.lots >= 0 ? 'text-white' : 'text-rose-400'}`}>
                                    {pos.lots >= 0 ? '+' : ''}{pos.lots.toFixed(2)}
                                 </span>
                                 <span className="text-[0.5rem] font-black text-slate-700 ml-1">LOTS</span>
                               </td>
                              <td className="py-8 font-mono text-[0.8rem] text-slate-400">
                                 {pos.entry_price.toFixed(pos.symbol.includes('JPY') || pos.symbol.includes('XAU') ? 3 : 5)}
                              </td>
                              <td className="py-8 font-mono text-[0.8rem] text-white font-black animate-pulse">
                                 {curPrice > 0 ? curPrice.toFixed(pos.symbol.includes('JPY') || pos.symbol.includes('XAU') ? 3 : 5) : '---'}
                              </td>
                              <td className="py-8">
                                 <div className="space-y-1">
                                    <div className="text-[0.55rem] font-black text-rose-500/50 uppercase flex items-center gap-2">
                                       <span className="w-1.5 h-1.5 rounded-full bg-rose-500/30" /> SL: {pos.sl_price?.toFixed(pos.symbol.includes('JPY') || pos.symbol.includes('XAU') ? 3 : 5) || '---'}
                                    </div>
                                    <div className="text-[0.55rem] font-black text-emerald-500/50 uppercase flex items-center gap-2">
                                       <span className="w-1.5 h-1.5 rounded-full bg-emerald-500/30" /> TP: {pos.tp_price?.toFixed(pos.symbol.includes('JPY') || pos.symbol.includes('XAU') ? 3 : 5) || '---'}
                                    </div>
                                 </div>
                              </td>
                              <td className="py-8 font-mono font-black italic">
                                 <div className="flex flex-col">
                                    <span className={`text-sm ${pnl.usd >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                       {pnl.usd >= 0 ? '+' : ''}${pnl.usd.toFixed(2)}
                                    </span>
                                     <span className={`text-[0.55rem] font-black italic opacity-60 ${pnl.pct >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                                        {pnl.pct >= 0 ? '+' : ''}{pnl.pct.toFixed(4)}%
                                     </span>
                                 </div>
                              </td>
                              <td className="py-8 text-right px-10">
                                 <div className="flex items-center justify-end gap-3">
                                    <span className="bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 px-4 py-2 rounded-2xl font-mono text-[0.7rem] font-black uppercase tracking-[0.2em] shadow-[0_0_15px_rgba(99,102,241,0.1)]">
                                       {pos.rule_code || 'FX-CORE'}
                                    </span>
                                    <button 
                                      onClick={() => {
                                        setSelectedTicker(pos.symbol)
                                        setShowChart(true)
                                      }}
                                      className="w-8 h-8 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-500 hover:bg-blue-500 hover:text-white transition-all shadow-lg shadow-blue-500/10 group-hover:scale-110"
                                      title="Ver Gráfico"
                                    >
                                       <span className="text-[0.6rem] font-black">📈</span>
                                    </button>

                                    <button 
                                      onClick={async () => {
                                        if (confirm(`¿Cerrar posición de ${pos.symbol} manualmente? Se enviará al historial.`)) {
                                          try {
                                            const res = await fetch(`/api/v1/positions/forex/${pos.id}/close`, { method: 'POST' })
                                            if (res.ok) {
                                              fetchData()
                                            } else {
                                              alert("Error al cerrar posición")
                                            }
                                          } catch (err) {
                                            console.error("Close error:", err)
                                          }
                                        }
                                      }}
                                      className="w-8 h-8 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-500 hover:bg-emerald-500 hover:text-white transition-all shadow-lg shadow-emerald-500/10 group-hover:scale-110"
                                      title="Cerrar Posición (Mover al Historial)"
                                    >
                                       <span className="text-xs font-black">✓</span>
                                    </button>
                                    <button 
                                      onClick={async () => {
                                        if (confirm(`¿ELIMINAR registro de ${pos.symbol} permanentemente? No aparecerá en el historial.`)) {
                                          try {
                                            const res = await fetch(`/api/v1/positions/forex/${pos.id}`, { method: 'DELETE' })
                                            if (res.ok) {
                                              fetchData()
                                            } else {
                                              alert("Error al eliminar registro")
                                            }
                                          } catch (err) {
                                            console.error("Delete error:", err)
                                          }
                                        }
                                      }}
                                      className="w-8 h-8 rounded-full bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-500 hover:bg-rose-500 hover:text-white transition-all shadow-lg shadow-rose-500/10 group-hover:scale-110"
                                      title="ELIMINAR Registro (Borrado Permanente)"
                                    >
                                       <span className="text-xs font-black">🗑️</span>
                                    </button>
                                 </div>
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
                <>
                <table className="w-full text-left">
                  <thead className="bg-white/[0.01] text-[0.6rem] text-slate-500 font-black uppercase tracking-[0.2em] border-b border-white/5">
                    <tr>
                       <th className="py-8 px-10">INSTRUMENTO</th>
                       <th className="py-8">CERRADA EL</th>
                       <th className="py-8">LOTAJE</th>
                       <th className="py-8">ENTRADA</th>
                       <th className="py-8">CIERRE</th>
                       <th className="py-8">ESTADO / REASON</th>
                       <th className="py-8">RESULTADO</th>
                       <th className="py-8 text-right px-10">ESTRATEGIA</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {closedPositions.length > 0 ? (
                      closedPositions.slice(closedPage * ITEMS_PER_PAGE, (closedPage + 1) * ITEMS_PER_PAGE).map((pos: any) => {
                        const isLong = pos.side.toLowerCase() === 'long' || pos.side.toLowerCase() === 'buy'
                        const exitPrice = pos.exit_price || pos.close_price || pos.current_price || 0
                        const realPnl = parseFloat(pos.pnl_usd || 0)

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
                                <span className={`font-mono text-sm ${pos.lots >= 0 ? 'text-slate-400' : 'text-rose-400/60'}`}>
                                   {pos.lots >= 0 ? '+' : ''}{pos.lots.toFixed(2)}
                                </span>
                             </td>
                             <td className="py-8 font-mono text-[0.8rem] text-slate-500">
                                {pos.entry_price.toFixed(pos.symbol.includes('JPY') || pos.symbol.includes('XAU') ? 3 : 5)}
                             </td>
                             <td className="py-8 font-mono text-[0.8rem] text-slate-300 font-bold">
                                {exitPrice.toFixed(pos.symbol.includes('JPY') || pos.symbol.includes('XAU') ? 3 : 5)}
                             </td>
                             <td className="py-8">
                                <span className="text-[0.6rem] font-black text-slate-500 uppercase bg-white/5 px-2 py-1 rounded">
                                   {pos.close_reason || 'MANUAL / SL'}
                                </span>
                             </td>
                             <td className="py-8 font-mono font-black italic">
                                <div className="flex flex-col">
                                   <span className={`text-sm ${realPnl > 0 ? 'text-emerald-400' : realPnl < 0 ? 'text-rose-400' : 'text-slate-400'}`}>
                                      {realPnl > 0 ? '+' : realPnl < 0 ? '-' : ''}${Math.abs(realPnl).toFixed(2)}
                                   </span>
                                    <span className={`text-[0.55rem] font-black italic opacity-60 ${realPnl >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                                       {realPnl >= 0 ? '+' : ''}{((isLong ? (exitPrice - pos.entry_price) : (pos.entry_price - exitPrice)) / pos.entry_price * 100).toFixed(4)}%
                                    </span>
                                </div>
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
                         <td colSpan={9} className="py-32 text-center">
                            <div className="flex flex-col items-center gap-4 opacity-40">
                               <div className="text-4xl">📚</div>
                               <div className="text-[0.7rem] font-black text-slate-500 uppercase tracking-[0.5em] italic">No hay historial de posiciones cerradas</div>
                            </div>
                         </td>
                      </tr>
                    )}
                  </tbody>
                </table>

                {/* PAGINATION CONTROLS */}
                {activeTab === 'closed' && closedPositions.length > ITEMS_PER_PAGE && (
                  <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '16px', padding: '24px 0', borderTop: '1px solid rgba(255,255,255,0.05)', background: 'rgba(255,255,255,0.01)', flexWrap: 'wrap' }}>
                    <button 
                      onClick={() => setClosedPage(p => Math.max(0, p - 1))}
                      disabled={closedPage === 0}
                      style={{ padding: '8px 16px', borderRadius: '8px', background: '#12161F', border: '1px solid rgba(255,255,255,0.1)', color: '#FFF', cursor: 'pointer', fontSize: '0.8rem', opacity: closedPage === 0 ? 0.3 : 1 }}
                    >
                      Anterior
                    </button>
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', justifyContent: 'center' }}>
                      {[...Array(Math.ceil(closedPositions.length / ITEMS_PER_PAGE))].map((_, i) => (
                        <button 
                          key={i}
                          onClick={() => setClosedPage(i)}
                          style={{ 
                            width: '32px', 
                            height: '32px', 
                            borderRadius: '6px', 
                            cursor: 'pointer', 
                            fontWeight: 'bold', 
                            fontSize: '0.8rem', 
                            background: closedPage === i ? '#3b82f6' : '#12161F', 
                            color: closedPage === i ? '#fff' : '#888',
                            border: closedPage === i ? 'none' : '1px solid rgba(255,255,255,0.1)',
                            boxShadow: closedPage === i ? '0 0 10px rgba(59,130,246,0.5)' : 'none'
                          }}
                        >
                          {i + 1}
                        </button>
                      ))}
                    </div>
                    <button 
                      onClick={() => setClosedPage(p => Math.min(Math.ceil(closedPositions.length / ITEMS_PER_PAGE) - 1, p + 1))}
                      disabled={closedPage >= Math.ceil(closedPositions.length / ITEMS_PER_PAGE) - 1}
                      style={{ padding: '8px 16px', borderRadius: '8px', background: '#12161F', border: '1px solid rgba(255,255,255,0.1)', color: '#FFF', cursor: 'pointer', fontSize: '0.8rem', opacity: closedPage >= Math.ceil(closedPositions.length / ITEMS_PER_PAGE) - 1 ? 0.3 : 1 }}
                    >
                      Siguiente
                    </button>
                  </div>
                )}
                </>
              )}
           </div>
        </div>

        {showChart && <ChartModal symbol={selectedTicker} onClose={() => setShowChart(false)} />}
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

function TradingViewWidget({ symbol }: { symbol: string }) {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!container.current) return;
    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.type = "text/javascript";
    script.async = true;
    
    // Mapeo de símbolos para Forex
    const getFxtvSymbol = (s: string) => {
        if (s.includes('XAU')) return `SAXO:XAUUSD`;
        if (s.includes('JPY')) return `FX:USDJPY`;
        if (s.includes('EUR')) return `FX:EURUSD`;
        if (s.includes('GBP')) return `FX:GBPUSD`;
        return `FX:${s}`;
    };

    script.innerHTML = JSON.stringify({
      "autosize": true,
      "symbol": getFxtvSymbol(symbol),
      "interval": "15",
      "timezone": "America/Lima",
      "theme": "dark",
      "style": "1",
      "locale": "en",
      "enable_publishing": false,
      "hide_side_toolbar": false,
      "allow_symbol_change": true,
      "calendar": false,
      "support_host": "https://www.tradingview.com"
    });
    container.current.appendChild(script);
    
    return () => {
      if (container.current) container.current.innerHTML = '';
    }
  }, [symbol]);

  return (
    <div className="tradingview-widget-container" ref={container} style={{ height: "100%", width: "100%" }}>
      <div className="tradingview-widget-container__widget" style={{ height: "calc(100% - 32px)", width: "100%" }}></div>
    </div>
  );
}

function ChartModal({ symbol, onClose }: { symbol: string, onClose: () => void }) {
  return (
    <div 
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-md p-4 md:p-8"
      onClick={onClose}
    >
      <div 
        className="relative w-[95%] h-[92%] bg-[#0a0a0f] border border-white/10 rounded-[32px] overflow-hidden shadow-2xl shadow-blue-500/10 flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-8 py-6 border-b border-white/5 bg-white/[0.02]">
          <div className="flex items-center gap-4">
            <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse shadow-[0_0_10px_#3b82f6]" />
            <h3 className="text-sm font-black uppercase tracking-[0.3em] text-white italic">{symbol} <span className="text-slate-500 not-italic ml-2">Technical Analysis</span></h3>
          </div>
          <button 
            onClick={onClose}
            className="w-10 h-10 rounded-full bg-white/5 hover:bg-rose-500/20 hover:text-rose-500 transition-all flex items-center justify-center text-slate-400 group"
          >
            <span className="text-xl font-light group-hover:rotate-90 transition-transform">✕</span>
          </button>
        </div>
        <div className="flex-1 w-full bg-black/20">
          <TradingViewWidget symbol={symbol} />
        </div>
      </div>
    </div>
  );
}

