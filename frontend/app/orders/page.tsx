'use client'
import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'

export default function OrdersPage() {
  const [orders, setOrders] = useState<any[]>([])
  const [trapOrders, setTrapOrders] = useState<any[]>([])
  const [filter, setFilter] = useState<string>('all')
  const [page, setPage] = useState(1)
  const itemsPerPage = 20

  useEffect(() => {
    loadOrders()
    loadTrapOrders()
  }, [])

  async function loadOrders() {
    const { data } = await supabase.from('orders').select('*').order('created_at', { ascending: false }).limit(200)
    if (data) setOrders(data)
  }

  async function loadTrapOrders() {
    const { data } = await supabase
      .from('pending_orders')
      .select('*')
      .eq('status', 'pending')
      .or('trade_type.eq.trap,timeframe.eq.TRAP')
      .order('created_at', { ascending: false })
    if (data) setTrapOrders(data)
  }

  const filteredOrders = orders.filter(o => {
    if (filter === 'all') return true
    if (filter === 'TRAP') return ['Dd61', 'Dd51'].includes(o.rule_code)
    if (filter === 'BUY' || filter === 'SELL') return o.side === filter
    return o.status === filter
  })

  const totalPages = Math.ceil(filteredOrders.length / itemsPerPage) || 1
  const paginatedOrders = filteredOrders.slice((page - 1) * itemsPerPage, page * itemsPerPage)

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'open': return 'badge-blue'
      case 'tp_hit': return 'badge-green'
      case 'sl_hit': return 'badge-orange' 
      case 'manual_close': return 'badge-gray'
      case 'error': return 'badge-red'
      default: return 'badge-gray'
    }
  }

  const getStatusText = (status: string) => {
    switch(status) {
      case 'tp_hit': return 'TP ✅'
      case 'sl_hit': return 'SL 🛑'
      case 'manual_close': return 'Manual'
      case 'error': return 'Error'
      case 'open': return 'Open'
      default: return status
    }
  }

  return (
    <div className="space-y-10">
      <div className="page-header">
        <div className="flex items-center gap-4">
          <div className="w-2 h-8 bg-blue-500 rounded-full" />
          <div>
            <h1>Orders History</h1>
            <p className="text-slate-400">Log of all Binance order submissions and TRAP range orders</p>
          </div>
        </div>
      </div>

      {/* SECCIÓN TRAP — RANGO PLANO ACUMULACIÓN */}
      <section>
        <div className="flex items-center justify-between mb-4 px-2">
           <h2 className="text-xs font-black text-slate-500 uppercase tracking-[0.3em]">Órdenes de Rango Plano (TRAP)</h2>
           <span className="text-[0.6rem] font-bold text-blue-400 uppercase tracking-widest bg-blue-500/10 px-3 py-1 rounded-full border border-blue-500/20">
             Cazando en soporte/resistencia
           </span>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {trapOrders.length > 0 ? (
            trapOrders.map(t => (
              <div key={t.id} className="card glass-effect !p-6 border-blue-500/20 shadow-[0_0_30px_rgba(59,130,246,0.05)] relative overflow-hidden group">
                 <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
                    <span className="text-4xl font-black italic">TRAP</span>
                 </div>
                 
                 <div className="flex justify-between items-start mb-6">
                    <div>
                       <div className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest mb-1">Activo</div>
                       <div className="text-xl font-black italic tracking-tighter">{t.symbol.replace('USDT','')}</div>
                    </div>
                    <div className="text-right">
                       <div className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest mb-1">Lado</div>
                       <span className={`text-xs font-black px-3 py-1 rounded-md ${t.direction === 'long' ? 'text-emerald-400 bg-emerald-400/10' : 'text-rose-400 bg-rose-400/10'}`}>
                         {t.direction.toUpperCase()}
                       </span>
                    </div>
                 </div>

                 <div className="grid grid-cols-2 gap-4 mb-6">
                    <div>
                       <div className="text-[0.55rem] font-bold text-slate-500 uppercase mb-1">Precio Limit</div>
                       <div className="text-sm font-mono font-bold text-white">${t.limit_price.toLocaleString()}</div>
                    </div>
                    <div className="text-right">
                       <div className="text-[0.55rem] font-bold text-slate-500 uppercase mb-1">Regla</div>
                       <div className="text-sm font-mono font-bold text-blue-400">{t.rule_code}</div>
                    </div>
                 </div>

                 <div className="bg-slate-900/40 rounded-xl p-4 border border-white/5 space-y-3">
                    <div className="flex justify-between text-[0.6rem] font-bold">
                       <span className="text-slate-500 uppercase">Stop Loss:</span>
                       <span className="text-rose-500 font-mono">${t.sl_price.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between text-[0.6rem] font-bold">
                       <span className="text-slate-500 uppercase">Take Profit 1:</span>
                       <span className="text-emerald-500 font-mono">${t.tp1_price.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between text-[0.6rem] font-bold">
                       <span className="text-slate-500 uppercase">Take Profit 2:</span>
                       <span className="text-emerald-400 font-mono">${t.tp2_price.toLocaleString()}</span>
                    </div>

                    <div className="flex justify-between text-[0.6rem] font-bold pt-1 border-t border-white/5">
                       <span className="text-slate-500 uppercase">Temporaridad:</span>
                       <span className="text-blue-400 uppercase tracking-tighter">
                         {t.timeframe === 'TRAP' ? 'N/A' : (t.timeframe === '15m' ? '15 Minutos' : (t.timeframe === '4h' ? '4 Horas' : t.timeframe))}
                       </span>
                    </div>
                 </div>

                 <div className="mt-4 flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                    <span className="text-[0.6rem] text-blue-400/80 font-bold uppercase tracking-widest">Esperando Gatillo...</span>
                 </div>
              </div>
            ))
          ) : (
            <div className="col-span-full py-8 text-center text-slate-500 italic text-sm bg-slate-900/20 rounded-2xl border border-dashed border-slate-800">
               No hay órdenes TRAP activas en este momento.
            </div>
          )}
        </div>
      </section>

      {/* HISTORIAL GENERAL */}
      <section>
        <div className="flex items-center justify-between mb-6 px-2">
           <h2 className="text-xs font-black text-slate-500 uppercase tracking-[0.3em]">Historial de Ejecuciones</h2>
           <div className="flex gap-2">
             {['all', 'TRAP', 'BUY', 'SELL', 'open', 'sl_hit', 'tp_hit', 'error'].map(f => (
               <button 
                 key={f} 
                 onClick={() => { setFilter(f); setPage(1); }}
                 className={`text-[0.6rem] font-black px-4 py-2 rounded-lg transition-all border uppercase tracking-widest ${filter === f ? 'bg-blue-600 border-blue-500 text-white' : 'bg-slate-900/60 border-slate-800 text-slate-500 hover:border-slate-700'}`}
               >
                 {f === 'all' ? 'Todos' : f.replace('_', ' ')}
               </button>
             ))}
           </div>
        </div>

        <div className="card glass-effect !p-0 overflow-hidden border-slate-800/50">
          {paginatedOrders.length > 0 ? (
            <>
              <div className="table-container !bg-transparent">
                <table className="w-full text-left">
                  <thead>
                    <tr className="text-[0.6rem] text-slate-500 uppercase tracking-widest border-b border-white/5">
                      <th className="py-4 px-6">Fecha</th>
                      <th>Símbolo</th>
                      <th>Lado</th>
                      <th>Tipo</th>
                      <th>Cant.</th>
                      <th>Limit</th>
                      <th>Entrada</th>
                      <th>SL / TP</th>
                      <th>Estado</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {paginatedOrders.map(o => {
                      const time = new Date(o.created_at).toLocaleString('es-ES', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
                      const isTrap = ['Dd61', 'Dd51'].includes(o.rule_code)
                      return (
                        <tr key={o.id} className="hover:bg-white/5 transition-colors group">
                          <td className="py-4 px-6 text-[0.65rem] font-mono text-slate-500 uppercase">{time}</td>
                           <td className="font-bold text-sm tracking-tighter">
                             <div className="flex flex-col">
                               <span>{o.symbol.replace('USDT','')}</span>
                               {isTrap && <span className="text-[0.5rem] text-blue-400 font-bold uppercase tracking-widest">TRAP 🎯</span>}
                             </div>
                           </td>
                          <td>
                            <span className={`text-[0.6rem] font-black uppercase ${o.side === 'BUY' ? 'text-emerald-500' : 'text-rose-500'}`}>
                              {o.side}
                            </span>
                          </td>
                          <td className="text-[0.65rem] font-bold text-slate-500 uppercase tracking-tighter">{o.order_type}</td>
                          <td className="text-xs font-mono">{parseFloat(o.quantity).toFixed(4)}</td>
                          <td className="text-xs font-mono text-slate-400">${parseFloat(o.limit_price || '0').toFixed(2)}</td>
                          <td className="text-xs font-mono font-bold">${parseFloat(o.entry_price || '0').toFixed(2)}</td>
                          <td className="text-[0.65rem] font-mono">
                             <span className="text-rose-500">${parseFloat(o.stop_loss_price).toFixed(2)}</span> / 
                             <span className="text-emerald-500">${parseFloat(o.take_profit_price).toFixed(2)}</span>
                          </td>
                          <td>
                            <span className={`badge ${getStatusBadge(o.status)} text-[0.6rem] font-black uppercase`} style={o.status === 'sl_hit' ? { backgroundColor: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.2)' } : {}}>
                              {getStatusText(o.status)}
                            </span>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              
              <div className="flex justify-between items-center p-6 border-t border-white/5">
                <button 
                  disabled={page === 1} 
                  onClick={() => setPage(page - 1)}
                  className="text-[0.65rem] font-bold px-4 py-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 disabled:opacity-30"
                >
                  Previous
                </button>
                <span className="text-[0.65rem] font-bold text-slate-500 uppercase tracking-widest">
                  Page {page} of {totalPages}
                </span>
                <button 
                  disabled={page === totalPages} 
                  onClick={() => setPage(page + 1)}
                  className="text-[0.65rem] font-bold px-4 py-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 disabled:opacity-30"
                >
                  Next
                </button>
              </div>
            </>
          ) : (
             <div className="py-20 text-center text-slate-500 italic text-sm">No se encontraron órdenes en el historial.</div>
          )}
        </div>
      </section>

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
