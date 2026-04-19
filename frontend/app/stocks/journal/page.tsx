"use client"
import { useState, useEffect } from 'react'
import Link from 'next/link'

export default function StocksJournal() {
  const [trades, setTrades] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchJournal()
  }, [])

  const fetchJournal = async () => {
    try {
      const res = await fetch('/api/v1/stocks/journal')
      const data = await res.json()
      setTrades(Array.isArray(data) ? data : [])
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const stats = {
    totalTrades: trades.length,
    wins: trades.filter(t => (t.unrealized_pnl || 0) > 0).length,
    losses: trades.filter(t => (t.unrealized_pnl || 0) <= 0).length,
    totalPnL: trades.reduce((acc, t) => acc + (t.unrealized_pnl || 0), 0)
  }

  const winRate = stats.totalTrades > 0 ? (stats.wins / stats.totalTrades * 100).toFixed(1) : 0

  return (
    <div style={{ padding: '30px', background: '#0B0E14', minHeight: '100vh', color: '#FFF', fontFamily: 'Inter, sans-serif' }}>
      
      {/* HEADER & STATS */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '30px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 900, margin: 0, letterSpacing: '-0.02em' }}>📓 Diario de Trading (Stocks)</h1>
          <p style={{ color: '#666', fontSize: '14px', marginTop: '5px' }}>Historial de operaciones cerradas y rendimiento</p>
        </div>
        
        <div style={{ display: 'flex', gap: '30px', background: 'rgba(255,255,255,0.02)', padding: '15px 25px', borderRadius: '16px', border: '1px solid rgba(255,255,255,0.05)' }}>
          <div style={{ textAlign: 'center' }}>
            <p style={{ fontSize: '10px', color: '#555', fontWeight: 800, textTransform: 'uppercase', marginBottom: '4px' }}>Win Rate</p>
            <p style={{ fontSize: '18px', fontWeight: 900, margin: 0, color: Number(winRate) >= 50 ? '#00C896' : '#FF4757' }}>{winRate}%</p>
          </div>
          <div style={{ width: '1px', background: 'rgba(255,255,255,0.05)' }} />
          <div style={{ textAlign: 'center' }}>
            <p style={{ fontSize: '10px', color: '#555', fontWeight: 800, textTransform: 'uppercase', marginBottom: '4px' }}>Trades</p>
            <p style={{ fontSize: '18px', fontWeight: 900, margin: 0 }}>{stats.totalTrades}</p>
          </div>
          <div style={{ width: '1px', background: 'rgba(255,255,255,0.05)' }} />
          <div style={{ textAlign: 'center' }}>
            <p style={{ fontSize: '10px', color: '#555', fontWeight: 800, textTransform: 'uppercase', marginBottom: '4px' }}>Net PnL</p>
            <p style={{ fontSize: '18px', fontWeight: 900, margin: 0, color: stats.totalPnL >= 0 ? '#00C896' : '#FF4757' }}>
              {stats.totalPnL >= 0 ? '+' : ''}${stats.totalPnL.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </p>
          </div>
        </div>
      </div>

      <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: '16px', border: '1px solid rgba(255,255,255,0.05)', overflow: 'hidden' }}>
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: '150px 100px 100px 120px 120px 100px 80px 120px', 
          padding: '16px 24px', 
          background: 'rgba(255,255,255,0.03)',
          fontSize: '10px', 
          fontWeight: 900, 
          color: '#555', 
          textTransform: 'uppercase',
          letterSpacing: '0.1em'
        }}>
          <span>Cierre (Fecha)</span>
          <span>Ticker</span>
          <span>Grupo</span>
          <span>Entrada Avg</span>
          <span>Salida</span>
          <span>Acciones</span>
          <span>DCA</span>
          <span style={{ textAlign: 'right' }}>Resultado PnL</span>
        </div>

        {loading && <div style={{ padding: '60px', textAlign: 'center', color: '#444' }}>Cargando diario...</div>}
        {!loading && trades.length === 0 && (
          <div style={{ padding: '80px', textAlign: 'center' }}>
             <p style={{ color: '#444', fontSize: '14px', marginBottom: '10px' }}>Tu diario está vacío.</p>
             <p style={{ color: '#222', fontSize: '12px' }}>Las posiciones aparecerán aquí una vez que sean cerradas por el motor.</p>
          </div>
        )}
        
        {!loading && trades.map((trade, i) => {
          const isWin = (trade.unrealized_pnl || 0) > 0;
          return (
            <div key={trade.id} style={{ 
              display: 'grid', 
              gridTemplateColumns: '150px 100px 100px 120px 120px 100px 80px 120px', 
              padding: '18px 24px', 
              borderBottom: '1px solid rgba(255,255,255,0.02)',
              alignItems: 'center',
              background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)'
            }}>
              <span style={{ fontSize: '11px', color: '#666' }}>
                {new Date(trade.updated_at).toLocaleString([], { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
              </span>
              <span style={{ fontWeight: 900, fontSize: '14px' }}>{trade.ticker}</span>
              <span style={{ fontSize: '10px', fontWeight: 800, color: '#555' }}>
                {trade.group_name === 'inversiones_pro' ? 'PRO' : 'HOT'}
              </span>
              <span style={{ color: '#AAA' }}>${trade.avg_price?.toFixed(2)}</span>
              <span style={{ fontWeight: 700 }}>${trade.current_price?.toFixed(2)}</span>
              <span style={{ color: '#AAA' }}>{trade.shares}</span>
              <span style={{ color: trade.dca_count > 0 ? '#CE93D8' : '#333' }}>
                {trade.dca_count > 0 ? `×${trade.dca_count}` : '—'}
              </span>
              <div style={{ textAlign: 'right' }}>
                <p style={{ 
                  margin: 0, 
                  fontWeight: 900, 
                  color: isWin ? '#00C896' : '#FF4757',
                  fontSize: '14px'
                }}>
                  {isWin ? '+' : ''}${trade.unrealized_pnl?.toFixed(2)}
                </p>
                <p style={{ 
                  margin: 0, 
                  fontSize: '11px', 
                  color: isWin ? '#00C896' : '#FF4757',
                  opacity: 0.6
                }}>
                  {isWin ? '+' : ''}{trade.unrealized_pnl_pct?.toFixed(2)}%
                </p>
              </div>
            </div>
          )
        })}
      </div>

      <div style={{ marginTop: '30px' }}>
        <Link href="/stocks/positions" style={{ color: '#00C896', textDecoration: 'none', fontWeight: 800, fontSize: '12px', borderBottom: '1px solid transparent' }}>
          ← REGRESAR A POSICIONES ACTIVAS
        </Link>
      </div>
    </div>
  )
}
