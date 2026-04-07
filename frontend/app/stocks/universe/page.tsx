"use client"
import { useState, useEffect } from 'react'
import Link from 'next/link'

export default function StocksUniverse() {
  const [universe, setUniverse] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [sortBy, setSortBy] = useState('catalyst_score')
  const [filterPool, setFilterPool] = useState('all')

  useEffect(() => {
    fetchUniverse()
  }, [])

  const fetchUniverse = async () => {
    try {
      const res = await fetch('/api/v1/stocks/universe')
      const data = await res.json()
      setUniverse(data.universe || [])
    } catch (err) {
      console.error("Fetch universe failed", err)
    } finally {
      setLoading(false)
    }
  }

  const sorted = [...universe]
    .filter(u => filterPool === 'all' || u.pool_type === filterPool)
    .sort((a, b) => {
      if (sortBy === 'technical_score') return (b.technical_score || 0) - (a.technical_score || 0)
      if (sortBy === 'rvol') return (b.rvol || 0) - (a.rvol || 0)
      return (b.catalyst_score || 0) - (a.catalyst_score || 0)
    })

  return (
    <div style={{ padding: '24px' }}>
      {/* HEADER */}
      <div style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', gap: '8px', fontSize: '11px', fontWeight: 900, color: '#555', textTransform: 'uppercase', letterSpacing: '0.15em', marginBottom: '4px' }}>
          <Link href="/portfolio" style={{ color: '#22C55E', textDecoration: 'none' }}>Portfolio</Link>
          <span>/</span>
          <Link href="/stocks/dashboard" style={{ color: '#22C55E', textDecoration: 'none' }}>Bolsa</Link>
          <span>/</span>
          <span style={{ color: '#888' }}>Universe</span>
        </div>
        <h1 style={{ fontSize: '24px', fontWeight: 900, color: '#FFF', margin: 0, fontStyle: 'italic' }}>
          🔍 Universe Builder
        </h1>
        <p style={{ color: '#555', fontSize: '12px', marginTop: '4px' }}>
          Candidatos del día — filtrados por volumen, market cap y catalizadores
        </p>
      </div>

      {/* CONTROLS */}
      <div style={{
        display: 'flex',
        gap: '12px',
        marginBottom: '20px',
        flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', gap: '6px' }}>
          {[
            { key: 'catalyst_score', label: 'Catalizador' },
            { key: 'technical_score', label: 'Técnico' },
            { key: 'rvol', label: 'RVOL' },
          ].map(opt => (
            <button
              key={opt.key}
              onClick={() => setSortBy(opt.key)}
              style={{
                padding: '6px 14px',
                borderRadius: '6px',
                border: `1px solid ${sortBy === opt.key ? 'rgba(34,197,94,0.40)' : 'rgba(255,255,255,0.06)'}`,
                background: sortBy === opt.key ? 'rgba(34,197,94,0.12)' : 'rgba(255,255,255,0.02)',
                color: sortBy === opt.key ? '#22C55E' : '#555',
                fontSize: '11px',
                fontWeight: 700,
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', gap: '6px' }}>
          {['all', 'core', 'tactical'].map(pool => (
            <button
              key={pool}
              onClick={() => setFilterPool(pool)}
              style={{
                padding: '6px 14px',
                borderRadius: '6px',
                border: `1px solid ${filterPool === pool ? 'rgba(79,195,247,0.40)' : 'rgba(255,255,255,0.06)'}`,
                background: filterPool === pool ? 'rgba(79,195,247,0.12)' : 'rgba(255,255,255,0.02)',
                color: filterPool === pool ? '#4FC3F7' : '#555',
                fontSize: '11px',
                fontWeight: 700,
                cursor: 'pointer',
                textTransform: 'uppercase',
              }}
            >
              {pool}
            </button>
          ))}
        </div>

        <div style={{ marginLeft: 'auto', color: '#555', fontSize: '12px', fontWeight: 700 }}>
          {sorted.length} candidatos
        </div>
      </div>

      {/* TABLE */}
      {loading ? (
        <div style={{ color: '#666', padding: '40px', textAlign: 'center' }}>Cargando universe...</div>
      ) : sorted.length === 0 ? (
        <div style={{
          background: 'rgba(17, 24, 39, 0.4)',
          border: '1px solid rgba(255, 255, 255, 0.04)',
          borderRadius: '16px',
          padding: '60px',
          textAlign: 'center',
        }}>
          <div style={{ fontSize: '48px', marginBottom: '16px', opacity: 0.3 }}>🔍</div>
          <p style={{ color: '#666', fontSize: '14px' }}>
            No hay candidatos en el universe todavía.
          </p>
          <p style={{ color: '#555', fontSize: '12px', marginTop: '8px' }}>
            El Universe Builder se ejecuta automáticamente post-cierre diario (Capa 0 — Sprint 6).
          </p>
        </div>
      ) : (
        <div style={{
          background: 'rgba(17, 24, 39, 0.4)',
          border: '1px solid rgba(255, 255, 255, 0.04)',
          borderRadius: '16px',
          overflow: 'hidden',
        }}>
          {/* Table Header */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '100px 1fr 100px 100px 100px 100px 80px',
            padding: '14px 20px',
            borderBottom: '1px solid rgba(255,255,255,0.04)',
            fontSize: '10px',
            fontWeight: 900,
            color: '#555',
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
          }}>
            <span>Ticker</span>
            <span>Catalizador</span>
            <span>Pool</span>
            <span>Catalyst</span>
            <span>Tech Score</span>
            <span>RVOL</span>
            <span>MTF</span>
          </div>

          {/* Table Rows */}
          {sorted.map((item, i) => (
            <div
              key={item.ticker}
              style={{
                display: 'grid',
                gridTemplateColumns: '100px 1fr 100px 100px 100px 100px 80px',
                padding: '12px 20px',
                borderBottom: i < sorted.length - 1 ? '1px solid rgba(255,255,255,0.02)' : 'none',
                alignItems: 'center',
                transition: 'background 0.15s',
              }}
              onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.02)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            >
              <span style={{ fontWeight: 900, color: '#FFF', fontSize: '13px' }}>{item.ticker}</span>
              <span style={{ color: '#888', fontSize: '12px' }}>{item.catalyst_type || '—'}</span>
              <span style={{
                fontSize: '10px', fontWeight: 800,
                color: item.pool_type === 'core' ? '#4FC3F7' : '#F59E0B',
                textTransform: 'uppercase',
              }}>
                {item.pool_type || '—'}
              </span>
              <span style={{
                fontWeight: 800, fontSize: '13px', fontFamily: 'monospace',
                color: (item.catalyst_score || 0) >= 7 ? '#22C55E' : '#888',
              }}>
                {item.catalyst_score || '—'}
              </span>
              <span style={{
                fontWeight: 800, fontSize: '13px', fontFamily: 'monospace',
                color: (item.technical_score || 0) >= 60 ? '#22C55E' : (item.technical_score || 0) >= 40 ? '#F59E0B' : '#666',
              }}>
                {item.technical_score || '—'}
              </span>
              <span style={{
                fontWeight: 800, fontSize: '12px', fontFamily: 'monospace',
                color: (item.rvol || 0) >= 2.5 ? '#F59E0B' : '#666',
              }}>
                {item.rvol ? `${item.rvol.toFixed(1)}x` : '—'}
              </span>
              <span style={{
                fontSize: '11px', fontWeight: 800,
                color: item.mtf_confirmed ? '#22C55E' : '#444',
              }}>
                {item.mtf_confirmed ? '✅' : '—'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
