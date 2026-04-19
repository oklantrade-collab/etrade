"use client"
import { useState, useEffect } from 'react'
import Link from 'next/link'

export default function StocksUniverse() {
  const [universe, setUniverse] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [sortBy, setSortBy] = useState('fundamental_score')
  const [filterPool, setFilterPool] = useState('all')

  useEffect(() => {
    fetchUniverse()
  }, [])

  const fetchUniverse = async () => {
    try {
      setLoading(true)
      const res = await fetch('/api/v1/stocks/universe')
      const data = await res.json()
      setUniverse(data.universe || [])
    } catch (err) {
      console.error("Fetch universe failed", err)
    } finally {
      setLoading(false)
    }
  }

  const handleManualRefresh = async () => {
    try {
      setRefreshing(true)
      const res = await fetch('/api/v1/stocks/refresh-fundamentals', { method: 'POST' })
      if (res.ok) {
        await fetchUniverse()
      }
    } catch (err) {
      console.error("Manual refresh failed", err)
    } finally {
      setRefreshing(false)
    }
  }

  const filtered = universe.filter(item => {
    // 1. Ocultar excluidas por defecto (Mejora 1)
    if (item.quality_flag?.includes('✗')) return false
    
    // 2. Filtro de Pool (Botones superiores)
    if (filterPool === 'all') return true
    return item.pool_type?.toLowerCase().includes(filterPool.toLowerCase())
  })

  const sorted = [...filtered].sort((a, b) => {
    if (sortBy === 'fundamental_score') return (b.fundamental_score || 0) - (a.fundamental_score || 0)
    if (sortBy === 'revenue_growth') return (b.revenue_growth || 0) - (a.revenue_growth || 0)
    if (sortBy === 'technical_score') return (b.technical_score || 0) - (a.technical_score || 0)
    return (b.fundamental_score || 0) - (a.fundamental_score || 0)
  })

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* HEADER */}
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <div style={{ display: 'flex', gap: '8px', fontSize: '11px', fontWeight: 900, color: '#555', textTransform: 'uppercase', letterSpacing: '0.15em', marginBottom: '4px' }}>
            <Link href="/portfolio" style={{ color: '#22C55E', textDecoration: 'none' }}>Portfolio</Link>
            <span>/</span>
            <Link href="/stocks/dashboard" style={{ color: '#22C55E', textDecoration: 'none' }}>Bolsa</Link>
            <span>/</span>
            <span style={{ color: '#888' }}>Universe</span>
          </div>
          <h1 style={{ fontSize: '28px', fontWeight: 900, color: '#FFF', margin: 0, fontStyle: 'italic', letterSpacing: '-0.02em' }}>
            🔍 Universe Builder <span style={{ color: 'rgba(255,255,255,0.2)', fontStyle: 'normal' }}>v5.0</span>
          </h1>
          <p style={{ color: '#555', fontSize: '12px', marginTop: '4px', fontWeight: 600 }}>
            Análisis Fundamental e Institucional — Identificando Líderes de Crecimiento
          </p>
        </div>

        <button
          onClick={handleManualRefresh}
          disabled={refreshing}
          style={{
            padding: '10px 18px',
            borderRadius: '8px',
            background: refreshing ? 'rgba(255,255,255,0.05)' : 'rgba(34,197,94,0.15)',
            border: `1px solid ${refreshing ? 'rgba(255,255,255,0.1)' : 'rgba(34,197,94,0.3)'}`,
            color: refreshing ? '#555' : '#22C55E',
            fontSize: '12px',
            fontWeight: 800,
            cursor: refreshing ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          {refreshing ? 'Refreshing...' : '🔄 Refresh Fundamentals'}
        </button>
      </div>

      {/* CONTROLS */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '20px', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: '6px' }}>
          {[
            { key: 'fundamental_score', label: 'Fundamentos' },
            { key: 'revenue_growth', label: 'Crecimiento' },
            { key: 'technical_score', label: 'Técnico' },
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
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', gap: '6px' }}>
          {['ALL', 'FUTURE_GIANT', 'GROWTH_LEADER'].map(pool => (
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
              }}
            >
              {pool.replace('_', ' ')}
            </button>
          ))}
        </div>
      </div>

      {/* TABLE */}
      {loading ? (
        <div style={{ color: '#666', padding: '100px', textAlign: 'center' }}>Brains are analyzing...</div>
      ) : sorted.length === 0 ? (
        <div style={{
          background: 'rgba(17, 24, 39, 0.4)',
          border: '1px solid rgba(254, 187, 0, 0.1)',
          borderRadius: '16px',
          padding: '80px 20px',
          textAlign: 'center',
        }}>
          <div style={{ fontSize: '40px', marginBottom: '16px' }}>📉</div>
          <h3 style={{ color: '#DDD', margin: '0 0 8px 0' }}>No hay empresas con estas características</h3>
          <p style={{ color: '#666', fontSize: '13px', maxWidth: '400px', margin: '0 auto' }}>
            El universo actual no contiene coincidencias para este filtro. Prueba con <strong>Refresh Fundamentals</strong> para actualizar datos corporativos.
          </p>
        </div>
      ) : (
        <div style={{ background: 'rgba(17, 24, 39, 0.4)', border: '1px solid rgba(255, 255, 255, 0.04)', borderRadius: '16px', overflow: 'hidden' }}>
          <div style={{
            display: 'grid', gridTemplateColumns: '90px 80px 100px 150px 150px 90px 80px 100px 100px 70px',
            padding: '16px 24px', borderBottom: '1px solid rgba(255,255,255,0.04)',
            fontSize: '10px', fontWeight: 900, color: '#444', textTransform: 'uppercase', letterSpacing: '0.12em',
          }}>
            <span>Ticker</span>
            <span>Precio</span>
            <span style={{ color: '#22C55E' }}>Intrinsic</span>
            <span>Pool</span>
            <span>Fundamental Score</span>
            <span>Rev Growth</span>
            <span>Margin</span>
            <span>RS Score</span>
            <span>Inst Own</span>
            <span style={{ textAlign: 'center' }}>Quality</span>
          </div>

          {sorted.map((item, i) => {
            const isUndervalued = item.intrinsic_price > item.price && item.intrinsic_price > 0;
            return (
              <div
                key={item.ticker}
                style={{
                  display: 'grid', gridTemplateColumns: '90px 80px 100px 150px 150px 90px 80px 100px 100px 70px',
                  padding: '14px 24px', borderBottom: i < sorted.length - 1 ? '1px solid rgba(255,255,255,0.02)' : 'none',
                  alignItems: 'center', transition: 'all 0.15s',
                }}
                onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.02)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <span style={{ fontWeight: 900, color: '#FFF', fontSize: '13px' }}>{item.ticker}</span>
                <span style={{ color: '#BBB', fontSize: '12px', fontWeight: 600 }}>${item.price?.toFixed(2) || '—'}</span>
                
                {/* VALOR INTRÍNSECO */}
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                    <span style={{ color: isUndervalued ? '#22C55E' : '#888', fontWeight: 900, fontSize: '12px' }}>
                        ${item.intrinsic_price ? item.intrinsic_price.toFixed(2) : '—'}
                    </span>
                    {isUndervalued && <span style={{ fontSize: '8px', color: '#22C55E', fontWeight: 900 }}>UNDERVALUED</span>}
                </div>
              
              {/* MEJORA 2: DISTINGUIR FUTURE VS GROWTH */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {item.pool_type?.split(',').map((p: any) => {
                  const name = p.trim();
                  if (!name) return null;
                  const isGiant = name === 'GIANT' || name === 'FUTURE_GIANT';
                  return (
                    <span key={name} style={{
                      fontSize: '9px', fontWeight: 900,
                      padding: '2px 8px', borderRadius: '4px',
                      background: isGiant ? '#1E40AF' : '#FEBB00',
                      color: isGiant ? '#FFF' : '#333',
                      border: `1px solid ${isGiant ? '#3B82F6' : '#FFD700'}`,
                      textTransform: 'uppercase',
                      textAlign: 'center',
                      width: 'fit-content'
                    }}>
                      {name === 'GIANT' ? 'FUTURE GIANT' : name === 'LEADER' ? 'GROWTH LEADER' : name.replace('_', ' ')}
                    </span>
                  );
                }) || <span style={{ color: '#444', fontSize: '11px' }}>—</span>}
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div style={{ flex: 1, height: '6px', background: 'rgba(255,255,255,0.03)', borderRadius: '3px', position: 'relative', overflow: 'hidden' }}>
                  <div style={{ position: 'absolute', height: '100%', width: `${item.fundamental_score}%`, background: item.fundamental_score > 70 ? '#22C55E' : item.fundamental_score > 40 ? '#F59E0B' : '#666' }}></div>
                </div>
                <span style={{ fontSize: '12px', fontWeight: 900, color: '#FFF', width: '30px' }}>{Math.round(item.fundamental_score)}</span>
              </div>

              <span style={{ color: (item.revenue_growth || 0) > 20 ? '#22C55E' : '#888', fontWeight: 800, fontSize: '12px' }}>
                {item.revenue_growth ? `+${item.revenue_growth.toFixed(1)}%` : '—'}
              </span>
              
              <span style={{ color: '#888', fontWeight: 700, fontSize: '12px' }}>{item.gross_margin ? `${item.gross_margin.toFixed(1)}%` : '—'}</span>

              <span style={{ 
                color: item.rs_score === -1 ? '#EF4444' : (item.rs_score || 0) > 80 ? '#22C55E' : (item.rs_score || 0) > 50 ? '#F59E0B' : '#555', 
                fontWeight: 900, fontSize: item.rs_score === -1 ? '9px' : '12px'
              }}>
                {item.rs_score === -1 ? 'RS_UNAVAILABLE' : (item.rs_score !== null && item.rs_score !== undefined ? Math.round(item.rs_score) : '—')}
              </span>

              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ color: '#888', fontWeight: 700, fontSize: '12px' }}>{item.inst_ownership ? `${item.inst_ownership.toFixed(1)}%` : '—'}</span>
                <span style={{ color: '#22C55E', fontSize: '10px', opacity: 0.7 }}>▲</span>
              </div>

              {/* MEJORA 1: COLUMNA QUALITY */}
              <div style={{ textAlign: 'center' }}>
                <span style={{
                  fontSize: '14px',
                  color: item.quality_flag?.includes('EXCLUDED') ? '#EF4444' : item.quality_flag?.includes('REVIEW') ? '#F59E0B' : '#22C55E',
                  fontWeight: 900
                }}>
                  {item.quality_flag === 'EXCLUDED' ? '✗' : item.quality_flag === 'REVIEW' ? '⚠' : '✓'}
                </span>
              </div>
            </div>
            );
          })}
        </div>
      )}
    </div>
  )
}
