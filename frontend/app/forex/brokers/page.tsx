'use client'
import { useState, useEffect } from 'react'
import { supabase } from '@/lib/supabase'

export default function BrokersPage() {
  const [balanceAmount, setBalanceAmount] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [positions, setPositions] = useState<any[]>([])

  useEffect(() => {
    fetchBalance()
    fetchPositions()
  }, [])
  const [balanceSource, setBalanceSource] = useState('')

  const fetchBalance = async () => {
    try {
      setLoading(true)
      setError('')
      // Read directly from Supabase — no backend API needed
      const { data, error: sbErr } = await supabase
        .from('trading_config')
        .select('capital_forex_futures, regime_params')
        .eq('id', 1)
        .maybeSingle()

      if (sbErr) {
        setError(sbErr.message)
        return
      }

      const params = data?.regime_params || {}
      const brokerBal = params.broker_balance_forex

      if (brokerBal != null && brokerBal > 0) {
        setBalanceAmount(brokerBal)
        setBalanceSource('IC Markets (en vivo)')
      } else {
        // Fallback: solo capital base asignado
        const base = parseFloat(data?.capital_forex_futures || '0')
        setBalanceAmount(base)
        setBalanceSource('Capital asignado (pendiente sync broker)')
      }
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const fetchPositions = async () => {
    try {
      const res = await fetch('/api/v1/forex/dashboard/positions')
      const data = await res.json()
      if (data.positions) {
        setPositions(data.positions)
      }
    } catch (err: any) {
      console.error("Error fetching positions", err)
    }
  }

  return (
    <div style={{ padding: '32px', maxWidth: '1000px', margin: '0 auto' }}>
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>🏦 Brokers</h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '12px', marginTop: '4px', letterSpacing:'1px', textTransform:'uppercase' }}>Gestión de Conexiones a Cuentas Reales/Demo</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px', marginBottom: '32px' }}>
        {/* IC Markets Card */}
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(0,200,150,0.3)', borderRadius: '10px', padding: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
             <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#00C896', boxShadow: '0 0 10px #00C896' }} />
                <div>
                   <h2 style={{ margin: 0, fontSize: '16px', fontWeight: 800 }}>IC Markets / cTrader</h2>
                   <div style={{ color: '#00C896', fontSize: '11px', fontWeight: 700 }}>CONECTADO API</div>
                </div>
             </div>
          </div>
          
          <div style={{ background: 'rgba(0,0,0,0.2)', padding: '16px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)', marginBottom: '16px' }}>
             <div style={{ color: 'var(--text-muted)', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '4px' }}>Saldo en Vivo (Broker)</div>
             {loading ? (
                <div style={{ color: '#aaa', fontSize: '24px', fontWeight: 800 }}>Cargando...</div>
             ) : error ? (
                <div style={{ color: '#EF4444', fontSize: '14px', fontWeight: 700 }}>Error: {error}</div>
             ) : (
                <div style={{ color: '#FFF', fontSize: '28px', fontWeight: 900 }}>
                  ${balanceAmount?.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})} USD
                </div>
                {balanceSource && (
                  <div style={{ color: 'var(--text-muted)', fontSize: '10px', marginTop: '4px' }}>
                    📡 {balanceSource}
                  </div>
                )}
             )}
          </div>
          
          <button onClick={fetchBalance} disabled={loading} style={{ width: '100%', padding: '10px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#FFF', borderRadius: '6px', fontSize: '12px', cursor: 'pointer' }}>
             🔄 Actualizar Saldo
          </button>
        </div>
      </div>

      <div>
        <h2 style={{ fontSize: '16px', fontWeight: 700, marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          📋 Operaciones Activas ({positions.length})
        </h2>
        
        {positions.length === 0 ? (
           <div style={{ padding: '32px', textAlign: 'center', background: 'rgba(255,255,255,0.02)', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.05)' }}>
             <div style={{ fontSize: '32px', marginBottom: '8px', opacity: 0.5 }}>💤</div>
             <div style={{ color: 'var(--text-secondary)' }}>No hay operaciones activas en este momento.</div>
           </div>
        ) : (
           <div style={{ overflowX: 'auto', background: 'rgba(255,255,255,0.02)', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.05)' }}>
             <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                <thead>
                   <tr style={{ background: 'rgba(0,0,0,0.2)', borderBottom: '1px solid rgba(255,255,255,0.05)', textAlign: 'left' }}>
                      <th style={{ padding: '12px 16px', color: 'var(--text-muted)' }}>ID/TIPO</th>
                      <th style={{ padding: '12px 16px', color: 'var(--text-muted)' }}>SÍMBOLO</th>
                      <th style={{ padding: '12px 16px', color: 'var(--text-muted)' }}>LOTE</th>
                      <th style={{ padding: '12px 16px', color: 'var(--text-muted)' }}>PRECIO ENTRADA</th>
                      <th style={{ padding: '12px 16px', color: 'var(--text-muted)' }}>PRECIO ACTUAL</th>
                      <th style={{ padding: '12px 16px', color: 'var(--text-muted)', textAlign: 'right' }}>PnL</th>
                   </tr>
                </thead>
                <tbody>
                   {positions.map((pos, idx) => {
                      const isLong = pos.side?.toLowerCase() === 'long' || pos.side?.toLowerCase() === 'buy'
                      const isProfit = pos.unrealized_pnl_pips >= 0
                      return (
                        <tr key={idx} style={{ borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
                           <td style={{ padding: '12px 16px' }}>
                              <div style={{ fontWeight: 700 }}>{pos.id || pos.position_id}</div>
                              <div style={{ color: isLong ? '#00C896' : '#EF4444', fontSize: '10px', fontWeight: 900 }}>{isLong ? 'BUY' : 'SELL'}</div>
                           </td>
                           <td style={{ padding: '12px 16px', fontWeight: 800 }}>{pos.symbol}</td>
                           <td style={{ padding: '12px 16px' }}>{pos.quantity}</td>
                           <td style={{ padding: '12px 16px' }}>{pos.avg_entry_price || pos.entry_price}</td>
                           <td style={{ padding: '12px 16px' }}>{pos.current_price}</td>
                           <td style={{ padding: '12px 16px', textAlign: 'right', fontWeight: 800, color: isProfit ? '#00C896' : '#EF4444' }}>
                              {pos.unrealized_pnl_pips > 0 ? '+' : ''}{pos.unrealized_pnl_pips} pips
                           </td>
                        </tr>
                      )
                   })}
                </tbody>
             </table>
           </div>
        )}
      </div>
    </div>
  )
}
