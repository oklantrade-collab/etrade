'use client'
import Link from 'next/link'
import { ReactNode, useEffect, useState } from 'react'

export const OPTIONS_UI_ENABLED = process.env.NEXT_PUBLIC_OPTIONS_ENABLED !== 'false'

const card: React.CSSProperties = {
  background: 'rgba(17, 24, 39, 0.4)', backdropFilter: 'blur(12px)',
  border: '1px solid rgba(255,255,255,0.04)', borderRadius: 16, padding: 24,
}
export const optCard = card

export function ComingSoon() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '70vh', gap: 24 }}>
      <div style={{ fontSize: 80 }}>🎯</div>
      <h2 style={{ fontSize: 36, fontWeight: 900, color: '#FFF', margin: 0, fontStyle: 'italic' }}>Opciones</h2>
      <div style={{ padding: '6px 20px', borderRadius: 20, background: 'rgba(171,71,188,0.12)', border: '1px solid rgba(171,71,188,0.3)', color: '#AB47BC', fontSize: 11, fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.15em' }}>
        Módulo desactivado
      </div>
      <p style={{ color: '#666', fontSize: 14, maxWidth: 500, textAlign: 'center', lineHeight: 1.7 }}>
        El módulo APEX Options está en construcción por fases (solo Paper Trading).
        Actívelo con <code>NEXT_PUBLIC_OPTIONS_ENABLED=true</code> en el frontend y <code>OPTIONS_ENABLED=true</code> en el backend.
      </p>
      <Link href="/stocks/dashboard" style={{ padding: '12px 32px', borderRadius: 8, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)', color: '#888', fontSize: 13, fontWeight: 700, textDecoration: 'none' }}>
        ← Volver a Stocks
      </Link>
    </div>
  )
}

const NAV = [
  { href: '/options', label: 'Dashboard' },
  { href: '/options/universe', label: 'Universe' },
  { href: '/options/opportunities', label: 'Opportunities' },
  { href: '/options/positions', label: 'Positions' },
  { href: '/options/performance', label: 'Performance' },
  { href: '/options/status', label: 'Data & Status' },
]

export function useOptionsStatus() {
  const [status, setStatus] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const load = () => fetch('/api/v1/options/status').then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(setStatus).catch(e => setError(String(e)))
    load()
    const t = setInterval(load, 30000)
    return () => clearInterval(t)
  }, [])
  return { status, error }
}

export function OptionsShell({ title, active, children }: { title: string; active: string; children: ReactNode }) {
  const { status } = useOptionsStatus()
  if (!OPTIONS_UI_ENABLED) return <ComingSoon />
  const ds = status?.worker?.data_state ?? 'UNKNOWN'
  const dsColor = ds === 'LIVE' ? '#26A69A' : ds === 'UNKNOWN' ? '#888' : '#FFA726'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <h2 style={{ fontSize: 28, fontWeight: 900, color: '#FFF', margin: 0, fontStyle: 'italic' }}>{title}</h2>
        <span style={{ padding: '4px 12px', borderRadius: 12, background: 'rgba(38,166,154,0.12)', border: '1px solid rgba(38,166,154,0.4)', color: '#26A69A', fontSize: 11, fontWeight: 900 }}>PAPER</span>
        <span style={{ padding: '4px 12px', borderRadius: 12, border: `1px solid ${dsColor}`, color: dsColor, fontSize: 11, fontWeight: 900 }}>DATOS: {ds}</span>
        <span style={{ padding: '4px 12px', borderRadius: 12, border: '1px solid #444', color: '#999', fontSize: 11, fontWeight: 700 }}>WORKER: {status?.worker?.state ?? '…'}</span>
      </div>
      {ds === 'DELAYED' && (
        <div style={{ padding: '10px 16px', borderRadius: 10, background: 'rgba(255,167,38,0.08)', border: '1px solid rgba(255,167,38,0.35)', color: '#FFA726', fontSize: 12 }}>
          MODO PRUEBA: datos retrasados (~15 min). Sirve para validar la plataforma; los resultados no son válidos para decidir los gates G1/G3 ni para evaluar rentabilidad.
        </div>
      )}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {NAV.map(n => (
          <Link key={n.href} href={n.href} style={{
            padding: '8px 16px', borderRadius: 8, fontSize: 12, fontWeight: 700, textDecoration: 'none',
            background: active === n.href ? 'rgba(255,255,255,0.08)' : 'transparent',
            color: active === n.href ? '#FFF' : '#666', border: '1px solid rgba(255,255,255,0.05)',
          }}>{n.label}</Link>
        ))}
      </div>
      {children}
    </div>
  )
}

export function Placeholder({ sprint, items }: { sprint: string; items: string[] }) {
  return (
    <div style={optCard}>
      <div style={{ fontSize: 10, fontWeight: 900, color: '#555', textTransform: 'uppercase', letterSpacing: '0.2em', marginBottom: 12 }}>
        Disponible en {sprint}
      </div>
      <ul style={{ color: '#888', fontSize: 13, lineHeight: 1.9, margin: 0, paddingLeft: 18 }}>
        {items.map(i => <li key={i}>{i}</li>)}
      </ul>
      <p style={{ color: '#555', fontSize: 12, marginTop: 14 }}>
        Sin datos de mercado no se muestran cifras: ningún valor se inventa ni se rellena con ceros.
      </p>
    </div>
  )
}
