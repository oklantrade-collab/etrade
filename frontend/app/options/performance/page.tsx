'use client'
import { useEffect, useState } from 'react'
import { OptionsShell, optCard } from '@/components/options/OptionsShell'

const n = (v: any, d = 2) => (v === null || v === undefined ? '—' : Number(v).toFixed(d))

function EquityChart({ data }: { data: any[] }) {
  if (!data?.length) return <div style={{ color: '#666', fontSize: 12, padding: '20px 0', textAlign: 'center' }}>Sin datos de curva de equidad aún (se requieren operaciones cerradas).</div>

  const W = 680, H = 160, P = 30
  const xs = data.map(d => d.trade_num)
  const ys = data.map(d => d.cumulative_pnl)
  const x0 = 1, x1 = Math.max(data.length, 5)
  const yMin = Math.min(...ys, 0), yMax = Math.max(...ys, 10)

  const sx = (x: number) => P + ((x - x0) / (x1 - x0 || 1)) * (W - 2 * P)
  const sy = (y: number) => H - P - ((y - yMin) / (yMax - yMin || 1)) * (H - 2 * P)

  const path = data.map((d, i) => `${i ? 'L' : 'M'}${sx(d.trade_num).toFixed(1)},${sy(d.cumulative_pnl).toFixed(1)}`).join(' ')
  const lastY = ys[ys.length - 1]

  return (
    <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: 8, padding: 12, border: '1px solid rgba(255,255,255,0.05)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <b style={{ color: '#CCC', fontSize: 12 }}>Curva de Equidad Acumulada (P&L Realizado USD)</b>
        <span style={{ fontSize: 11, color: lastY >= 0 ? '#26A69A' : '#EF5350', fontWeight: 700 }}>
          ${n(lastY)} total
        </span>
      </div>
      <svg width={W} height={H} style={{ width: '100%', height: 'auto', display: 'block' }} viewBox={`0 0 ${W} ${H}`}>
        {/* Zero line */}
        <line x1={P} x2={W - P} y1={sy(0)} y2={sy(0)} stroke="#444" strokeDasharray="3 3" />
        <path d={path} fill="none" stroke={lastY >= 0 ? '#26A69A' : '#EF5350'} strokeWidth={2.5} />
        {data.map((d, idx) => (
          <circle key={idx} cx={sx(d.trade_num)} cy={sy(d.cumulative_pnl)} r={3} fill={d.pnl >= 0 ? '#26A69A' : '#EF5350'} />
        ))}
        <text x={P} y={H - 8} fill="#666" fontSize={10}>Trade 1</text>
        <text x={W - P - 40} y={H - 8} fill="#666" fontSize={10}>Trade {data.length}</text>
        <text x={W - P - 60} y={sy(0) - 4} fill="#888" fontSize={10}>$0.00</text>
      </svg>
    </div>
  )
}

export default function OptionsPerformance() {
  const [summary, setSummary] = useState<any>(null)
  const [calib, setCalib] = useState<any>(null)
  const [g3, setG3] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      fetch('/api/v1/options/performance/summary').then(r => r.json()),
      fetch('/api/v1/options/performance/calibration').then(r => r.json()),
      fetch('/api/v1/options/g3').then(r => r.json()),
    ])
      .then(([s, c, g]) => {
        setSummary(s)
        setCalib(c)
        setG3(g)
      })
      .catch(() => setErr('API no disponible'))
      .finally(() => setLoading(false))
  }, [])

  const th: React.CSSProperties = { textAlign: 'left', color: '#666', fontSize: 10, textTransform: 'uppercase', padding: '6px 10px' }
  const td: React.CSSProperties = { color: '#AAA', fontSize: 12, padding: '6px 10px', borderTop: '1px solid rgba(255,255,255,0.04)' }
  const kpiCard: React.CSSProperties = { background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 8, padding: '10px 14px', flex: 1, minWidth: 140 }

  return (
    <OptionsShell title="Options Performance" active="/options/performance">
      {/* Banner de Evaluación Gate G3 */}
      {g3 && (
        <div style={{
          background: g3.verdict === 'GO' ? 'rgba(38, 166, 154, 0.12)' : 'rgba(255, 167, 38, 0.1)',
          border: `1px solid ${g3.verdict === 'GO' ? '#26A69A' : 'rgba(255, 167, 38, 0.3)'}`,
          borderRadius: 8,
          padding: '14px 18px',
          marginBottom: 16,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <div>
              <b style={{ color: '#FFF', fontSize: 14 }}>Gate G3: Evaluación de Shadow Forward Paper</b>
              <div style={{ color: '#AAA', fontSize: 11, marginTop: 2 }}>
                Evaluación continua de los 5 requisitos para autorizar transición de fase (§17 y §18).
              </div>
            </div>
            <div style={{
              padding: '4px 12px',
              borderRadius: 6,
              background: g3.verdict === 'GO' ? '#26A69A' : (g3.verdict === 'NO-GO' ? '#EF5350' : 'rgba(255, 167, 38, 0.3)'),
              color: '#FFF',
              fontWeight: 800,
              fontSize: 12,
            }}>
              VEREDICTO: {g3.verdict}
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 10 }}>
            {(g3.criteria || []).map((c: any) => (
              <div key={c.id} style={{ background: 'rgba(0,0,0,0.2)', padding: 8, borderRadius: 6, fontSize: 11 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <b style={{ color: '#DDD' }}>{c.name}</b>
                  <span style={{ color: c.status === 'PASS' ? '#26A69A' : (c.status === 'FAIL' ? '#EF5350' : '#FFA726'), fontWeight: 700 }}>
                    {c.status}
                  </span>
                </div>
                <div style={{ color: '#888', marginTop: 4 }}>Actual: <b style={{ color: '#FFF' }}>{c.current}</b></div>
                <div style={{ color: '#666', fontSize: 10 }}>Req: {c.required}</div>
              </div>
            ))}
          </div>

          {g3.recommendations && g3.recommendations.length > 0 && (
            <div style={{ marginTop: 10, fontSize: 11, color: '#FFA726' }}>
              <b>Recomendaciones:</b> {g3.recommendations.join(' · ')}
            </div>
          )}
        </div>
      )}

      {/* KPI Summary Cards */}
      {summary && (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
          <div style={kpiCard}>
            <div style={{ color: '#888', fontSize: 11, textTransform: 'uppercase' }}>P&L Neto Realizado</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: summary.net_pnl_usd >= 0 ? '#26A69A' : '#EF5350', marginTop: 4 }}>
              ${n(summary.net_pnl_usd)}
            </div>
          </div>
          <div style={kpiCard}>
            <div style={{ color: '#888', fontSize: 11, textTransform: 'uppercase' }}>Win Rate</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#29B6F6', marginTop: 4 }}>
              {n(summary.win_rate_pct, 1)}% <span style={{ fontSize: 11, color: '#888' }}>({summary.winning_trades}/{summary.total_trades})</span>
            </div>
          </div>
          <div style={kpiCard}>
            <div style={{ color: '#888', fontSize: 11, textTransform: 'uppercase' }}>Profit Factor</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: summary.profit_factor >= 1.5 ? '#26A69A' : '#FFA726', marginTop: 4 }}>
              {n(summary.profit_factor)}
            </div>
          </div>
          <div style={kpiCard}>
            <div style={{ color: '#888', fontSize: 11, textTransform: 'uppercase' }}>Expectancy / Trade</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: summary.expectancy_usd >= 0 ? '#26A69A' : '#EF5350', marginTop: 4 }}>
              ${n(summary.expectancy_usd)}
            </div>
          </div>
          <div style={kpiCard}>
            <div style={{ color: '#888', fontSize: 11, textTransform: 'uppercase' }}>Max Drawdown</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#EF5350', marginTop: 4 }}>
              ${n(summary.max_drawdown_usd)}
            </div>
          </div>
        </div>
      )}

      {/* Curva de Equidad Acumulada */}
      {summary && <div style={{ marginBottom: 16 }}><EquityChart data={summary.equity_curve || []} /></div>}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Calibración de Probabilidad y Alpha */}
        <div style={optCard}>
          <b style={{ color: '#FFF', fontSize: 13 }}>Calibración de Probabilidad (Reliability Diagram)</b>
          <div style={{ color: '#777', fontSize: 11, marginTop: 2, marginBottom: 10 }}>
            Compara la probabilidad teórica (POP) estimada a la entrada con la frecuencia observada de éxito (§11).
          </div>

          {calib?.calibration?.bins && (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead>
                <tr>
                  <th style={th}>Tramo POP</th>
                  <th style={th}>Trades</th>
                  <th style={th}>POP Media</th>
                  <th style={th}>Win Rate Obs.</th>
                  <th style={th}>Error Calibr.</th>
                </tr>
              </thead>
              <tbody>
                {calib.calibration.bins.map((b: any) => (
                  <tr key={b.bin_index}>
                    <td style={{ ...td, color: '#FFF' }}>{b.range}</td>
                    <td style={td}>{b.trades_count}</td>
                    <td style={td}>{n(b.mean_theoretical_pop, 1)}%</td>
                    <td style={td}>{b.observed_win_pct != null ? `${n(b.observed_win_pct, 1)}%` : '—'}</td>
                    <td style={{ ...td, color: b.calibration_error_pts <= 10 ? '#26A69A' : '#EF5350' }}>
                      ±{n(b.calibration_error_pts, 1)} pts
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {calib?.alpha_estimation && (
            <div style={{ marginTop: 12, background: 'rgba(255,255,255,0.02)', padding: 10, borderRadius: 6, fontSize: 11, lineHeight: 1.7 }}>
              <b style={{ color: '#29B6F6' }}>Estimación Empírica de Alpha (Drift APEX)</b><br />
              Prior teórico: α={calib.alpha_estimation.prior_alpha} · Estimado empírico: <b style={{ color: '#FFF' }}>α={calib.alpha_estimation.estimated_alpha}</b> (confianza: {calib.alpha_estimation.confidence})<br />
              Tasa observada en {calib.alpha_estimation.samples_count} operaciones: {calib.alpha_estimation.observed_win_rate_pct}%
            </div>
          )}
        </div>

        {/* Desglose por Estrategia y Sensibilidad a Slippage */}
        <div style={optCard}>
          <b style={{ color: '#FFF', fontSize: 13 }}>Rendimiento por Estrategia</b>
          {summary?.by_strategy && Object.keys(summary.by_strategy).length > 0 ? (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11, marginTop: 10 }}>
              <thead>
                <tr>
                  <th style={th}>Estrategia</th>
                  <th style={th}>Trades</th>
                  <th style={th}>Win Rate</th>
                  <th style={th}>P&L Neto</th>
                  <th style={th}>Expectancy</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(summary.by_strategy).map(([st, data]: any) => (
                  <tr key={st}>
                    <td style={{ ...td, color: '#FFF' }}>{st}</td>
                    <td style={td}>{data.trades}</td>
                    <td style={td}>{data.win_rate_pct}%</td>
                    <td style={{ ...td, color: data.net_pnl >= 0 ? '#26A69A' : '#EF5350' }}>${n(data.net_pnl)}</td>
                    <td style={td}>${n(data.expectancy)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div style={{ color: '#666', fontSize: 12, padding: '16px 0' }}>Sin trades cerrados aún.</div>
          )}

          {summary?.slippage_sensitivity && (
            <div style={{ marginTop: 14, background: 'rgba(255,255,255,0.02)', padding: 10, borderRadius: 6, fontSize: 11, lineHeight: 1.7 }}>
              <b style={{ color: '#FFA726' }}>Sensibilidad a Slippage de Ejecución</b><br />
              Coste base de slippage: ${n(summary.slippage_sensitivity.base_slippage_usd)}<br />
              P&L si el slippage fuera 2×: <b style={{ color: summary.slippage_sensitivity.pnl_with_2x_slippage >= 0 ? '#26A69A' : '#EF5350' }}>${n(summary.slippage_sensitivity.pnl_with_2x_slippage)}</b><br />
              P&L si el slippage fuera 3× (adverso): <b style={{ color: summary.slippage_sensitivity.pnl_with_3x_slippage >= 0 ? '#26A69A' : '#EF5350' }}>${n(summary.slippage_sensitivity.pnl_with_3x_slippage)}</b>
            </div>
          )}
        </div>
      </div>
    </OptionsShell>
  )
}
