'use client'
import { useEffect, useState } from 'react'
import { OptionsShell, optCard, useOptionsStatus } from '@/components/options/OptionsShell'
import UniverseCard from '@/components/options/UniverseCard'

export default function OptionsStatusPage() {
  const { status } = useOptionsStatus()
  const [g1, setG1] = useState<any>(null)
  useEffect(() => { fetch('/api/v1/options/g1').then(r => r.ok ? r.json() : null).then(setG1).catch(() => {}) }, [])
  const th: React.CSSProperties = { textAlign: 'left', color: '#555', fontSize: 10, textTransform: 'uppercase', padding: '6px 10px' }
  const td: React.CSSProperties = { color: '#AAA', fontSize: 12, padding: '6px 10px', borderTop: '1px solid rgba(255,255,255,0.04)' }
  return (
    <OptionsShell title="Data & Status" active="/options/status">
      <div style={optCard}>
        <div style={{ color: '#888', fontSize: 13, lineHeight: 1.9 }}>
          Modelo: <b style={{ color: '#CCC' }}>{status?.model_version ?? '…'}</b> · Modo: <b style={{ color: '#CCC' }}>{status?.execution_mode ?? '…'}</b> ·
          Worker: <b style={{ color: '#CCC' }}>{status?.worker?.state ?? '…'}</b> · Datos: <b style={{ color: '#CCC' }}>{status?.worker?.data_state ?? '…'}</b>
        </div>
      </div>
      <div style={optCard}>
        <div style={{ fontSize: 10, fontWeight: 900, color: '#555', textTransform: 'uppercase', letterSpacing: '0.2em', marginBottom: 12 }}>
          Gate G1 — Veredicto: {g1?.verdict ?? '…'}
        </div>
        {g1 && g1.sessions.length === 0 && <div style={{ color: '#666', fontSize: 13 }}>Aún no hay sesiones medidas. Ejecute <code>python -m app.options.g1_probe --from-apex --save</code> durante el horario de mercado.</div>}
        {g1 && g1.sessions.length > 0 && (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead><tr><th style={th}>Fecha</th><th style={th}>Evaluados</th><th style={th}>Optionables</th><th style={th}>Viables</th><th style={th}>Datos</th><th style={th}>Resultado</th></tr></thead>
            <tbody>{g1.sessions.map((s: any) => (
              <tr key={s.session_date}>
                <td style={td}>{s.session_date}</td><td style={td}>{s.symbols_evaluated}</td><td style={td}>{s.optionable_count}</td>
                <td style={td}>{s.viable_candidates}</td><td style={td}>{s.market_data_type}</td>
                <td style={{ ...td, color: s.session_pass ? '#26A69A' : '#EF5350' }}>{s.session_pass ? 'PASA' : 'NO PASA'}</td>
              </tr>))}</tbody>
          </table>
        )}
      </div>
      <UniverseCard />
    </OptionsShell>
  )
}
