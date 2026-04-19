"use client"
import { useState } from 'react'
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line 
} from 'recharts'

export default function StocksBacktesting() {
  const [ticker, setTicker] = useState('NVDA')
  const [strategy, setStrategy] = useState('S01')
  const [period, setPeriod] = useState('1y')
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<any>(null)

  const handleRun = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/v1/stocks/backtest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticker,
          rule_code: strategy,
          period: period
        })
      })
      const data = await res.json()
      
      if (!res.ok || data.error) {
        alert(data.error || data.detail || "Error en el servidor")
        setResults(null)
      } else {
        setResults(data)
      }
    } catch (err) {
      console.error(err)
      alert("Error ejecutando backtest")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ padding: '30px', background: '#0B0E14', minHeight: '100vh', color: '#FFF', fontFamily: 'Inter, sans-serif' }}>
      
      <div style={{ marginBottom: '40px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 900, margin: 0, letterSpacing: '-0.02em' }}>🧪 Stocks Backtesting Lab</h1>
          <p style={{ color: '#666', fontSize: '14px', marginTop: '5px' }}>Simula tus estrategias S01-S08 contra datos históricos</p>
        </div>
        <div style={{ background: 'rgba(0,180,255,0.1)', border: '1px solid rgba(0,180,255,0.2)', padding: '10px 20px', borderRadius: '12px' }}>
          <span style={{ fontSize: '12px', fontWeight: 800, color: '#4FC3F7' }}>LIVE MARKET FEED</span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: '30px' }}>
        
        {/* CONFIG PANEL */}
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '24px', padding: '24px', height: 'fit-content' }}>
          <h3 style={{ fontSize: '12px', fontWeight: 800, color: '#555', textTransform: 'uppercase', marginBottom: '20px' }}>Parametrización</h3>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div>
              <label style={{ fontSize: '10px', color: '#888', fontWeight: 800, textTransform: 'uppercase' }}>Activo (Ticker)</label>
              <input value={ticker} onChange={e => setTicker(e.target.value.toUpperCase())} style={{ width: '100%', background: '#000', border: '1px solid #333', borderRadius: '10px', padding: '12px', color: '#FFF', marginTop: '4px' }} />
            </div>

            <div>
              <label style={{ fontSize: '10px', color: '#888', fontWeight: 800, textTransform: 'uppercase' }}>Regla Optimizada</label>
              <select value={strategy} onChange={e => setStrategy(e.target.value)} style={{ width: '100%', background: '#000', border: '1px solid #333', borderRadius: '10px', padding: '12px', color: '#FFF', marginTop: '4px' }}>
                <option value="S01">S01 - PRO MKT BUY</option>
                <option value="S02">S02 - PRO LMT BUY</option>
                <option value="S05">S05 - HOT MKT BUY</option>
                <option value="S06">S06 - HOT LMT BUY</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: '10px', color: '#888', fontWeight: 800, textTransform: 'uppercase' }}>Ventana Proyectada</label>
              <div style={{ display: 'flex', gap: '5px', marginTop: '4px' }}>
                {['1m', '3m', '6m', '1y'].map(p => (
                  <button key={p} onClick={() => setPeriod(p)} style={{ flex: 1, padding: '8px', borderRadius: '8px', border: period === p ? '1px solid #00C896' : '1px solid #333', background: period === p ? 'rgba(0,200,150,0.1)' : 'transparent', color: period === p ? '#00C896' : '#666', fontSize: '11px', fontWeight: 700, cursor: 'pointer' }}>{p.toUpperCase()}</button>
                ))}
              </div>
            </div>

            <button 
              onClick={handleRun}
              disabled={loading}
              style={{ marginTop: '20px', padding: '16px', background: '#00C896', border: 'none', borderRadius: '12px', color: '#000', fontWeight: 950, cursor: 'pointer', fontSize: '13px' }}
            >
              {loading ? 'SIMULANDO...' : 'EJECUTAR BACKTEST'}
            </button>
          </div>
        </div>

        {/* RESULTS PANEL */}
        <div style={{ minHeight: '500px' }}>
          {!results && !loading && (
            <div style={{ height: '100%', border: '2px dashed rgba(255,255,255,0.05)', borderRadius: '24px', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', color: '#444' }}>
               <p style={{ fontSize: '14px', marginBottom: '5px' }}>Selecciona una configuración y ejecuta el test.</p>
               <p style={{ fontSize: '11px' }}>El sistema analizará el historico de precios contra las condiciones de la regla.</p>
            </div>
          )}

          {loading && (
            <div style={{ height: '100%', borderRadius: '24px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(255,255,255,0.01)' }}>
               <div style={{ textAlign: 'center' }}>
                  <div style={{ width: '40px', height: '40px', border: '3px solid #00C896', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
                  <p style={{ marginTop: '15px', fontSize: '12px', fontWeight: 800, color: '#00C896' }}>CALCULANDO ALFA...</p>
               </div>
               <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
            </div>
          )}

          {results && results.summary && (
            <div>
              {/* SUMMARY GRID */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '20px', marginBottom: '20px' }}>
                <div style={{ background: 'rgba(0,200,150,0.05)', padding: '20px', borderRadius: '18px', border: '1px solid rgba(0,200,150,0.1)' }}>
                   <p style={{ fontSize: '10px', fontWeight: 800, color: '#00C896' }}>RETORNO TOTAL</p>
                   <p style={{ fontSize: '24px', fontWeight: 950, margin: '5px 0' }}>+{results.summary?.return}%</p>
                </div>
                <div style={{ background: 'rgba(255,71,87,0.05)', padding: '20px', borderRadius: '18px', border: '1px solid rgba(255,71,87,0.1)' }}>
                   <p style={{ fontSize: '10px', fontWeight: 800, color: '#FF4757' }}>MAX DRAWDOWN</p>
                   <p style={{ fontSize: '24px', fontWeight: 950, margin: '5px 0' }}>{results.summary?.maxDrawdown}%</p>
                </div>
                <div style={{ background: 'rgba(255,183,77,0.05)', padding: '20px', borderRadius: '18px', border: '1px solid rgba(255,183,77,0.1)' }}>
                   <p style={{ fontSize: '10px', fontWeight: 800, color: '#FFB74D' }}>PROFIT FACTOR</p>
                   <p style={{ fontSize: '24px', fontWeight: 950, margin: '5px 0' }}>{results.summary?.profitFactor}</p>
                </div>
              </div>

              {/* CHART */}
              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '30px', borderRadius: '24px', border: '1px solid rgba(255,255,255,0.05)' }}>
                 <h4 style={{ fontSize: '11px', fontWeight: 800, color: '#555', marginBottom: '25px', textTransform: 'uppercase' }}>Simulación Proyectada</h4>
                 <div style={{ height: '300px' }}>
                    <ResponsiveContainer width="100%" height="100%">
                       <LineChart data={results.equityCurve}>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" vertical={false} />
                          <XAxis dataKey="date" stroke="#333" fontSize={10} axisLine={false} tickLine={false} />
                          <YAxis stroke="#333" fontSize={10} axisLine={false} tickLine={false} tickFormatter={v => `$${v}`} />
                          <Tooltip contentStyle={{ background: '#161922', border: '1px solid #333', borderRadius: '12px' }} />
                          <Line type="monotone" dataKey="equity" stroke="#00C896" strokeWidth={4} dot={{ fill: '#00C896', r: 4 }} />
                       </LineChart>
                    </ResponsiveContainer>
                 </div>
              </div>
            </div>
          )}
        </div>

      </div>
    </div>
  )
}
