'use client'
import React, { useState, useEffect } from 'react'

interface RuleDiagnosticPanelProps {
  symbol: string
  onClose: () => void
}

const RuleDiagnosticPanel: React.FC<RuleDiagnosticPanelProps> = ({ symbol, onClose }) => {
  const [timeframe, setTimeframe] = useState('15m')
  const [activeTab, setActiveTab] = useState('scalping')
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  const TIMEFRAMES = ['5m', '15m', '30m', '4h']

  useEffect(() => {
    fetchRuleEvaluation(symbol, timeframe)
    
    // Auto-refresh cada 30 segundos
    const timer = setInterval(() => {
      fetchRuleEvaluation(symbol, timeframe)
    }, 30000)
    
    return () => clearInterval(timer)
  }, [symbol, timeframe])

  const fetchRuleEvaluation = async (sym: string, tf: string) => {
    setLoading(true)
    try {
      // Usar la ruta relativa para aprovechar el rewrite de Next.js (evita errores de CORS)
      const res = await fetch(`/api/v1/strategies/live/${sym}?timeframe=${tf}`)
      const json = await res.json()
      setData(json)
    } catch (err) {
      console.error("Error fetching rule evaluation:", err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div 
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.85)',
        backdropFilter: 'blur(8px)',
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px'
      }}
      onClick={onClose}
    >
      <div 
        style={{
          width: '900px',
          maxWidth: '100%',
          maxHeight: '90vh',
          background: '#0D1117',
          border: '1px solid rgba(255,255,255,0.12)',
          borderRadius: '24px',
          overflow: 'hidden',
          boxShadow: '0 25px 80px rgba(0,0,0,0.8)',
          display: 'flex',
          flexDirection: 'column'
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* HEADER */}
        <div style={{
          padding: '24px 32px 20px',
          borderBottom: '1px solid rgba(255,255,255,0.08)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: 'rgba(255,255,255,0.02)',
        }}>
          <div>
            <div style={{
              fontSize: '22px',
              fontWeight: 800,
              color: '#FFF',
              letterSpacing: '-0.5px',
              display: 'flex',
              alignItems: 'center',
              gap: '12px'
            }}>
              <span style={{ opacity: 0.5 }}>🔍</span> Diagnóstico — {symbol}
            </div>
            <div style={{
              fontSize: '12px',
              color: '#666',
              marginTop: '4px',
              fontWeight: 500,
              textTransform: 'uppercase',
              letterSpacing: '1px'
            }}>
              Estado de reglas en tiempo real v5.0
            </div>
          </div>

          {/* SELECTOR DE TIMEFRAME */}
          <div style={{
            display: 'flex',
            gap: '6px',
            alignItems: 'center',
            background: 'rgba(0,0,0,0.3)',
            padding: '4px',
            borderRadius: '10px',
            border: '1px solid rgba(255,255,255,0.05)'
          }}>
            {TIMEFRAMES.map(tf => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                style={{
                  padding: '6px 14px',
                  borderRadius: '8px',
                  border: 'none',
                  background: timeframe === tf ? '#00C896' : 'transparent',
                  color: timeframe === tf ? '#000' : '#888',
                  fontSize: '12px',
                  fontWeight: 700,
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}>
                {tf.toUpperCase()}
              </button>
            ))}

            <button
              onClick={onClose}
              style={{
                marginLeft: '12px',
                background: 'rgba(255,255,255,0.08)',
                border: 'none',
                borderRadius: '8px',
                color: '#AAA',
                width: '32px',
                height: '32px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                fontSize: '16px',
                transition: 'background 0.2s'
              }}
              onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,50,50,0.2)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.08)')}
            >
              ✕
            </button>
          </div>
        </div>

        {/* CONTEXTO DE MERCADO ACTUAL */}
        <div style={{
          padding: '16px 32px',
          background: 'rgba(255,255,255,0.01)',
          borderBottom: '1px solid rgba(255,255,255,0.04)',
          display: 'flex',
          gap: '32px',
          fontSize: '12px',
        }}>
          {data && [
            { label: 'Precio', value: `$${data.context?.price?.toLocaleString(undefined, { minimumFractionDigits: 2 })}` },
            { label: 'MTF', value: data.context?.mtf_score?.toFixed(2), color: data.context?.mtf_score > 0 ? '#00C896' : '#FF4757' },
            { label: 'ADX', value: `${data.context?.adx?.toFixed(1)} (${data.context?.adx_velocity || ''})` },
            { label: 'SAR 4h', value: data.context?.sar_trend_4h > 0 ? 'LONG' : 'SHORT', color: data.context?.sar_trend_4h > 0 ? '#00C896' : '#FF4757' },
            { label: 'Zona Fib', value: data.context?.fibonacci_zone, color: data.context?.fibonacci_zone > 0 ? '#00C896' : '#FF4757' },
            { label: 'Retro/Range', value: data.context?.is_range_or_fall ? 'CUMPLE' : 'FALTA', color: data.context?.is_range_or_fall ? '#4FC3F7' : '#FF4757' },
            { label: 'Pine Signal', value: data.context?.pinescript_signal || '—', color: data.context?.pinescript_signal === 'Buy' ? '#00C896' : data.context?.pinescript_signal === 'Sell' ? '#FF4757' : '#666' },
          ].map(item => (
            <div key={item.label}>
              <div style={{ color: '#444', marginBottom: '2px', fontWeight: 700, textTransform: 'uppercase', fontSize: '10px', letterSpacing: '0.5px' }}>{item.label}</div>
              <div style={{ color: item.color || '#CCC', fontWeight: 700, fontSize: '14px', fontFamily: 'monospace' }}>{item.value}</div>
            </div>
          ))}
        </div>

        {/* TABS SCALPING / SWING */}
        <div style={{
          display: 'flex',
          padding: '0 32px',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          background: 'rgba(255,255,255,0.01)',
        }}>
          {[
            { key: 'scalping', label: '⚡ Scalping', color: '#4FC3F7' },
            { key: 'swing', label: '📈 Swing Trade', color: '#CE93D8' },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                padding: '16px 24px',
                background: 'transparent',
                border: 'none',
                borderBottom: activeTab === tab.key ? `3px solid ${tab.color}` : '3px solid transparent',
                color: activeTab === tab.key ? tab.color : '#555',
                fontSize: '14px',
                fontWeight: 800,
                cursor: 'pointer',
                marginBottom: '-1px',
                transition: 'all 0.2s',
                textTransform: 'uppercase',
                letterSpacing: '1px'
              }}>
              {tab.label}
            </button>
          ))}
        </div>

        {/* TABLA DE REGLAS */}
        <div style={{
          overflowY: 'auto',
          flex: 1,
          padding: '24px 32px 32px',
        }} className="custom-scrollbar">

          {loading ? (
            <div style={{ textAlign: 'center', padding: '100px', color: '#444', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px' }}>
              <div style={{ width: '40px', height: '40px', border: '3px solid #1a1f2e', borderTopColor: '#00C896', borderRadius: '50%', animation: 'spin 1s linear infinite' }}></div>
              <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
              <div style={{ fontWeight: 600, fontSize: '14px', letterSpacing: '1px' }}>EVALUANDO REGLAS DE ESTRATEGIA...</div>
            </div>
          ) : (
            ['long', 'short'].map(direction => {
              const dirRules = data?.rules?.filter(
                (r: any) => r.direction === direction && r.strategy_type === activeTab
              ) || []

              if (dirRules.length === 0) return null

              return (
                <div key={direction} style={{ marginBottom: '32px' }}>
                  {/* HEADER DIRECCIÓN */}
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    marginBottom: '16px',
                    padding: '8px 0',
                    borderBottom: '1px solid rgba(255,255,255,0.03)'
                  }}>
                    <div style={{
                      width: '10px',
                      height: '10px',
                      borderRadius: '50%',
                      background: direction === 'long' ? '#00C896' : '#FF4757',
                      boxShadow: `0 0 10px ${direction === 'long' ? 'rgba(0,200,150,0.5)' : 'rgba(255,71,87,0.5)'}`
                    }} />
                    <span style={{
                      color: direction === 'long' ? '#00C896' : '#FF4757',
                      fontSize: '12px',
                      fontWeight: 900,
                      letterSpacing: '2px',
                      textTransform: 'uppercase'
                    }}>
                      OPERACIONES {direction === 'long' ? 'ALCISTAS' : 'BAJISTAS'}
                    </span>
                    <div style={{ flex: 1, height: '1px', background: 'rgba(255,255,255,0.03)' }}></div>
                  </div>

                  {/* REGLAS */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {dirRules.map((rule: any) => (
                      <RuleRow key={rule.rule_code} rule={rule} context={data.context} />
                    ))}
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}

const RuleRow: React.FC<{ rule: any, context: any }> = ({ rule, context }) => {
  const [expanded, setExpanded] = useState(rule.triggered || rule.score >= 0.50)

  const scoreColor = rule.triggered ? '#00C896' : rule.score >= 0.5 ? '#FFB74D' : '#FF4757'
  const scorePct = Math.round(rule.score * 100)

  return (
    <div style={{
      border: `1px solid ${rule.triggered ? 'rgba(0,200,150,0.3)' : 'rgba(255,255,255,0.06)'}`,
      borderRadius: '12px',
      overflow: 'hidden',
      background: rule.triggered ? 'rgba(0,200,150,0.06)' : 'rgba(255,255,255,0.02)',
      transition: 'all 0.2s ease'
    }}>
      {/* HEADER DE LA REGLA */}
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '14px 20px',
          cursor: 'pointer',
          gap: '16px',
        }}>
        <span style={{ fontFamily: 'monospace', fontSize: '15px', fontWeight: 900, color: scoreColor, minWidth: '60px' }}>{rule.rule_code}</span>
        <span style={{ flex: 1, fontSize: '13px', color: '#BBB', fontWeight: 600 }}>{rule.rule_name}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ width: '100px', height: '6px', background: 'rgba(0,0,0,0.4)', borderRadius: '3px', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ width: `${scorePct}%`, height: '100%', background: scoreColor, transition: 'width 0.8s cubic-bezier(0.17, 0.67, 0.83, 0.67)' }} />
          </div>
          <span style={{ fontSize: '13px', fontWeight: 800, color: scoreColor, minWidth: '40px', textAlign: 'right', fontFamily: 'monospace' }}>{scorePct}%</span>
        </div>
        <span style={{
          padding: '4px 10px',
          borderRadius: '6px',
          fontSize: '10px',
          fontWeight: 900,
          letterSpacing: '0.8px',
          background: rule.triggered ? 'rgba(0,200,150,0.2)' : 'rgba(255,71,87,0.1)',
          color: rule.triggered ? '#00C896' : '#FF4757',
          border: `1px solid ${rule.triggered ? 'rgba(0,200,150,0.4)' : 'rgba(255,71,87,0.2)'}`,
          minWidth: '80px',
          textAlign: 'center'
        }}>
          {rule.triggered ? '✓ CUMPLE' : '✗ FALTA'}
        </span>
        <span style={{ color: '#444', fontSize: '12px', transform: expanded ? 'rotate(90deg)' : 'rotate(0)', transition: 'transform 0.3s' }}>▶</span>
      </div>

      {expanded && (
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', padding: '8px 0 16px', background: 'rgba(0,0,0,0.2)' }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: '40px 1fr 50px 100px 100px 70px 70px',
            gap: '0 12px',
            padding: '8px 24px',
            fontSize: '10px',
            color: '#555',
            fontWeight: 800,
            letterSpacing: '1px',
            textTransform: 'uppercase',
            borderBottom: '1px solid rgba(255,255,255,0.03)',
            marginBottom: '4px'
          }}>
            <span></span>
            <span>Condición de Mercado</span>
            <span style={{ textAlign: 'right' }}>Peso</span>
            <span style={{ textAlign: 'right' }}>Actual</span>
            <span style={{ textAlign: 'right' }}>Objetivo</span>
            <span style={{ textAlign: 'right' }}>Falta %</span>
            <span style={{ textAlign: 'right' }}>Falta Num</span>
          </div>

          {(Object.entries(rule.conditions || {}) as [string, any][]).map(([cid, cond]) => {
            const isPrice = [
              'price', 'basis', 'upper_1', 'upper_2', 'upper_3', 'upper_4', 'upper_5', 'upper_6',
              'lower_1', 'lower_2', 'lower_3', 'lower_4', 'lower_5', 'lower_6',
            ].includes(cond.source_field)
            
            const isNumeric = typeof cond.current_value === 'number' && typeof cond.target_value === 'number'

            const currentVal = cond.current_value
            const targetVal = cond.target_value

            let gapPct: string | null = null
            let gapNum: string | null = null

            if (isNumeric && !cond.passed) {
              const diff = targetVal - currentVal
              gapPct = targetVal !== 0 ? ((diff / targetVal) * 100).toFixed(2) : '0'
              gapNum = Math.abs(diff).toLocaleString('en-US', { maximumFractionDigits: 4 })
            }

            return (
              <div key={cid} style={{
                display: 'grid',
                gridTemplateColumns: '40px 1fr 50px 100px 100px 70px 70px',
                gap: '0 12px',
                padding: '8px 24px',
                alignItems: 'center',
                background: cond.passed ? 'transparent' : 'rgba(255,71,87,0.03)',
              }}>
                <span style={{ fontSize: '14px', color: cond.passed ? '#00C896' : '#FF4757', fontWeight: 'bold', textAlign: 'center' }}>{cond.passed ? '✓' : '✗'}</span>
                <span title={cond.source_field} style={{ fontSize: '13px', color: cond.passed ? '#888' : '#EEE', fontWeight: cond.passed ? 400 : 500 }}>{cond.name}</span>
                <span style={{ fontSize: '11px', color: '#555', textAlign: 'right', fontWeight: 700 }}>{Math.round(cond.weight * 100)}%</span>
                <span style={{ fontSize: '12px', color: cond.passed ? '#666' : '#CCC', textAlign: 'right', fontFamily: 'monospace' }}>{formatValue(currentVal, cond.source_field)}</span>
                <span style={{ fontSize: '12px', color: cond.passed ? '#666' : '#FFB74D', textAlign: 'right', fontFamily: 'monospace', fontWeight: 600 }}>{cond.passed ? '—' : formatValue(targetVal, cond.source_field)}</span>
                <span style={{ fontSize: '11px', color: cond.passed ? '#444' : '#FF8A65', textAlign: 'right', fontFamily: 'monospace' }}>{cond.passed ? '—' : gapPct ? `${parseFloat(gapPct) > 0 ? '+' : ''}${gapPct}%` : '—'}</span>
                <span style={{ fontSize: '11px', color: cond.passed ? '#444' : '#FF8A65', textAlign: 'right', fontFamily: 'monospace' }}>{cond.passed ? '—' : gapNum || '—'}</span>
              </div>
            )
          })}

          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 24px 0', borderTop: '1px solid rgba(255,255,255,0.05)', marginTop: '8px', fontSize: '11px', color: '#555', fontWeight: 600 }}>
            <span>Score Ponderado: <span style={{ color: scoreColor }}>{rule.score.toFixed(4)}</span> / {rule.min_score.toFixed(2)} mínimo</span>
            <span style={{ color: scoreColor, fontWeight: 700 }}>
              {rule.triggered ? '🟢 TODOS LOS CRITERIOS CUMPLIDOS' : `🔴 FALTAN ${Object.values(rule.conditions).filter((c: any) => !c.passed).length} CONDICIONES`}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

const formatValue = (val: any, field: string) => {
  if (val === null || val === undefined) return '—'
  const priceFields = ['price', 'basis', 'upper_1', 'upper_2', 'upper_3', 'upper_4', 'upper_5', 'upper_6', 'lower_1', 'lower_2', 'lower_3', 'lower_4', 'lower_5', 'lower_6']
  if (priceFields.includes(field)) return `$${parseFloat(val).toLocaleString('en-US', { maximumFractionDigits: 4 })}`
  if (typeof val === 'boolean') return val ? 'SÍ' : 'NO'
  if (typeof val === 'number') return parseFloat(val.toFixed(4)).toString()
  return String(val)
}

export default RuleDiagnosticPanel;
