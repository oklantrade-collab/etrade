'use client'
import { Fragment, useEffect, useState, useRef } from 'react'
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

  // Modales
  const [showChart, setShowChart] = useState(false)
  const [selectedTicker, setSelectedTicker] = useState('')
  const [selectedModalPos, setSelectedModalPos] = useState<any>(null)

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
    if (!confirm('¿Cerrar / simular salida para esta posición de opción?')) return
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

  const handleDelete = async (id: number, sym: string) => {
    if (!confirm(`¿ELIMINAR registro de opción de ${sym} permanentemente?`)) return
    try {
      const res = await fetch(`/api/v1/options/positions/${id}`, { method: 'DELETE' })
      if (res.ok) {
        setItems(prev => prev.filter(p => p.id !== id))
        setMsg(`Posición de ${sym} eliminada permanentemente.`)
        loadData()
      } else {
        setErr('Error al eliminar la posición.')
      }
    } catch {
      setErr('Error de red al eliminar la posición.')
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

  const actionBtnStyle: React.CSSProperties = {
    padding: '4px 8px',
    borderRadius: '6px',
    fontSize: '11px',
    fontWeight: 700,
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'all 0.2s',
  }

  return (
    <OptionsShell title="Options Positions" active="/options/positions">
      {/* MODAL DETALLES */}
      {selectedModalPos && (
        <OptionDetailModal pos={selectedModalPos} onClose={() => setSelectedModalPos(null)} />
      )}

      {/* MODAL TRADINGVIEW */}
      {showChart && (
        <ChartModal symbol={selectedTicker} onClose={() => setShowChart(false)} />
      )}

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
            Posiciones Abiertas ({summary?.open_positions ?? items.filter(i => i.status === 'open').length})
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
            Historial / Cerradas ({summary?.closed_positions ?? items.filter(i => i.status === 'closed').length})
          </button>

          {tab === 'open' && (
            <span style={{
              fontSize: 11,
              padding: '4px 10px',
              borderRadius: 6,
              background: (summary?.open_positions ?? items.length) >= 3 ? 'rgba(239, 68, 68, 0.15)' : 'rgba(34, 197, 94, 0.15)',
              color: (summary?.open_positions ?? items.length) >= 3 ? '#EF4444' : '#22C55E',
              border: '1px solid currentColor',
              fontWeight: 700,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 5
            }}>
              🎯 Slots Activos: {summary?.open_positions ?? items.length} / 3 {(summary?.open_positions ?? items.length) >= 3 ? '(Cupo Lleno)' : `(${3 - (summary?.open_positions ?? items.length)} Libres)`}
            </span>
          )}
        </div>

        {loading && <div style={{ color: '#888', fontSize: 12, padding: '20px 0', textAlign: 'center' }}>Cargando posiciones…</div>}

        {!loading && items.length === 0 && (
          <div style={{ color: '#666', fontSize: 13, padding: '30px 0', textAlign: 'center' }}>
            {tab === 'open'
              ? 'No hay posiciones paper abiertas actualmente en cartera.'
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
                    <th style={{ ...th, textAlign: 'center' }}>Acciones</th>
                  </>
                ) : (
                  <>
                    <th style={th}>Crédito Salida</th>
                    <th style={th}>P&L Realizado</th>
                    <th style={th}>Motivo Salida</th>
                    <th style={th}>Fecha Cierre</th>
                    <th style={{ ...th, textAlign: 'center' }}>Acciones</th>
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
                    <td style={{ ...td, color: '#FFF', fontWeight: 700 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span>{p.symbol}</span>
                        {p.exit_plan?.partial_tp_taken && (
                          <span style={{ fontSize: 9, color: '#22C55E', background: 'rgba(34,197,94,0.15)', border: '1px solid rgba(34,197,94,0.3)', padding: '1px 5px', borderRadius: 4 }}>
                            ⚡ 50% TP TOMADO
                          </span>
                        )}
                      </div>
                      {p.exit_plan?.stop_loss_underlying > 0 && (
                        <div style={{
                          fontSize: 9,
                          color: (p.exit_plan?.be_locked || p.exit_plan?.trailing_sl_type === 'BE_LOCK_PLUS_1PCT') ? '#22C55E' : '#FFA726',
                          fontWeight: 600,
                          marginTop: 2
                        }}>
                          {(p.exit_plan?.be_locked || p.exit_plan?.trailing_sl_type === 'BE_LOCK_PLUS_1PCT') ? '🔒 BE +1% SL:' : '🛡️ SL:'} ${n(p.exit_plan.stop_loss_underlying)} ({p.exit_plan?.trailing_sl_type === 'BE_LOCK_PLUS_1PCT' ? '+1% LOCK' : p.exit_plan.trailing_sl_type})
                        </div>
                      )}
                    </td>
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
                        <td style={{ ...td, textAlign: 'center' }}>
                          <div style={{ display: 'flex', gap: '6px', justifyContent: 'center', alignItems: 'center' }}>
                            <button
                              onClick={e => { e.stopPropagation(); setSelectedTicker(p.symbol); setShowChart(true); }}
                              style={{ ...actionBtnStyle, background: 'rgba(56,189,248,0.1)', color: '#38BDF8', border: '1px solid rgba(56,189,248,0.2)' }}
                              title="Ver Gráfico Subyacente (TradingView)"
                            >
                              📊
                            </button>
                            <button
                              onClick={e => { e.stopPropagation(); setSelectedModalPos(p); }}
                              style={{ ...actionBtnStyle, background: 'rgba(255,255,255,0.05)', color: '#FFF', border: '1px solid rgba(255,255,255,0.15)' }}
                              title="Ver Detalles"
                            >
                              🔍
                            </button>
                            <button
                              onClick={e => { e.stopPropagation(); handleManualExit(p.id); }}
                              style={{ ...actionBtnStyle, background: 'rgba(38,166,154,0.15)', color: '#26A69A', border: '1px solid rgba(38,166,154,0.3)' }}
                              title="Cerrar Posición"
                            >
                              ✓
                            </button>
                            <button
                              onClick={e => { e.stopPropagation(); handleDelete(p.id, p.symbol); }}
                              style={{ ...actionBtnStyle, background: 'rgba(239,83,80,0.15)', color: '#EF5350', border: '1px solid rgba(239,83,80,0.3)' }}
                              title="Eliminar Registro"
                            >
                              🗑️
                            </button>
                          </div>
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
                            <div>
                              <span style={{
                                display: 'inline-block',
                                padding: '2px 8px',
                                borderRadius: 4,
                                background: EXIT_REASONS[p.exit_reason].bg,
                                color: EXIT_REASONS[p.exit_reason].color,
                                fontSize: 10,
                                fontWeight: 600,
                              }}>
                                {p.exit_plan?.detailed_exit_reason?.includes('be_lock') ? '🔒 SL Breakeven +1%' :
                                 p.exit_plan?.detailed_exit_reason?.includes('ema3_flat') ? '⚡ Agotamiento EMA3 1H' :
                                 p.exit_plan?.detailed_exit_reason?.includes('sipv_trend_flip_15m') ? '🔄 Giro SIPV 15m' :
                                 p.exit_plan?.detailed_exit_reason?.includes('sipv') ? '🔄 Giro SIPV 1H' :
                                 p.exit_plan?.detailed_exit_reason?.includes('ema_cross') ? '⚡ Cruce EMA 15m' :
                                 p.exit_plan?.detailed_exit_reason?.includes('rsi_climax') ? '🎯 Clímax RSI 1H' :
                                 p.exit_plan?.detailed_exit_reason?.includes('upper_6') ? '🎯 TP Upper 6' :
                                 p.exit_plan?.detailed_exit_reason?.includes('lower_6') ? '🎯 TP Lower 6' :
                                 p.exit_plan?.detailed_exit_reason?.includes('sl_underlying') ? '🛡️ SL Subyacente' :
                                 EXIT_REASONS[p.exit_reason].label}
                              </span>
                              {p.exit_plan?.detailed_exit_text && (
                                <div style={{ fontSize: 9, color: '#888', marginTop: 3, maxWidth: 220, lineHeight: 1.2 }}>
                                  {p.exit_plan.detailed_exit_text}
                                </div>
                              )}
                            </div>
                          ) : (p.exit_reason || '—')}
                        </td>
                        <td style={td}>{p.exit_time ? new Date(p.exit_time).toLocaleDateString() : '—'}</td>
                        <td style={{ ...td, textAlign: 'center' }}>
                          <div style={{ display: 'flex', gap: '6px', justifyContent: 'center', alignItems: 'center' }}>
                            <button
                              onClick={e => { e.stopPropagation(); setSelectedTicker(p.symbol); setShowChart(true); }}
                              style={{ ...actionBtnStyle, background: 'rgba(56,189,248,0.1)', color: '#38BDF8', border: '1px solid rgba(56,189,248,0.2)' }}
                              title="Ver Gráfico Subyacente (TradingView)"
                            >
                              📊
                            </button>
                            <button
                              onClick={e => { e.stopPropagation(); setSelectedModalPos(p); }}
                              style={{ ...actionBtnStyle, background: 'rgba(255,255,255,0.05)', color: '#FFF', border: '1px solid rgba(255,255,255,0.15)' }}
                              title="Ver Detalles"
                            >
                              🔍
                            </button>
                            <button
                              onClick={e => { e.stopPropagation(); handleDelete(p.id, p.symbol); }}
                              style={{ ...actionBtnStyle, background: 'rgba(239,83,80,0.15)', color: '#EF5350', border: '1px solid rgba(239,83,80,0.3)' }}
                              title="Eliminar Registro"
                            >
                              🗑️
                            </button>
                          </div>
                        </td>
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
                                <b style={{ color: '#FFF', fontSize: 13 }}>Fills de Entrada (Detalle Operativo)</b>
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

// ── COMPONENTES MODAL ────────────────────────────────────────────────────────

function DetailItem({ label, val, color }: { label: string; val: any; color?: string }) {
  return (
    <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px 14px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.04)' }}>
      <p style={{ margin: 0, fontSize: '10px', color: '#777', textTransform: 'uppercase', fontWeight: 800 }}>{label}</p>
      <p style={{ margin: '4px 0 0', fontSize: '14px', fontWeight: 700, color: color || '#FFF' }}>{val || '—'}</p>
    </div>
  )
}

function OptionDetailModal({ pos, onClose }: { pos: any; onClose: () => void }) {
  if (!pos) return null
  return (
    <div 
      onClick={onClose}
      style={{
        position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
        background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(8px)',
        zIndex: 1100, display: 'flex', alignItems: 'center', justifyContent: 'center',
        cursor: 'pointer'
      }}
    >
      <div 
        onClick={e => e.stopPropagation()}
        style={{
          background: '#12161F', width: '520px', maxHeight: '90vh', borderRadius: '20px',
          border: '1px solid rgba(255,255,255,0.1)', overflow: 'hidden',
          boxShadow: '0 25px 50px -12px rgba(0,0,0,0.5)',
          display: 'flex', flexDirection: 'column', cursor: 'default'
        }}
      >
        <div style={{ padding: '24px 28px', borderBottom: '1px solid rgba(255,255,255,0.06)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h2 style={{ fontSize: '22px', fontWeight: 900, margin: 0, color: '#FFF' }}>{pos.symbol}</h2>
              <span style={{
                background: pos.direction === 'bullish' ? 'rgba(38,166,154,0.15)' : 'rgba(239,83,80,0.15)',
                color: pos.direction === 'bullish' ? '#26A69A' : '#EF5350',
                padding: '3px 8px', borderRadius: 4, fontSize: 11, fontWeight: 700
              }}>
                {pos.direction === 'bullish' ? 'CALL / ALCISTA' : 'PUT / BAJISTA'}
              </span>
            </div>
            <p style={{ color: '#00C896', fontSize: '11px', fontWeight: 800, textTransform: 'uppercase', margin: '4px 0 0 0' }}>
              {STRAT[pos.strategy_type] || pos.strategy_type} · Vencimiento: {pos.expiry}
            </p>
          </div>
          <button onClick={onClose} style={{ background: 'rgba(255,255,255,0.05)', border: 'none', color: '#FFF', width: '32px', height: '32px', borderRadius: '50%', cursor: 'pointer', fontWeight: 900, fontSize: 18 }}>×</button>
        </div>

        <div style={{ padding: '24px 28px', overflowY: 'auto', flex: 1, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
          <DetailItem label="Subyacente" val={pos.symbol} color="#FFF" />
          <DetailItem label="Estrategia" val={STRAT[pos.strategy_type] || pos.strategy_type} color="#00C896" />
          <DetailItem label="Vencimiento" val={pos.expiry} color="#FFF" />
          <DetailItem label="Cantidad (Contratos)" val={`${pos.qty}x (100 sh/c)`} color="#FFF" />
          <DetailItem label="Débito Entrada" val={`$${n(pos.entry_debit)}`} color="#FFF" />
          <DetailItem label="Total Invertido" val={`$${n(pos.entry_total_invested)}`} color="#FFF" />
          <DetailItem label="Mark Actual" val={pos.last_mark_price ? `$${n(pos.last_mark_price)}` : '—'} color="#38BDF8" />
          <DetailItem label="P&L No Realizado" val={`$${n(pos.unrealized_pnl)}`} color={(pos.unrealized_pnl || 0) >= 0 ? '#26A69A' : '#EF5350'} />
          <DetailItem label="Pérdida Máxima" val={`$${n(pos.max_loss_total)}`} color="#EF5350" />
          <DetailItem label="Breakeven" val={pos.breakeven ? `$${n(pos.breakeven)}` : '—'} color="#FFA726" />
          <DetailItem label="Estado Posición" val={pos.status?.toUpperCase()} color={pos.status === 'open' ? '#26A69A' : '#888'} />
          <DetailItem label="Fecha Entrada" val={pos.entry_time ? new Date(pos.entry_time).toLocaleString() : '—'} color="#AAA" />
          {pos.status === 'closed' && (
            <>
              <DetailItem label="Fecha Cierre" val={pos.exit_time ? new Date(pos.exit_time).toLocaleString() : '—'} color="#AAA" />
              <DetailItem label="Crédito Salida" val={pos.exit_credit ? `$${n(pos.exit_credit)}` : '—'} color="#FFF" />
              <DetailItem label="P&L Realizado" val={`$${n(pos.realized_pnl)}`} color={(pos.realized_pnl || 0) >= 0 ? '#26A69A' : '#EF5350'} />
              <DetailItem label="Motivo Cierre" val={EXIT_REASONS[pos.exit_reason]?.label || pos.exit_reason || '—'} color="#FFA726" />
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function TradingViewWidget({ symbol }: { symbol: string }) {
  const containerId = `tv-chart-opt-${symbol}`;
  const containerRef = useRef<any>(null);
  const scriptLoaded = useRef(false);

  useEffect(() => {
    if (scriptLoaded.current) return;
    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/tv.js";
    script.async = true;
    script.onload = () => {
      if ((window as any).TradingView && containerRef.current) {
        const tvTimezone = typeof window !== "undefined" ? (localStorage.getItem("app_timezone") || "America/Lima") : "America/Lima";

        new (window as any).TradingView.widget({
          "autosize": true,
          "symbol": symbol,
          "interval": "15",
          "timezone": tvTimezone,
          "theme": "dark",
          "style": "1",
          "locale": "es",
          "toolbar_bg": "#161922",
          "enable_publishing": false,
          "allow_symbol_change": true,
          "container_id": containerId,
          "backgroundColor": "#0F1117",
          "gridColor": "rgba(255, 255, 255, 0.05)",
          "hide_side_toolbar": false,
          "studies": [
            "BB@tv-basicstudies",
            "MAExp@tv-basicstudies",
            "MASimple@tv-basicstudies"
          ],
          "studies_overrides": {
            "moving average.length": 3,
            "moving average.plot.color": "#E3FF00",
            "moving average.ma.color": "#E3FF00",
            "moving average.linewidth": 2
          },
          "overrides": {
            "mainSeriesProperties.style": 1,
          }
        });
      }
    };
    document.head.appendChild(script);
    scriptLoaded.current = true;
  }, [symbol, containerId]);

  return (
    <div ref={containerRef} id={containerId} style={{ height: '100%', width: '100%', borderRadius: '16px', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.1)' }} />
  );
}

function ChartModal({ symbol, onClose }: { symbol: string, onClose: () => void }) {
  return (
    <div style={{ position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', background: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1200, backdropFilter: 'blur(5px)' }}>
      <div style={{ background: '#0F1117', width: '95%', height: '92%', borderRadius: '24px', border: '1px solid #38BDF8', overflow: 'hidden', display: 'flex', flexDirection: 'column', boxShadow: '0 0 50px rgba(56,189,248,0.2)' }}>
        <div style={{ padding: '15px 25px', background: '#161922', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
          <div>
            <h3 style={{ margin: 0, color: '#FFF', fontSize: '16px', fontWeight: 900 }}>GRÁFICO TÉCNICO SUBYACENTE: {symbol}</h3>
            <span style={{ fontSize: '11px', color: '#38BDF8' }}>Acción origen de la opción en TradingView</span>
          </div>
          <button onClick={onClose} style={{ background: '#EF4444', border: 'none', color: '#FFF', padding: '6px 15px', borderRadius: '8px', fontSize: '10px', fontWeight: 900, cursor: 'pointer' }}>CERRAR GRÁFICO</button>
        </div>
        <div style={{ flex: 1, background: '#000' }}>
          <TradingViewWidget symbol={symbol} />
        </div>
      </div>
    </div>
  )
}
