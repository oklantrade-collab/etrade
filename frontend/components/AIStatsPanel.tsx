'use client'
import { useEffect, useState } from 'react'

interface AIStat {
  recommendation: string
  total: number
  acertos: number
  avg_pnl_usd: number
  total_pnl_usd: number
}

export default function AIStatsPanel() {
  const [stats, setStats] = useState<AIStat[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadStats()
  }, [])

  async function loadStats() {
    try {
      const res = await fetch(`/api/v1/performance/ai-stats`)
      if (res.ok) {
        setStats(await res.json())
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div className="p-4 text-xs text-slate-500 italic">Cargando estadísticas de IA...</div>

  return (
    <div className="card glass-effect border-indigo-500/20">
      <div className="flex justify-between items-center mb-6">
        <div>
           <h3 className="font-bold text-lg text-indigo-400 font-mono italic tracking-tighter uppercase">ESTADÍSTICAS DE LA IA</h3>
           <p className="text-[10px] text-slate-500 uppercase tracking-widest font-bold">Últimos 30 días — Paper Trading</p>
        </div>
        <div className="px-3 py-1 bg-indigo-500/10 border border-indigo-500/20 rounded-full">
           <span className="text-[10px] font-black italic text-indigo-400">ANALYSIS ENGINE</span>
        </div>
      </div>

      <div className="table-container">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-slate-800 text-[10px] font-black uppercase text-slate-500 tracking-tighter">
              <th className="pb-3 px-2">Recomendación</th>
              <th className="pb-3 px-2">Trades</th>
              <th className="pb-3 px-2">Acertó (WR)</th>
              <th className="pb-3 px-2 text-right">P&L Histórico</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {stats.map((s, idx) => {
               const wr = s.total > 0 ? (s.acertos / s.total) * 100 : 0
               return (
                <tr key={idx} className="group hover:bg-indigo-500/5 transition-colors">
                  <td className="py-4 px-2">
                    <span className={`px-2 py-1 rounded text-[10px] font-black uppercase tracking-widest ${
                      s.recommendation === 'enter' ? 'bg-emerald-500/20 text-emerald-400' :
                      s.recommendation === 'caution' ? 'bg-amber-500/20 text-amber-400' :
                      s.recommendation === 'wait' ? 'bg-slate-500/20 text-slate-400' :
                      'bg-slate-800 text-slate-300'
                    }`}>
                      {s.recommendation}
                    </span>
                  </td>
                  <td className="py-4 px-2 font-mono text-xs">{s.total}</td>
                  <td className="py-4 px-2">
                    <div className="flex flex-col">
                       <span className="text-xs font-bold text-white">{wr.toFixed(1)}%</span>
                       <span className="text-[9px] text-slate-500">{s.acertos}W / {s.total - s.acertos}L</span>
                    </div>
                  </td>
                  <td className={`py-4 px-2 text-right font-mono font-bold text-xs ${s.total_pnl_usd >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                    {s.total_pnl_usd >= 0 ? '+' : ''}{s.total_pnl_usd.toFixed(2)} USDT
                  </td>
                </tr>
               )
            })}
            {stats.length === 0 && (
              <tr>
                <td colSpan={4} className="py-10 text-center text-slate-600 text-xs italic">Aún no hay suficientes trades registrados con recomendación IA.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <style jsx>{`
        .table-container {
          overflow-x: auto;
        }
      `}</style>
    </div>
  )
}
