'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { OptionsShell, optCard } from '@/components/options/OptionsShell'

interface Underlying {
  id: number
  symbol: string
  price: number | null
  direction?: string | null
  direction_source?: string | null
  catalyst_score?: number | null
  apex_score?: number | null
  optionable: boolean
  optionable_reason?: string | null
  warnings?: string[]
  strike_gap_pct?: number | null
  atm_spread_pct?: number | null
  atm_oi?: number | null
  atm_volume?: number | null
  data_state?: string
  updated_at?: string
  catalyst_meta?: any
}

const n = (v: any, d = 2) => (v === null || v === undefined ? '—' : Number(v).toFixed(d))

export default function OptionsUniversePage() {
  const [items, setItems] = useState<Underlying[]>([])
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [filterDir, setFilterDir] = useState<'all' | 'CALL' | 'PUT' | 'optionable'>('all')
  const [search, setSearch] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const loadData = async () => {
    setLoading(true)
    setErr(null)
    try {
      const res = await fetch('/api/v1/options/universe').then(r => r.json())
      setItems(res.items || [])
    } catch (e) {
      setErr('Error al cargar universo de opciones')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const handleTriggerCatalystScan = async () => {
    setScanning(true)
    setMsg(null)
    setErr(null)
    try {
      const res = await fetch('/api/v1/options/catalysts/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      }).then(r => r.json())
      if (res.total_selected !== undefined) {
        setMsg(`¡Escaneo de catalizadores completado! ${res.calls_selected} CALLs y ${res.puts_selected} PUTs actualizadas.`)
        await loadData()
      } else {
        setMsg('Escaneo ejecutado.')
        await loadData()
      }
    } catch {
      setErr('Error al ejecutar el escaneo de catalizadores')
    } finally {
      setScanning(false)
    }
  }

  const filtered = items.filter(u => {
    if (search && !u.symbol.toLowerCase().includes(search.toLowerCase())) return false
    const dir = (u.direction || '').toUpperCase()
    if (filterDir === 'CALL') return dir === 'CALL' || dir === 'BULLISH'
    if (filterDir === 'PUT') return dir === 'PUT' || dir === 'BEARISH'
    if (filterDir === 'optionable') return Boolean(u.optionable)
    return true
  })

  const callsCount = items.filter(u => ['CALL', 'BULLISH'].includes((u.direction || '').toUpperCase())).length
  const putsCount = items.filter(u => ['PUT', 'BEARISH'].includes((u.direction || '').toUpperCase())).length
  const optionableCount = items.filter(u => u.optionable).length

  const th: React.CSSProperties = { textAlign: 'left', color: '#666', fontSize: 10, textTransform: 'uppercase', padding: '10px 12px' }
  const td: React.CSSProperties = { color: '#AAA', fontSize: 12, padding: '10px 12px', borderTop: '1px solid rgba(255,255,255,0.04)' }
  const kpiCard: React.CSSProperties = { background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 10, padding: '12px 16px', flex: 1, minWidth: 160 }

  return (
    <OptionsShell title="Options Universe" active="/options/universe">
      {/* HEADER & SWITCHER */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16, marginBottom: 16 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <h1 style={{ fontSize: 24, fontWeight: 900, color: '#FFF', margin: 0, letterSpacing: '-0.5px' }}>
              ⚡ Universo de Opciones (CALL & PUT)
            </h1>
            <span style={{ fontSize: 10, padding: '3px 10px', borderRadius: 20, background: 'rgba(171,71,188,0.15)', color: '#AB47BC', fontWeight: 800, border: '1px solid rgba(171,71,188,0.3)' }}>
              CATALIZADORES 5M & ARBITRAJE
            </span>
          </div>
          <p style={{ color: '#777', fontSize: 12, margin: '4px 0 0 0' }}>
            Pool de subyacentes clasificados en tiempo real para opciones CALL (alcistas) y PUT (acciones cayendo).
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {/* Switcher entre Stocks Universe y Options Universe */}
          <div style={{
            display: 'flex',
            background: 'rgba(255,255,255,0.04)',
            padding: '3px',
            borderRadius: '10px',
            border: '1px solid rgba(255,255,255,0.08)'
          }}>
            <Link
              href="/stocks/universe"
              style={{
                padding: '6px 12px',
                borderRadius: '7px',
                color: '#888',
                fontWeight: 700,
                fontSize: '11px',
                textDecoration: 'none',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              📈 Acciones (Stocks)
            </Link>
            <span style={{
              padding: '6px 12px',
              borderRadius: '7px',
              background: '#AB47BC',
              color: '#FFF',
              fontWeight: 800,
              fontSize: '11px',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}>
              ⚡ Opciones (CALL/PUT)
            </span>
          </div>

          <button
            onClick={handleTriggerCatalystScan}
            disabled={scanning}
            style={{
              background: scanning ? 'rgba(255,255,255,0.05)' : 'linear-gradient(135deg, #AB47BC 0%, #7B1FA2 100%)',
              color: scanning ? '#666' : '#FFF',
              border: 'none',
              borderRadius: 8,
              padding: '9px 16px',
              fontSize: 12,
              fontWeight: 800,
              cursor: scanning ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              boxShadow: scanning ? 'none' : '0 4px 14px rgba(171,71,188,0.3)',
            }}
          >
            {scanning ? '⏳ Escaneando 5m…' : '⚡ Escanear Catalizadores'}
          </button>
        </div>
      </div>

      {msg && (
        <div style={{ background: 'rgba(38,166,154,0.15)', border: '1px solid rgba(38,166,154,0.3)', color: '#26A69A', borderRadius: 8, padding: '10px 14px', fontSize: 12, marginBottom: 14 }}>
          {msg}
        </div>
      )}
      {err && (
        <div style={{ background: 'rgba(239,83,80,0.15)', border: '1px solid rgba(239,83,80,0.3)', color: '#EF5350', borderRadius: 8, padding: '10px 14px', fontSize: 12, marginBottom: 14 }}>
          {err}
        </div>
      )}

      {/* METRICS CARDS */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
        <div style={kpiCard}>
          <div style={{ color: '#888', fontSize: 11, textTransform: 'uppercase' }}>Subyacentes Totales</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: '#FFF', marginTop: 4 }}>
            {items.length} <span style={{ fontSize: 12, color: '#666' }}>monitoreados</span>
          </div>
        </div>

        <div style={kpiCard}>
          <div style={{ color: '#888', fontSize: 11, textTransform: 'uppercase' }}>🟢 Oportunidades CALL</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: '#22C55E', marginTop: 4 }}>
            {callsCount} <span style={{ fontSize: 12, color: '#666' }}>/ max 25</span>
          </div>
        </div>

        <div style={kpiCard}>
          <div style={{ color: '#888', fontSize: 11, textTransform: 'uppercase' }}>🟣 Oportunidades PUT</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: '#AB47BC', marginTop: 4 }}>
            {putsCount} <span style={{ fontSize: 12, color: '#666' }}>/ max 25</span>
          </div>
        </div>

        <div style={kpiCard}>
          <div style={{ color: '#888', fontSize: 11, textTransform: 'uppercase' }}>Optionables Verificados</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: '#38BDF8', marginTop: 4 }}>
            {optionableCount} <span style={{ fontSize: 12, color: '#666' }}>({items.length > 0 ? Math.round((optionableCount / items.length) * 100) : 0}%)</span>
          </div>
        </div>
      </div>

      {/* MAIN CONTAINER */}
      <div style={optCard}>
        {/* FILTERS & SEARCH */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
          <div style={{ display: 'flex', gap: 6, background: 'rgba(0,0,0,0.3)', padding: 4, borderRadius: 8, border: '1px solid rgba(255,255,255,0.05)' }}>
            <button
              onClick={() => setFilterDir('all')}
              style={{
                padding: '6px 14px', borderRadius: 6, fontSize: 11, fontWeight: 700, border: 'none', cursor: 'pointer',
                background: filterDir === 'all' ? 'rgba(255,255,255,0.1)' : 'transparent',
                color: filterDir === 'all' ? '#FFF' : '#888',
              }}
            >
              Todos ({items.length})
            </button>
            <button
              onClick={() => setFilterDir('CALL')}
              style={{
                padding: '6px 14px', borderRadius: 6, fontSize: 11, fontWeight: 700, border: 'none', cursor: 'pointer',
                background: filterDir === 'CALL' ? 'rgba(34,197,94,0.2)' : 'transparent',
                color: filterDir === 'CALL' ? '#22C55E' : '#888',
              }}
            >
              🟢 CALL Alcistas ({callsCount})
            </button>
            <button
              onClick={() => setFilterDir('PUT')}
              style={{
                padding: '6px 14px', borderRadius: 6, fontSize: 11, fontWeight: 700, border: 'none', cursor: 'pointer',
                background: filterDir === 'PUT' ? 'rgba(171,71,188,0.2)' : 'transparent',
                color: filterDir === 'PUT' ? '#AB47BC' : '#888',
              }}
            >
              🟣 PUT Bajistas ({putsCount})
            </button>
            <button
              onClick={() => setFilterDir('optionable')}
              style={{
                padding: '6px 14px', borderRadius: 6, fontSize: 11, fontWeight: 700, border: 'none', cursor: 'pointer',
                background: filterDir === 'optionable' ? 'rgba(56,189,248,0.2)' : 'transparent',
                color: filterDir === 'optionable' ? '#38BDF8' : '#888',
              }}
            >
              Solo Optionables ({optionableCount})
            </button>
          </div>

          <div style={{ display: 'flex', gap: 10 }}>
            <input
              type="text"
              placeholder="Buscar símbolo (SPY, NVDA...)"
              value={search}
              onChange={e => setSearch(e.target.value)}
              style={{
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: 6,
                padding: '7px 12px',
                color: '#FFF',
                fontSize: 12,
                outline: 'none',
                width: 220,
              }}
            />
            <button
              onClick={loadData}
              disabled={loading}
              style={{
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.1)',
                color: '#AAA',
                borderRadius: 6,
                padding: '7px 12px',
                fontSize: 12,
                cursor: 'pointer',
              }}
            >
              ↻ Refrescar
            </button>
          </div>
        </div>

        {/* TABLE */}
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: 'rgba(0,0,0,0.2)' }}>
                <th style={th}>Símbolo</th>
                <th style={th}>Precio</th>
                <th style={th}>Dirección / Sesgo</th>
                <th style={th}>Score Catalítico</th>
                <th style={th}>Catalizadores Activos</th>
                <th style={th}>ATM Spread %</th>
                <th style={th}>ATM OI / Vol</th>
                <th style={th}>Opcionable</th>
                <th style={th}>Cadenas / Acciones</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={9} style={{ textAlign: 'center', padding: '30px', color: '#666' }}>
                    Cargando universo de opciones...
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={9} style={{ textAlign: 'center', padding: '30px', color: '#666' }}>
                    No se encontraron subyacentes con los filtros actuales.
                  </td>
                </tr>
              ) : (
                filtered.map(u => {
                  const dir = (u.direction || '').toUpperCase()
                  const isCall = dir === 'CALL' || dir === 'BULLISH'
                  const isPut = dir === 'PUT' || dir === 'BEARISH'
                  const score = u.catalyst_score ?? u.apex_score

                  return (
                    <tr key={u.symbol} style={{ transition: 'background 0.2s' }}>
                      <td style={td}>
                        <div style={{ fontWeight: 800, color: '#FFF', fontSize: 13 }}>{u.symbol}</div>
                        <div style={{ fontSize: 10, color: '#666' }}>{u.data_state || 'DELAYED'}</div>
                      </td>
                      <td style={td}>
                        <span style={{ fontWeight: 700, color: '#EEE' }}>${n(u.price, 2)}</span>
                      </td>
                      <td style={td}>
                        {isCall ? (
                          <span style={{
                            padding: '3px 8px', borderRadius: 4, background: 'rgba(34,197,94,0.15)', color: '#22C55E',
                            fontWeight: 800, fontSize: 10, border: '1px solid rgba(34,197,94,0.3)',
                          }}>
                            🟢 CALL (Alcista)
                          </span>
                        ) : isPut ? (
                          <span style={{
                            padding: '3px 8px', borderRadius: 4, background: 'rgba(171,71,188,0.15)', color: '#AB47BC',
                            fontWeight: 800, fontSize: 10, border: '1px solid rgba(171,71,188,0.3)',
                          }}>
                            🟣 PUT (Bajista)
                          </span>
                        ) : (
                          <span style={{ color: '#666', fontSize: 11 }}>NEUTRAL</span>
                        )}
                      </td>
                      <td style={td}>
                        {score !== null && score !== undefined ? (
                          <span style={{
                            padding: '2px 8px', borderRadius: 4,
                            background: Number(score) >= 60 ? 'rgba(38,166,154,0.2)' : 'rgba(255,167,38,0.2)',
                            color: Number(score) >= 60 ? '#26A69A' : '#FFA726',
                            fontWeight: 700, fontSize: 11,
                          }}>
                            {Number(score).toFixed(1)}
                          </span>
                        ) : '—'}
                      </td>
                      <td style={td}>
                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                          <span style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, background: 'rgba(255,255,255,0.06)', color: '#AAA' }}>
                            C1 Gap
                          </span>
                          <span style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, background: 'rgba(255,255,255,0.06)', color: '#AAA' }}>
                            C2 Basis
                          </span>
                          <span style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, background: 'rgba(255,255,255,0.06)', color: '#AAA' }}>
                            C3 ADX
                          </span>
                          <span style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, background: 'rgba(255,255,255,0.06)', color: '#AAA' }}>
                            C4 Rebote
                          </span>
                        </div>
                      </td>
                      <td style={td}>
                        <span style={{ color: (u.atm_spread_pct ?? 99) <= 10 ? '#26A69A' : '#EF5350' }}>
                          {n(u.atm_spread_pct, 2)}%
                        </span>
                      </td>
                      <td style={td}>
                        <div style={{ fontSize: 11 }}>{n(u.atm_oi, 0)} OI</div>
                        <div style={{ fontSize: 10, color: '#666' }}>{n(u.atm_volume, 0)} vol</div>
                      </td>
                      <td style={td}>
                        {u.optionable ? (
                          <span style={{ color: '#26A69A', fontWeight: 700, fontSize: 11 }}>✓ Sí</span>
                        ) : (
                          <span style={{ color: '#EF5350', fontSize: 10 }} title={u.optionable_reason || ''}>
                            ✗ {u.optionable_reason ? u.optionable_reason.slice(0, 18) + '…' : 'No'}
                          </span>
                        )}
                      </td>
                      <td style={td}>
                        <Link
                          href={`/options/opportunities?symbol=${u.symbol}`}
                          style={{
                            padding: '4px 10px',
                            borderRadius: 4,
                            background: 'rgba(255,255,255,0.06)',
                            border: '1px solid rgba(255,255,255,0.1)',
                            color: '#DDD',
                            fontSize: 11,
                            textDecoration: 'none',
                            fontWeight: 600,
                          }}
                        >
                          Ver Oportunidades →
                        </Link>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </OptionsShell>
  )
}
