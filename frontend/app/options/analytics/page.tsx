'use client'
import { useEffect, useState } from 'react'
import { OptionsShell, optCard } from '@/components/options/OptionsShell'

export default function OptionsAnalyticsPage() {
  const [greeks, setGreeks] = useState<any>(null)
  const [counterfactuals, setCounterfactuals] = useState<any>(null)
  const [replayId, setReplayId] = useState('')
  const [replayResult, setReplayResult] = useState<any>(null)
  const [replayLoading, setReplayLoading] = useState(false)
  const [loading, setLoading] = useState(true)

  const loadData = async () => {
    setLoading(true)
    try {
      const [gRes, cRes] = await Promise.all([
        fetch('/api/v1/options/analytics/portfolio-greeks').then(r => r.json()),
        fetch('/api/v1/options/analytics/counterfactual-book?limit=30').then(r => r.json()),
      ])
      setGreeks(gRes)
      setCounterfactuals(cRes)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const handleReplay = async () => {
    if (!replayId.trim()) return
    setReplayLoading(true)
    setReplayResult(null)
    try {
      const res = await fetch(`/api/v1/options/evaluations/${replayId.trim()}/replay`, { method: 'POST' })
      const data = await res.json()
      setReplayResult(data)
    } catch (e: any) {
      setReplayResult({ ok: false, error: e.message })
    } finally {
      setReplayLoading(false)
    }
  }

  const totals = greeks?.portfolio_totals || {}

  return (
    <OptionsShell title="Analítica de Cartera y Griegas Netas" active="/options/analytics">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* Soft alerts */}
        {greeks?.alerts?.length > 0 && (
          <div style={{
            padding: '12px 16px', borderRadius: 10,
            background: 'rgba(255,167,38,0.1)', border: '1px solid rgba(255,167,38,0.4)',
            color: '#FFA726', fontSize: 13,
          }}>
            <div style={{ fontWeight: 800, marginBottom: 4 }}>⚠️ Alertas blandas de concentración de griegas (Doc §8.3):</div>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {greeks.alerts.map((a: string, idx: number) => <li key={idx}>{a}</li>)}
            </ul>
          </div>
        )}

        {/* 1. Portfolio Net Greeks Dashboard */}
        <div style={optCard}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <div>
              <h3 style={{ margin: 0, fontSize: 18, fontWeight: 900, color: '#FFF' }}>
                Griegas Netas Agregadas de la Cartera (Doc §8.3)
              </h3>
              <span style={{ fontSize: 11, color: '#888' }}>
                Posiciones abiertas: {totals.open_positions ?? 0} | Multiplicador estándar M=100 | Fuente: MODEL (Black-Scholes analítico)
              </span>
            </div>
            <button
              onClick={loadData}
              style={{
                padding: '6px 14px', borderRadius: 8, background: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.1)', color: '#FFF', fontSize: 12, cursor: 'pointer',
              }}
            >
              Refrescar Griegas
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
            <div style={{ padding: 14, borderRadius: 10, background: 'rgba(0,0,0,0.25)', border: '1px solid rgba(255,255,255,0.05)' }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#888', textTransform: 'uppercase' }}>Delta Neto (Acciones)</div>
              <div style={{ fontSize: 22, fontWeight: 900, color: (totals.delta_shares || 0) >= 0 ? '#26A69A' : '#EF5350', marginTop: 4 }}>
                {totals.delta_shares ? `${totals.delta_shares > 0 ? '+' : ''}${totals.delta_shares}` : '0.00'}
              </div>
              <div style={{ fontSize: 11, color: '#666', marginTop: 2 }}>Eq. acciones subyacentes</div>
            </div>

            <div style={{ padding: 14, borderRadius: 10, background: 'rgba(0,0,0,0.25)', border: '1px solid rgba(255,255,255,0.05)' }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#888', textTransform: 'uppercase' }}>Delta Neto (USD)</div>
              <div style={{ fontSize: 22, fontWeight: 900, color: (totals.delta_usd || 0) >= 0 ? '#26A69A' : '#EF5350', marginTop: 4 }}>
                {totals.delta_usd ? `$${totals.delta_usd.toLocaleString()}` : '$0.00'}
              </div>
              <div style={{ fontSize: 11, color: '#666', marginTop: 2 }}>Sesgo direccional ponderado</div>
            </div>

            <div style={{ padding: 14, borderRadius: 10, background: 'rgba(0,0,0,0.25)', border: '1px solid rgba(255,255,255,0.05)' }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#888', textTransform: 'uppercase' }}>Gamma Neta</div>
              <div style={{ fontSize: 22, fontWeight: 900, color: '#42A5F5', marginTop: 4 }}>
                {totals.gamma ? totals.gamma.toFixed(4) : '0.0000'}
              </div>
              <div style={{ fontSize: 11, color: '#666', marginTop: 2 }}>Curvatura del delta</div>
            </div>

            <div style={{ padding: 14, borderRadius: 10, background: 'rgba(0,0,0,0.25)', border: '1px solid rgba(255,255,255,0.05)' }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#888', textTransform: 'uppercase' }}>Vega Neta ($/punto IV)</div>
              <div style={{ fontSize: 22, fontWeight: 900, color: (totals.vega_point || 0) >= 0 ? '#AB47BC' : '#EF5350', marginTop: 4 }}>
                {totals.vega_point ? `$${totals.vega_point > 0 ? '+' : ''}${totals.vega_point}` : '$0.00'}
              </div>
              <div style={{ fontSize: 11, color: '#666', marginTop: 2 }}>P&L por +1% IV</div>
            </div>

            <div style={{ padding: 14, borderRadius: 10, background: 'rgba(0,0,0,0.25)', border: '1px solid rgba(255,255,255,0.05)' }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#888', textTransform: 'uppercase' }}>Theta Neta ($/día)</div>
              <div style={{ fontSize: 22, fontWeight: 900, color: (totals.theta_day || 0) >= 0 ? '#26A69A' : '#EF5350', marginTop: 4 }}>
                {totals.theta_day ? `$${totals.theta_day > 0 ? '+' : ''}${totals.theta_day}` : '$0.00'}
              </div>
              <div style={{ fontSize: 11, color: '#666', marginTop: 2 }}>Decaimiento temporal diario</div>
            </div>
          </div>

          {/* Posiciones abiertas desglose de griegas */}
          {greeks?.positions?.length > 0 && (
            <div style={{ marginTop: 18, overflowX: 'auto' }}>
              <div style={{ fontSize: 12, fontWeight: 800, color: '#aaa', marginBottom: 8, textTransform: 'uppercase' }}>
                Contribución por Posición Abierta:
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ color: '#777', borderBottom: '1px solid rgba(255,255,255,0.08)', textAlign: 'left' }}>
                    <th style={{ padding: '6px 8px' }}>Símbolo</th>
                    <th style={{ padding: '6px 8px' }}>Estrategia</th>
                    <th style={{ padding: '6px 8px' }}>Dirección</th>
                    <th style={{ padding: '6px 8px' }}>Delta ($USD)</th>
                    <th style={{ padding: '6px 8px' }}>Gamma</th>
                    <th style={{ padding: '6px 8px' }}>Vega ($/pt)</th>
                    <th style={{ padding: '6px 8px' }}>Theta ($/día)</th>
                  </tr>
                </thead>
                <tbody>
                  {greeks.positions.map((p: any) => (
                    <tr key={p.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                      <td style={{ padding: '8px', fontWeight: 800, color: '#FFF' }}>{p.symbol}</td>
                      <td style={{ padding: '8px', color: '#ccc' }}>{p.strategy}</td>
                      <td style={{ padding: '8px', color: p.direction === 'bullish' ? '#26A69A' : '#EF5350', fontWeight: 700 }}>{p.direction}</td>
                      <td style={{ padding: '8px', color: '#FFF' }}>${p.delta_usd}</td>
                      <td style={{ padding: '8px', color: '#aaa' }}>{p.gamma}</td>
                      <td style={{ padding: '8px', color: '#aaa' }}>${p.vega_point}</td>
                      <td style={{ padding: '8px', color: p.theta_day >= 0 ? '#26A69A' : '#EF5350' }}>${p.theta_day}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* 2. Deterministic Replay Evaluation Tool */}
        <div style={optCard}>
          <h3 style={{ margin: '0 0 8px 0', fontSize: 16, fontWeight: 900, color: '#FFF' }}>
            Herramienta de Replay Determinista (§13.3)
          </h3>
          <p style={{ color: '#888', fontSize: 12, margin: '0 0 14px 0' }}>
            Permite reejecutar la valoración matemática y el score de cualquier evaluación guardada en la base de datos para certificar reproducibilidad bit a bit sin sesgo de retroalimentación.
          </p>

          <div style={{ display: 'flex', gap: 10, maxWidth: 500, marginBottom: 14 }}>
            <input
              type="number"
              placeholder="ID de la candidata (opt_candidates.id)..."
              value={replayId}
              onChange={e => setReplayId(e.target.value)}
              style={{
                flex: 1, padding: '8px 12px', borderRadius: 8, background: 'rgba(0,0,0,0.3)',
                border: '1px solid rgba(255,255,255,0.1)', color: '#FFF', fontSize: 12,
              }}
            />
            <button
              onClick={handleReplay}
              disabled={replayLoading || !replayId}
              style={{
                padding: '8px 16px', borderRadius: 8, background: '#26A69A', border: 'none',
                color: '#FFF', fontWeight: 800, fontSize: 12, cursor: 'pointer', opacity: replayLoading ? 0.6 : 1,
              }}
            >
              {replayLoading ? 'Reejecutando...' : 'Reejecutar Evaluación'}
            </button>
          </div>

          {replayResult && (
            <div style={{
              padding: 14, borderRadius: 10,
              background: replayResult.ok && replayResult.replay?.matches ? 'rgba(38,166,154,0.08)' : 'rgba(239,83,80,0.08)',
              border: `1px solid ${replayResult.ok && replayResult.replay?.matches ? '#26A69A' : '#EF5350'}`,
            }}>
              {replayResult.ok ? (
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                    <span style={{
                      padding: '3px 10px', borderRadius: 12, fontWeight: 900, fontSize: 11,
                      background: replayResult.replay?.matches ? '#26A69A' : '#EF5350', color: '#FFF',
                    }}>
                      {replayResult.replay?.matches ? '✓ REPLAY DETERMINISTA CONFIRMADO (0 DIFF)' : '⚠️ DISCREPANCIA DETECTADA'}
                    </span>
                    <span style={{ fontSize: 12, color: '#FFF', fontWeight: 700 }}>
                      Score Original: {replayResult.replay?.original_score} | Reejecutado: {replayResult.replay?.replayed_score}
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: '#bbb' }}>
                    Cobertura de datos: {(replayResult.replay?.coverage * 100).toFixed(0)}% | Versión del modelo: {replayResult.replay?.breakdown?.model_version}
                  </div>
                </div>
              ) : (
                <div style={{ color: '#EF5350', fontSize: 13 }}>
                  Error al reejecutar: {replayResult.error || replayResult.detail}
                </div>
              )}
            </div>
          )}
        </div>

        {/* 3. Counterfactual Book vs Paper Portfolio */}
        <div style={optCard}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 900, color: '#FFF' }}>
                Libro Contrafactual vs Cartera Paper (Doc §12 y §14)
              </h3>
              <span style={{ fontSize: 11, color: '#888' }}>
                Registra candidatas con EV positivo no seleccionadas para medir el coste de oportunidad de los filtros ADUANA
              </span>
            </div>
            <div style={{ display: 'flex', gap: 8, fontSize: 12 }}>
              <span style={{ padding: '4px 10px', borderRadius: 8, background: 'rgba(38,166,154,0.1)', color: '#26A69A', fontWeight: 700 }}>
                Abiertas: {counterfactuals?.opened_count ?? 0}
              </span>
              <span style={{ padding: '4px 10px', borderRadius: 8, background: 'rgba(255,255,255,0.06)', color: '#aaa', fontWeight: 700 }}>
                Contrafactuales: {counterfactuals?.counterfactual_count ?? 0}
              </span>
            </div>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ color: '#777', borderBottom: '1px solid rgba(255,255,255,0.08)', textAlign: 'left' }}>
                  <th style={{ padding: '8px 10px' }}>Símbolo</th>
                  <th style={{ padding: '8px 10px' }}>Estrategia</th>
                  <th style={{ padding: '8px 10px' }}>Dirección</th>
                  <th style={{ padding: '8px 10px' }}>EV Neto</th>
                  <th style={{ padding: '8px 10px' }}>EV Ratio</th>
                  <th style={{ padding: '8px 10px' }}>Score</th>
                  <th style={{ padding: '8px 10px' }}>Robustez (ev_robust)</th>
                  <th style={{ padding: '8px 10px' }}>Estado / Motivo Rechazo</th>
                </tr>
              </thead>
              <tbody>
                {counterfactuals?.counterfactual_sample?.length === 0 ? (
                  <tr>
                    <td colSpan={8} style={{ padding: 16, textAlign: 'center', color: '#666' }}>
                      Sin candidatas contrafactuales registradas recientemente.
                    </td>
                  </tr>
                ) : (
                  counterfactuals?.counterfactual_sample?.map((c: any) => (
                    <tr key={c.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                      <td style={{ padding: '8px 10px', fontWeight: 800, color: '#FFF' }}>{c.symbol}</td>
                      <td style={{ padding: '8px 10px', color: '#ccc' }}>{c.strategy}</td>
                      <td style={{ padding: '8px 10px', color: c.direction === 'bullish' ? '#26A69A' : '#EF5350' }}>{c.direction}</td>
                      <td style={{ padding: '8px 10px', color: '#FFF' }}>{c.ev_view_net ? `$${c.ev_view_net}` : '-'}</td>
                      <td style={{ padding: '8px 10px', color: '#aaa' }}>{c.ev_ratio ? `${(c.ev_ratio * 100).toFixed(1)}%` : '-'}</td>
                      <td style={{ padding: '8px 10px', fontWeight: 700, color: '#FFF' }}>{c.score || '-'}</td>
                      <td style={{ padding: '8px 10px' }}>
                        <span style={{
                          padding: '2px 8px', borderRadius: 6, fontSize: 11, fontWeight: 800,
                          background: c.ev_robust ? 'rgba(38,166,154,0.15)' : 'rgba(255,255,255,0.05)',
                          color: c.ev_robust ? '#26A69A' : '#777',
                        }}>
                          {c.ev_robust ? 'ROBUSTO' : 'NO ROBUSTO'}
                        </span>
                      </td>
                      <td style={{ padding: '8px 10px', color: '#FFA726', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {c.rejection_reasons?.length > 0 ? c.rejection_reasons.join('; ') : c.eligibility_status}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </OptionsShell>
  )
}
