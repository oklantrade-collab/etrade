'use client'
import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'

/** Canonical crypto symbol for display (matches backend SOLUSDT). */
function normalizeCryptoSymbol(s: string) {
  return (s || '').replace(/\//g, '').toUpperCase()
}

export default function PositionsPage() {
  const [positions, setPositions] = useState<any[]>([])
  const [closedPositions, setClosedPositions] = useState<any[]>([])
  const [tab, setTab] = useState<'open'|'closed'>('open')

  useEffect(() => {
    loadPositions()
    loadClosedPositions()
    const channel = supabase
      .channel('positions-realtime')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'positions' }, () => { loadPositions(); loadClosedPositions(); })
      .subscribe()
    return () => { supabase.removeChannel(channel) }
  }, [])

  async function loadPositions() {
    const { data } = await supabase
      .from('positions')
      .select('*')
      .eq('status', 'open')
      .order('opened_at', { ascending: false })
    if (data) setPositions(data)
  }

  async function loadClosedPositions() {
    const { data } = await supabase
      .from('positions')
      .select('*')
      .eq('status', 'closed')
      .order('closed_at', { ascending: false })
      .limit(50)
    if (data) setClosedPositions(data)
  }

  async function handleClose(id: string) {
    if (!confirm('Are you sure you want to Market Close this position manually?')) return
    try {
      const resp = await fetch(`/api/v1/positions/${id}/close`, { method: 'DELETE' })
      const data = await resp.json()
      
      if (resp.ok && data.status === 'closed') {
        alert('Position closed successfully.')
        loadPositions()
        loadClosedPositions()
      } else {
        alert(`Error: ${data.message || 'Failed to close position.'}`)
      }
    } catch (e: any) {
      alert(`Network/Server error: ${e.message}`)
    }
  }

  const fmtPnl = (val: string | number) => {
    const num = parseFloat(val as string)
    if (isNaN(num)) return '$0.00'
    const str = `$${Math.abs(num).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    return num >= 0 ? `+${str}` : `-${str}`
  }

  return (
    <div>
      <div className="page-header">
        <h1>Positions</h1>
        <p>Live trading positions with Binance OCO brackets</p>
      </div>

      <div className="stats-grid" style={{ marginBottom: 32 }}>
        <div className="card">
          <div className="card-title">Open Risk</div>
          <div className="card-value neutral">{positions.length}/3</div>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Max open operations</p>
        </div>
        <div className="card">
          <div className="card-title">Live PnL</div>
          <div className={`card-value ${positions.reduce((s, p) => s + (parseFloat(p.unrealized_pnl) || 0), 0) >= 0 ? 'positive' : 'negative'}`}>
            {fmtPnl(positions.reduce((s, p) => s + (parseFloat(p.unrealized_pnl) || 0), 0))}
          </div>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Unrealized aggregated</p>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', background: 'var(--bg-card)' }}>
          <button 
            style={{ flex: 1, padding: 16, background: 'none', border: 'none', cursor: 'pointer', fontWeight: tab === 'open' ? 'bold' : 'normal', borderBottom: tab === 'open' ? '2px solid var(--accent-blue)' : 'none', color: tab === 'open' ? 'var(--text)' : 'var(--text-muted)' }}
            onClick={() => setTab('open')}
          >
            Open Positions ({positions.length})
          </button>
          <button 
            style={{ flex: 1, padding: 16, background: 'none', border: 'none', cursor: 'pointer', fontWeight: tab === 'closed' ? 'bold' : 'normal', borderBottom: tab === 'closed' ? '2px solid var(--accent-blue)' : 'none', color: tab === 'closed' ? 'var(--text)' : 'var(--text-muted)' }}
            onClick={() => setTab('closed')}
          >
            Closed History
          </button>
        </div>

        {tab === 'open' && (
          positions.length > 0 ? (
            <div className="table-container" style={{ margin: 0 }}>
              <table>
                <thead>
                    <tr>
                      <th>Time UTC</th>
                      <th>Symbol</th>
                      <th>Side</th>
                      <th className="text-center">Estrategia</th>
                      <th>Entry</th>
                      <th>Current Px <span style={{ fontSize: '0.65rem', opacity: 0.6 }}>(5m)</span></th>
                      <th>Size</th>
                      <th>SL / TP Bracket</th>
                      <th className="text-end">Live PnL</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((p) => {
                      const pnl = parseFloat(p.unrealized_pnl || '0')
                      return (
                        <tr key={p.id}>
                          <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: '1.2' }}>
                            <div>{new Date(p.opened_at).toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit' })}</div>
                            <div style={{ fontWeight: 'bold' }}>{new Date(p.opened_at).toLocaleTimeString('en-US', { timeZone: 'UTC', hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}</div>
                          </td>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                <div style={{ 
                                  width: '3px', 
                                  height: '24px', 
                                  borderRadius: '2px',
                                  background: (p.side || '').toLowerCase().includes('buy') || (p.side || '').toLowerCase().includes('long') ? '#10b981' : '#f43f5e',
                                  boxShadow: (p.side || '').toLowerCase().includes('buy') || (p.side || '').toLowerCase().includes('long') ? '0 0 10px #10b981' : '0 0 10px #f43f5e'
                                }} />
                                <span style={{ fontWeight: 600 }}>{normalizeCryptoSymbol(p.symbol)}</span>
                            </div>
                          </td>
                          <td>
                            <span className={`badge ${(p.side || '').toLowerCase().includes('long') || (p.side || '').toLowerCase().includes('buy') ? 'badge-green' : 'badge-red'}`}>
                              {(p.side || '').toLowerCase().includes('long') || (p.side || '').toLowerCase().includes('buy') ? 'BUY' : 'SELL'}
                            </span>
                          </td>
                          <td className="text-center" style={{ fontWeight: 800, color: 'var(--accent-blue)', fontSize: '0.85rem' }}>
                            {p.rule_code || '—'}
                          </td>
                          <td>${parseFloat(p.entry_price).toFixed(4)}</td>
                        <td>
                          <div style={{ display: 'flex', flexDirection: 'column' }}>
                            <span style={{ color: 'var(--accent-blue)' }}>
                              ${parseFloat(p.current_price || p.entry_price).toFixed(4)}
                            </span>
                          </div>
                        </td>
                        <td style={{ color: parseFloat(p.size) >= 0 ? 'var(--text)' : 'var(--accent-red)' }}>
                          {parseFloat(p.size) >= 0 ? '+' : ''}{parseFloat(p.size).toLocaleString('en-US', { maximumFractionDigits: 6 })}
                        </td>
                        <td>
                          <div style={{ display: 'flex', flexDirection: 'column', fontSize: '0.8rem' }}>
                            <span style={{ color: 'var(--accent-red)' }}>SL: ${parseFloat(p.stop_loss).toFixed(4)}</span>
                            <span style={{ color: 'var(--accent-green)' }}>TP: ${parseFloat(p.take_profit).toFixed(4)}</span>
                          </div>
                        </td>
                        <td style={{ textAlign: 'end' }}>
                          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                            <span style={{ fontWeight: 600, color: pnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                              {fmtPnl(pnl)}
                            </span>
                            {parseFloat(p.entry_price) > 0 && (
                              <span style={{ fontSize: '0.75rem', opacity: 0.8, color: pnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                                ({pnl >= 0 ? '+' : ''}{((pnl / (parseFloat(p.entry_price) * Math.abs(parseFloat(p.size)))) * 100).toFixed(2)}%)
                              </span>
                            )}
                          </div>
                        </td>
                        <td>
                          <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                            <button 
                              onClick={async () => {
                                if (confirm(`¿Cerrar posición de ${normalizeCryptoSymbol(p.symbol)} manualmente? Se enviará al historial.`)) {
                                  try {
                                    const res = await fetch(`/api/v1/positions/crypto/${p.id}/close`, { method: 'POST' })
                                    if (res.ok) {
                                      loadPositions()
                                      loadClosedPositions()
                                    } else {
                                      alert("Error al cerrar posición")
                                    }
                                  } catch (err) {
                                    console.error("Close error:", err)
                                  }
                                }
                              }}
                              style={{ width: '32px', height: '32px', borderRadius: '50%', background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)', color: '#10B981', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 'bold' }}
                              title="Cerrar Posición (Historial)"
                            >
                               ✓
                            </button>
                            <button 
                              onClick={async () => {
                                if (confirm(`¿ELIMINAR registro de ${normalizeCryptoSymbol(p.symbol)} permanentemente? No aparecerá en el historial.`)) {
                                  try {
                                    const res = await fetch(`/api/v1/positions/crypto/${p.id}`, { method: 'DELETE' })
                                    if (res.ok) {
                                      loadPositions()
                                      loadClosedPositions()
                                    } else {
                                      alert("Error al eliminar registro")
                                    }
                                  } catch (err) {
                                    console.error("Delete error:", err)
                                  }
                                }
                              }}
                              style={{ width: '32px', height: '32px', borderRadius: '50%', background: 'rgba(244,63,94,0.1)', border: '1px solid rgba(244,63,94,0.2)', color: '#F43F5E', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 'bold' }}
                              title="ELIMINAR Registro"
                            >
                               🗑️
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-muted)' }}>
              <p>No open positions right now.</p>
            </div>
          )
        )}

        {tab === 'closed' && (
          closedPositions.length > 0 ? (
            <div className="table-container" style={{ margin: 0 }}>
              <table>
                <thead>
                  <tr>
                    <th>Time UTC</th>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th className="text-center">Size</th>
                    <th>Entry</th>
                    <th>Close Px</th>
                    <th className="text-center">Estrategia</th>
                    <th>Reason</th>
                    <th className="text-end">PnL</th>
                  </tr>
                </thead>
                <tbody>
                  {closedPositions.map((p) => {
                    const time = new Date(p.closed_at).toLocaleString('en-US', { timeZone: 'UTC' })
                    const pnl = parseFloat(p.realized_pnl || '0')
                    const pnlPct = parseFloat(p.realized_pnl_pct || '0')
                    return (
                      <tr key={p.id}>
                        <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{time}</td>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                              <div style={{ 
                                width: '3px', 
                                height: '24px', 
                                borderRadius: '2px',
                                opacity: 0.5,
                                background: (p.side || '').toLowerCase().includes('buy') || (p.side || '').toLowerCase().includes('long') ? '#10b981' : '#f43f5e',
                                boxShadow: (p.side || '').toLowerCase().includes('buy') || (p.side || '').toLowerCase().includes('long') ? '0 0 10px #10b981' : '0 0 10px #f43f5e'
                              }} />
                              <span style={{ fontWeight: 600 }}>{normalizeCryptoSymbol(p.symbol)}</span>
                          </div>
                        </td>
                        <td>
                          <span className={`badge ${(p.side || '').toLowerCase().includes('long') || (p.side || '').toLowerCase().includes('buy') ? 'badge-green' : 'badge-red'}`}>
                            {(p.side || '').toLowerCase().includes('long') || (p.side || '').toLowerCase().includes('buy') ? 'BUY' : 'SELL'}
                          </span>
                        </td>
                        <td style={{ textAlign: 'center', fontSize: '0.9rem' }}>{parseFloat(p.size).toLocaleString('en-US')}</td>
                        <td>${parseFloat(p.entry_price).toFixed(4)}</td>
                        <td>${parseFloat(p.current_price || p.entry_price).toFixed(4)}</td>
                        <td style={{ fontWeight: 600, color: 'var(--accent-blue)', textAlign: 'center' }}>{p.rule_code || '—'}</td>
                        <td>
                          <span className={`badge ${p.close_reason === 'TP_HIT' ? 'badge-green' : p.close_reason === 'SL_HIT' ? 'badge-red' : 'badge-gray'}`}>
                            {p.close_reason === 'sar_phase_change' ? 'SAR PHASE CHANGE' : 
                             p.close_reason === 'tp_dynamic_band' ? 'BAND EXIT' : 
                             p.close_reason || 'MANUAL'}
                          </span>
                        </td>
                        <td style={{ textAlign: 'end' }}>
                          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                             <span style={{ fontWeight: 600, color: pnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                               {fmtPnl(pnl)}
                             </span>
                             <span style={{ fontSize: '0.75rem', opacity: 0.8, color: pnlPct >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                               ({pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%)
                             </span>
                          </div>
                        </td>
                        <td>
                          <button 
                            onClick={async () => {
                              if (confirm(`¿ELIMINAR este registro histórico permanentemente de la DB?`)) {
                                try {
                                  const res = await fetch(`/api/v1/positions/crypto/${p.id}`, { method: 'DELETE' })
                                  if (res.ok) {
                                    loadClosedPositions()
                                  } else {
                                    alert("Error al eliminar registro")
                                  }
                                } catch (err) {
                                  console.error("Delete error:", err)
                                }
                              }
                            }}
                            style={{ width: '24px', height: '24px', borderRadius: '50%', background: 'rgba(244,63,94,0.05)', border: '1px solid rgba(244,63,94,0.1)', color: '#F43F5E', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.7rem' }}
                            title="Eliminar del Historial"
                          >
                             🗑️
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-muted)' }}>
              <p>No closed positions history.</p>
            </div>
          )
        )}
      </div>
    </div>
  )
}
