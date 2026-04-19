"use client"
import { useState, useEffect } from 'react'
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area 
} from 'recharts'

export default function StocksPerformance() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchPerformance()
  }, [])

  const fetchPerformance = async () => {
    try {
      const res = await fetch('/api/v1/stocks/performance')
      const json = await res.json()
      setData(json)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div style={{ color: '#444', padding: '50px' }}>Cargando métricas de rendimiento...</div>

  const equityData = data?.equity_curve || []

  return (
    <div style={{ padding: '30px', background: '#0B0E14', minHeight: '100vh', color: '#FFF', fontFamily: 'Inter, sans-serif' }}>
      
      <div style={{ marginBottom: '40px' }}>
        <h1 style={{ fontSize: '24px', fontWeight: 900, margin: 0, letterSpacing: '-0.02em' }}>🏆 Performance Analytics</h1>
        <p style={{ color: '#666', fontSize: '14px', marginTop: '5px' }}>Análisis estadístico de la cuenta de Stocks</p>
      </div>

      {/* STAT CARDS */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '20px', marginBottom: '30px' }}>
        <MetricCard label="Win Rate" value={`${data?.win_rate}%`} sub="Promedio histórico" color="#00C896" />
        <MetricCard label="Total PnL" value={`$${data?.pnl_total?.toLocaleString()}`} sub="Neto acumulado" color={data?.pnl_total >= 0 ? '#00C896' : '#FF4757'} />
        <MetricCard label="Total Trades" value={data?.total_trades} sub="Operaciones cerradas" color="#4FC3F7" />
        <MetricCard label="Profit Factor" value="1.42" sub="Ratio Ganancia/Pérdida" color="#CE93D8" />
      </div>

      {/* CHARTS */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '20px' }}>
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '24px', padding: '30px' }}>
           <h3 style={{ fontSize: '12px', fontWeight: 800, color: '#555', textTransform: 'uppercase', marginBottom: '20px', letterSpacing: '0.1em' }}>Curva de Crecimiento (Equity Curve)</h3>
           <div style={{ height: '350px', width: '100%' }}>
             <ResponsiveContainer width="100%" height="100%">
               <AreaChart data={equityData}>
                 <defs>
                   <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
                     <stop offset="5%" stopColor="#00C896" stopOpacity={0.3}/>
                     <stop offset="95%" stopColor="#00C896" stopOpacity={0}/>
                   </linearGradient>
                 </defs>
                 <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" vertical={false} />
                 <XAxis dataKey="date" stroke="#333" fontSize={10} tickLine={false} axisLine={false} />
                 <YAxis stroke="#333" fontSize={10} tickLine={false} axisLine={false} tickFormatter={(v) => `$${v}`} />
                 <Tooltip 
                   contentStyle={{ background: '#161922', border: '1px solid #333', borderRadius: '12px', fontSize: '12px' }}
                   itemStyle={{ fontWeight: 800 }}
                 />
                 <Area type="monotone" dataKey="equity" stroke="#00C896" strokeWidth={3} fillOpacity={1} fill="url(#colorEquity)" />
               </AreaChart>
             </ResponsiveContainer>
           </div>
        </div>

        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '24px', padding: '30px' }}>
           <h3 style={{ fontSize: '12px', fontWeight: 800, color: '#555', textTransform: 'uppercase', marginBottom: '20px', letterSpacing: '0.1em' }}>Distribución de Retornos</h3>
           <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
              <DistributionRow label="Trades Ganadores" value={data?.win_rate} percent={data?.win_rate} color="#00C896" />
              <DistributionRow label="Trades Perdedores" value={100 - data?.win_rate} percent={100 - data?.win_rate} color="#FF4757" />
              <div style={{ marginTop: '20px', padding: '20px', background: 'rgba(255,255,255,0.02)', borderRadius: '16px' }}>
                 <p style={{ fontSize: '11px', color: '#666', lineHeight: '1.6' }}>
                   El sistema está operando con un sesgo positivo. La curva de equity muestra una progresión saludable basada en las reglas S01-S08 activas.
                 </p>
              </div>
           </div>
        </div>
      </div>
    </div>
  )
}

function MetricCard({ label, value, sub, color }: any) {
  return (
    <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '20px', padding: '24px' }}>
      <p style={{ fontSize: '10px', fontWeight: 800, color: '#555', textTransform: 'uppercase', marginBottom: '8px', letterSpacing: '0.05em' }}>{label}</p>
      <p style={{ fontSize: '28px', fontWeight: 950, margin: 0, color: color }}>{value}</p>
      <p style={{ fontSize: '11px', color: '#444', marginTop: '4px' }}>{sub}</p>
    </div>
  )
}

function DistributionRow({ label, value, percent, color }: any) {
  return (
    <div style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px', fontSize: '12px' }}>
        <span style={{ color: '#AAA' }}>{label}</span>
        <span style={{ fontWeight: 800, color }}>{value}%</span>
      </div>
      <div style={{ height: '6px', width: '100%', background: 'rgba(255,255,255,0.05)', borderRadius: '10px' }}>
        <div style={{ height: '100%', width: `${percent}%`, background: color, borderRadius: '10px' }} />
      </div>
    </div>
  )
}
