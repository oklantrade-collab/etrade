'use client'
import { Fragment, useEffect, useState } from 'react'
import { OptionsShell, optCard } from '@/components/options/OptionsShell'

const STRAT: Record<string, string> = {
  long_call: 'Long Call',
  long_put: 'Long Put',
  bull_call_spread: 'Bull Call Spread',
  bear_put_spread: 'Bear Put Spread',
}

const EXIT_REASONS: Record<string, { label: string; color: string; bg: string }> = {
  take_profit: { label: 'Take Profit', color: '#26A69A', bg: 'rgba(38, 166, 154, 0.15)' },
  stop_loss: { label: 'Stop Loss', color: '#EF5350', bg: 'rgba(239, 83, 80, 0.15)' },
  forced_close_time: { label: 'Cierre por Tiempo', color: '#FFA726', bg: 'rgba(255, 167, 38, 0.15)' },
  signal_invalidation: { label: 'Inversión Señal', color: '#AB47BC', bg: 'rgba(171, 71, 188, 0.15)' },
  bad_data_close: { label: 'Dato Stale', color: '#888', bg: 'rgba(255, 255, 255, 0.1)' },
  manual_simulated: { label: 'Salida Manual', color: '#29B6F6', bg: 'rgba(41, 182, 246, 0.15)' },
}

const n = (v: any, d = 2) => (v === null || v === undefined ? '—' : Number(v).toFixed(d))

export default function OptionsPositions() {
  const [tab, setTab] = useState<'open' | 'closed'>('open')
  const [items, setItems] = useState<any[]>([])
  const [summary, setSummary] = useState<any>(null)
  const [sel, setSel] = useState<number | null>(null)
  const [detail, setDetail] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  const loadData = () => {
    setLoading(true)
    fetch(`/api/v1/options/positions?status=${tab}`)
      .then(r => r.json())
      .then(d => {
        setItems(d.items || [])
        setSummary(d.summary || null)
        setErr(d.error || null)
      })
      .catch(() => setErr('API no disponible'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadData()
  }, [tab])

  const openRow = async (id: number) => {
    if (sel === id) { setSel(null); return }
    setSel(id); setDetail(null)
    setDetail(await fetch(`/api/v1/options/positions/${id}`).then(r => r.json()).catch(() => null))
  }

  const handleManualExit = async (id: number) => {
    if (!confirm('¿Simular salida manual para esta posición paper?')) return
    try {
      const res = await fetch(`/api/v1/options/positions/${id}/simulate-exit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'manual_simulated' }),
      }).then(r => r.json())

      if (res.ok) {
        setMsg(`Posición cerrada exitosamente. P&L realizado: $${n(res.realized_pnl)}`)
        loadData()
      } else {
        setErr(res.detail || 'Error al simular salida')
      }
    } catch {
      setErr('Error de red al simular salida')
    }
  }

  const handleEvaluateExits = async () => {
    try {
      const res = await fetch('/api/v1/options/positions/evaluate-exits', { method: 'POST' }).then(r => r.json())
      if (res.ok) {
        const closed = res.result?.closed_count || 0
        setMsg(`Evaluación completada. Posiciones cerradas automáticamente: ${closed}`)
        loadData()
      }
    } catch {
      setErr('Error al evaluar salidas')
    }
  }

  const th: React.CSSProperties = { textAlign: 'left', color: '#666', fontSize: 10, textTransform: 'uppercase', padding: '8px 10px' }
  const td: React.CSSProperties = { color: '#AAA', fontSize: 12, padding: '8px 10px', borderTop: '1px solid rgba(255,255,255,0.04)' }
  const kpiCard: React.CSSProperties = { background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 8, padding: '10px 14px', flex: 1, minWidth: 140 }

  return (
    <OptionsShell title="Options Positions" active="/options/positions">
      {/* KPIs Header */}
      {summary && (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
          <div style={kpiCard}>
            <div style={{ color: '#888', fontSize: 11, textTransform: 'uppercase' }}>P&L No Realizado</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: summary.unrealized_pnl_usd >= 0 ? '#26A69A' : '#EF5350', marginTop: 4 }}>
              ${n(summary.unrealized_pnl_usd)}
            </div>
          </div>
          <div style={kpiCard}>
            <div style={{ color: '#888', fontSize: 11, textTransform: 'uppercase' }}>P&L Realizado Acumulado</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: summary.realized_pnl_usd >= 0 ? '#26A69A' : '#EF5350', marginTop: 4 }}>
              ${n(summary.realized_pnl_usd)}
            </div>
          </div>
          <div style={kpiCard}>
            <div style={{ color: '#888', fontSize: 11, textTransform: 'uppercase' }}>Posiciones Abiertas</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#FFF', marginTop: 4 }}>
              {summary.open_positions} <span style={{ fontSize: 12, color: '#888' }}>activas</span>
            </div>
          </div>
          <div style={kpiCard}>
            <div style={{ color: '#888', fontSize: 11, textTransform: 'uppercase' }}>Riesgo Abierto Activo</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#29B6F6', marginTop: 4 }}>
              ${n(summary.open_risk_usd, 0)} <span style={{ fontSize: 12, color: '#888' }}>/ ${n(summary.max_open_risk_usd, 0)}</span>
            </div>
          </div>
          <div style={kpiCard}>
            <div style={{ color: '#888', fontSize: 11, textTransform: 'uppercase' }}>Win Rate (Cerradas)</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#FFD700', marginTop: 4 }}>
              {summary.win_rate_pct}% <span style={{ fontSize: 12, color: '#888' }}>({summary.closed_positions} cerradas)</span>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <button
              onClick={handleEvaluateExits}
              style={{
                background: 'rgba(38, 166, 154, 0.2)',
                color: '#26A69A',
                border: '1px solid rgba(38, 166, 154, 0.4)',
                borderRadius: 6,
                padding: '8px 14px',
                fontSize: 12,
                cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              ↻ Evaluar Salidas
            </button>
          </div>
        </div>
      )}

      {msg && (
        <div style={{ background: 'rgba(38, 166, 154, 0.15)', border: '1px solid #26A69A', color: '#26A69A', padding: '8px 12px', borderRadius: 6, marginBottom: 12, fontSize: 12 }}>
          {msg}
        </div>
      )}
      {err && (
        <div style={{ background: 'rgba(239, 83, 80, 0.15)', border: '1px solid #EF5350', color: '#EF5350', padding: '8px 12px', borderRadius: 6, marginBottom: 12, fontSize: 12 }}>
          {err}
        </div>
      )}

      <div style={optCard}>
        {/* Selector de Pestaña */}
        <div style={{ display: 'flex', gap: 10, borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: 10, marginBottom: 12 }}>
          <button
            onClick={() => setTab('open')}
            style={{
              background: tab === 'open' ? 'rgba(38, 166, 154, 0.2)' : 'transparent',
              color: tab === 'open' ? '#26A69A' : '#888',
              border: tab === 'open' ? '1px solid rgba(38, 166, 154, 0.4)' : 'none',
              borderRadius: 6,
              padding: '6px 14px',
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Posiciones Abiertas ({summary?.open_positions ?? 0})
          </button>
          <button
            onClick={() => setTab('closed')}
            style={{
              background: tab === 'closed' ? 'rgba(41, 182, 246, 0.2)' : 'transparent',
              color: tab === 'closed' ? '#29B6F6' : '#888',
              border: tab === 'closed' ? '1px solid rgba(41, 182, 246, 0.4)' : 'none',
              borderRadius: 6,
              padding: '6px 14px',
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Historial / Cerradas ({summary?.closed_positions ?? 0})
          </button>
        </div>

        {loading && <div style={{ color: '#888', fontSize: 12, padding: '20px 0', textAlign: 'center' }}>Cargando posiciones…</div>}

        {!loading && items.length === 0 && (
          <div style={{ color: '#666', fontSize: 13, padding: '30px 0', textAlign: 'center' }}>
            {tab === 'open'
              ? 'No hay posiciones paper abiertas actualmente. Seleccione candidatas en "Opportunities" para simular entradas.'
              : 'No hay posiciones cerradas en el historial.'}
          </div>
        )}

        {!loading && items.length > 0 && (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={th}>Ticker</th>
                <th style={th}>Estrategia</th>
                <th style={th}>Dir.</th>
                <th style={th}>Qty</th>
                <th style={th}>Venc.</th>
                <th style={th}>Débito Entrada</th>
                {tab === 'open' ? (
                  <>
                    <th style={th}>Mark Actual</th>
                    <th style={th}>P&L No Realizado</th>
                    <th style={th}>Pérdida Máx</th>
                    <th style={th}>Acción</th>
                  </>
                ) : (
                  <>
                    <th style={th}>Crédito Salida</th>
                    <th style={th}>P&L Realizado</th>
                    <th style={th}>Motivo Salida</th>
                    <th style={th}>Fecha Cierre</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {items.map(p => (
                <Fragment key={p.id}>
                  <tr
                    onClick={() => openRow(p.id)}
                    style={{ cursor: 'pointer', background: sel === p.id ? 'rgba(255,255,255,0.03)' : 'transparent' }}
                  >
                    <td style={{ ...td, color: '#FFF', fontWeight: 700 }}>{p.symbol}</td>
                    <td style={td}>{STRAT[p.strategy_type] || p.strategy_type}</td>
                    <td style={td}>{p.direction === 'bullish' ? '▲' : '▼'}</td>
                    <td style={td}>{p.qty}</td>
                    <td style={td}>{p.expiry}</td>
                    <td style={td}>${n(p.entry_debit)}</td>

                    {tab === 'open' ? (
                      <>
                        <td style={td}>${n(p.last_mark_price)}</td>
                        <td style={{ ...td, color: (p.unrealized_pnl || 0) >= 0 ? '#26A69A' : '#EF5350', fontWeight: 700 }}>
                          ${n(p.unrealized_pnl)}
                        </td>
                        <td style={td}>${n(p.max_loss_total)}</td>
                        <td style={td}>
                          <button
                            onClick={e => { e.stopPropagation(); handleManualExit(p.id) }}
                            style={{
                              background: 'rgba(239, 83, 80, 0.15)',
                              color: '#EF5350',
                              border: '1px solid rgba(239, 83, 80, 0.3)',
                              borderRadius: 4,
                              padding: '3px 8px',
                              fontSize: 10,
                              cursor: 'pointer',
                              fontWeight: 600,
                            }}
                          >
                            Cerrar
                          </button>
                        </td>
                      </>
                    ) : (
                      <>
                        <td style={td}>${n(p.exit_credit)}</td>
                        <td style={{ ...td, color: (p.realized_pnl || 0) >= 0 ? '#26A69A' : '#EF5350', fontWeight: 700 }}>
                          ${n(p.realized_pnl)}
                        </td>
                        <td style={td}>
                          {p.exit_reason && EXIT_REASONS[p.exit_reason] ? (
                            <span style={{
                              display: 'inline-block',
                              padding: '2px 8px',
                              borderRadius: 4,
                              background: EXIT_REASONS[p.exit_reason].bg,
                              color: EXIT_REASONS[p.exit_reason].color,
                              fontSize: 10,
                              fontWeight: 600,
                            }}>
                              {EXIT_REASONS[p.exit_reason].label}
                            </span>
                          ) : (p.exit_reason || '—')}
                        </td>
                        <td style={td}>{p.exit_time ? new Date(p.exit_time).toLocaleDateString() : '—'}</td>
                      </>
                    )}
                  </tr>

                  {sel === p.id && (
                    <tr>
                      <td colSpan={10} style={{ ...td, background: 'rgba(255,255,255,0.02)', padding: '16px' }}>
                        {!detail ? 'Cargando detalle…' : (
                          <div>
                            <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', marginBottom: 12 }}>
                              <div>
                                <b style={{ color: '#FFF', fontSize: 13 }}>Fills de Entrada (Simulados Conservadores)</b>
                                <table style={{ marginTop: 6, fontSize: 11 }}>
                                  <thead>
                                    <tr>
                                      <th style={th}>Pierna</th>
                                      <th style={th}>Strike / Tipo</th>
                                      <th style={th}>Bid / Ask</th>
                                      <th style={th}>Fill Price</th>
                                      <th style={th}>Slippage</th>
                                      <th style={th}>Comisión</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {(detail.entry_fills || []).map((f: any, idx: number) => (
                                      <tr key={idx}>
                                        <td style={{ ...td, color: f.side === 'buy' ? '#26A69A' : '#EF5350' }}>{f.side?.toUpperCase()}</td>
                                        <td style={td}>{f.strike} {f.right}</td>
                                        <td style={td}>{n(f.bid)} / {n(f.ask)}</td>
                                        <td style={{ ...td, color: '#FFF', fontWeight: 600 }}>${n(f.fill_price, 4)}</td>
                                        <td style={td}>${n(f.slippage_applied, 4)}</td>
                                        <td style={td}>${n(f.fee_usd)}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>

                              {detail.exit_fills && detail.exit_fills.length > 0 && (
                                <div>
                                  <b style={{ color: '#FFF', fontSize: 13 }}>Fills de Salida (Liquidación)</b>
                                  <table style={{ marginTop: 6, fontSize: 11 }}>
                                    <thead>
                                      <tr>
                                        <th style={th}>Cierre</th>
                                        <th style={th}>Strike / Tipo</th>
                                        <th style={th}>Bid / Ask</th>
                                        <th style={th}>Fill Salida</th>
                                        <th style={th}>Slippage</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {detail.exit_fills.map((f: any, idx: number) => (
                                        <tr key={idx}>
                                          <td style={{ ...td, color: f.closing_side === 'buy' ? '#26A69A' : '#EF5350' }}>{f.closing_side?.toUpperCase()}</td>
                                          <td style={td}>{f.strike} {f.right}</td>
                                          <td style={td}>{n(f.bid)} / {n(f.ask)}</td>
                                          <td style={{ ...td, color: '#FFF', fontWeight: 600 }}>${n(f.fill_price, 4)}</td>
                                          <td style={td}>${n(f.slippage_applied, 4)}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              )}
                            </div>

                            <div style={{ color: '#888', fontSize: 11, lineHeight: 1.7, marginTop: 8 }}>
                              Inversión total inicial: <b style={{ color: '#DDD' }}>${n(detail.entry_total_invested)}</b> (débito ${n(detail.entry_debit)} × 100 × {detail.qty} + comisiones ${n(detail.entry_costs)})<br />
                              {detail.status === 'closed' && (
                                <>
                                  Total recuperado en salida: <b style={{ color: '#DDD' }}>${n(detail.exit_total_recovered)}</b> (crédito ${n(detail.exit_credit)} × 100 × {detail.qty} - comisiones ${n(detail.exit_costs)}) · P&L neto: <b style={{ color: detail.realized_pnl >= 0 ? '#26A69A' : '#EF5350' }}>${n(detail.realized_pnl)}</b><br />
                                </>
                              )}
                              Plan de salida: {Object.entries(detail.exit_plan || {}).map(([k, v]) => `${k}=${v}`).join(' · ')}
                            </div>

                            {detail.risk_events && detail.risk_events.length > 0 && (
                              <div style={{ marginTop: 10 }}>
                                <b style={{ color: '#FFA726', fontSize: 11 }}>Eventos de Riesgo / Auditoría:</b>
                                <ul style={{ margin: '4px 0 0', paddingLeft: 18, color: '#AAA', fontSize: 11 }}>
                                  {detail.risk_events.map((ev: any) => (
                                    <li key={ev.id}>
                                      [{new Date(ev.created_at).toLocaleTimeString()}] <b>{ev.event_type}</b>: {JSON.stringify(ev.details)}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </OptionsShell>
  )
}
