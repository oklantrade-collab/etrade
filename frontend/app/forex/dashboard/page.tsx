"use client"
import { useState, useEffect } from 'react'
import Link from 'next/link'
import ForexWelcomeScreen from '../WelcomeScreen'
import TradeMarkerChart from '@/components/TradeMarkerChart'

const FOREX_PAIRS = [
  'EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD'
]

const PAIR_META: Record<string, any> = {
  EURUSD: { flag: '🇪🇺🇺🇸', name: 'Euro / USD', decimals: 5 },
  GBPUSD: { flag: '🇬🇧🇺🇸', name: 'GBP / USD', decimals: 5 },
  USDJPY: { flag: '🇺🇸🇯🇵', name: 'USD / JPY', decimals: 3 },
  XAUUSD: { flag: '🥇', name: 'Oro / USD', decimals: 2 },
}

export default function ForexDashboard() {
  const [snapshots, setSnapshots] = useState<any>({})
  const [focusPair, setFocusPair] = useState('EURUSD')
  const [candles, setCandles] = useState<any[]>([])
  const [trades, setTrades] = useState<any[]>([])
  const [timeframe, setTimeframe] = useState('15m')
  const [connected, setConnected] = useState(false)
  const [loading, setLoading] = useState(true)
  const [activePositions, setActivePositions] = useState<any[]>([])
  const [activePosition, setActivePosition] = useState<any>(null)

  useEffect(() => {
    checkConnection()
    const intervalSnap = setInterval(fetchSnapshots, 15000)
    const intervalCandles = setInterval(() => loadChartData(focusPair, false), 30000)
    const intervalPos = setInterval(fetchPositions, 10000)
    return () => {
        clearInterval(intervalSnap)
        clearInterval(intervalCandles)
        clearInterval(intervalPos)
    }
  }, [focusPair, timeframe])

  const checkConnection = async () => {
    try {
      const res = await fetch('/api/v1/forex/status')
      if (res.ok) {
        const data = await res.json().catch(() => ({ connected: false }))
        setConnected(data.connected)
        if (data.connected) {
            fetchSnapshots()
            loadChartData(focusPair, true)
            fetchPositions()
        }
      }
    } catch (err) {
      console.error("Connection check failed", err)
    } finally {
      setLoading(false)
    }
  }

  const fetchSnapshots = async () => {
    try {
      const res = await fetch('/api/v1/forex/snapshots')
      if (res.ok) {
        const data = await res.json().catch(() => ({}))
        setSnapshots(data)
      }
    } catch (err) {
      console.error("Fetch snapshots failed", err)
    }
  }

  const loadChartData = async (pair: string, isInitial: boolean = false) => {
    if (isInitial) {
      setCandles([]) // Reset to avoid scale mixup
      setTrades([])
    }
    try {
      const [cRes, tRes] = await Promise.all([
        fetch(`/api/v1/forex/candles?symbol=${pair}&timeframe=${timeframe}`),
        fetch(`/api/v1/market/trade-events/${pair}?days=15`)
      ])
      
      if (cRes.ok) {
        try {
          const data = await cRes.json()
          setCandles(Array.isArray(data) ? data : [])
        } catch (e) { console.error("Bad candles JSON", e) }
      }
      if (tRes.ok) {
        try {
          const tData = await tRes.json()
          setTrades(Array.isArray(tData) ? tData : [])
        } catch (e) { console.error("Bad trades JSON", e) }
      }
    } catch (err) {
      console.error('Error loading chart data:', err)
    }
  }

  const fetchPositions = async () => {
    try {
      const res = await fetch('/api/v1/forex/positions')
      if (res.ok) {
        const data = await res.json().catch(() => [])
        setActivePositions(data || [])
        const currentPos = data.find((p: any) => p.symbol === focusPair)
        setActivePosition(currentPos || null)
      }
    } catch (err) {
      console.error("Fetch positions failed", err)
    }
  }

  if (loading) {
    return <div style={{ padding: '24px', color: '#666' }}>Cargando Forex Dashboard...</div>
  }

  if (!connected) return <ForexWelcomeScreen />

  const snap = snapshots[focusPair] || {}

  return (
    <div style={{ padding: '24px' }}>
      {/* HEADER */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '20px',
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <div style={{ display: 'flex', gap: '8px', fontSize: '11px', fontWeight: 900, color: '#555', textTransform: 'uppercase', letterSpacing: '0.15em' }}>
            <Link href="/portfolio" style={{ color: '#4FC3F7', textDecoration: 'none' }}>Portfolio</Link>
            <span>/</span>
            <span style={{ color: '#888' }}>Forex</span>
          </div>
          <h1 style={{ fontSize: '24px', fontWeight: 900, color: '#FFF', margin: 0, fontStyle: 'italic', letterSpacing: '-0.02em' }}>💱 Forex Command Center</h1>
          <p style={{ color: '#555', fontSize: '12px', marginTop: '2px' }}>IC Markets — cTrader LIVE</p>
        </div>
        <div style={{
          background: 'rgba(0,200,150,0.10)',
          border: '1px solid #00C89622',
          borderRadius: '8px',
          padding: '8px 16px',
          color: '#00C896',
          fontSize: '12px',
          fontWeight: 700
        }}>
          <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', background: '#00C896', marginRight: '8px', boxShadow: '0 0 8px #00C896' }}></span>
          IC MARKETS ACTIVE
        </div>
      </div>

      {/* POSITIONS BAR (PREVIOUS SECTION) */}
      {activePositions.length > 0 && (
          <div style={{ display: 'flex', gap: '12px', marginBottom: '20px', overflowX: 'auto', paddingBottom: '8px' }}>
              {activePositions.map((p: any) => {
                  const s = snapshots[p.symbol] || {}
                  const curPrice = parseFloat(s.price || 0)
                  const isBuy = p.side?.toLowerCase() === 'long' || p.side?.toLowerCase() === 'buy'
                  const pipSize = p.symbol.includes('JPY') || p.symbol.includes('XAU') ? 0.01 : 0.0001
                  const pips = curPrice > 0 ? (isBuy ? (curPrice - p.entry_price) / pipSize : (p.entry_price - curPrice) / pipSize) : 0
                  
                  return (
                      <div key={p.id} style={{
                          flex: '0 0 auto',
                          background: 'rgba(255,255,255,0.03)',
                          border: `1px solid ${isBuy ? '#00C89644' : '#FF475744'}`,
                          borderRadius: '12px',
                          padding: '10px 16px',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '12px',
                          minWidth: '220px'
                      }}>
                          <div style={{ 
                              background: isBuy ? '#00C89622' : '#FF475722', 
                              color: isBuy ? '#00C896' : '#FF4757',
                              fontSize: '10px', fontWeight: 900, padding: '4px 8px', borderRadius: '6px'
                          }}>
                              {isBuy ? 'BUY' : 'SELL'}
                          </div>
                          <div>
                              <div style={{ fontSize: '12px', fontWeight: 900, color: '#FFF' }}>{p.symbol} <span style={{ opacity: 0.4, fontWeight: 500 }}>{p.lots}L</span></div>
                              <div style={{ fontSize: '9px', color: '#555' }}>Ent: {p.entry_price.toFixed(3)}</div>
                          </div>
                          <div style={{ marginLeft: 'auto', fontSize: '12px', fontWeight: 900, color: pips >= 0 ? '#00C896' : '#FF4757', fontStyle: 'italic' }}>
                            {pips >= 0 ? '+' : ''}{pips.toFixed(1)} P
                          </div>
                      </div>
                  )
              })}
          </div>
      )}

      {/* PAIR CARDS - ALL IN ONE ROW (RESTORED DESIGN) */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: '12px',
        marginBottom: '24px',
      }}>
        {FOREX_PAIRS.map(pair => (
          <ForexPairCard
            key={pair}
            pair={pair}
            snap={snapshots[pair] || {}}
            isFocus={pair === focusPair}
            position={activePositions.find(p => p.symbol === pair)}
            onClick={() => setFocusPair(pair)}
          />
        ))}
      </div>

      {/* CHART + ANALYSIS */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '24px' }}>
        <div style={{ background: 'rgba(17,17,25,0.4)', backdropFilter: 'blur(12px)', border: '1px solid rgba(255,255,255,0.04)', borderRadius: '16px', overflow: 'hidden' }}>
          <div style={{ padding: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span style={{ fontSize: '20px' }}>{PAIR_META[focusPair]?.flag}</span>
              <span style={{ color: '#FFF', fontWeight: 900, fontSize: '18px', fontStyle: 'italic' }}>{focusPair} <span style={{ color: '#555', fontSize: '12px', fontStyle: 'normal' }}>— PRICE CHART</span></span>
            </div>
            <div style={{ display: 'flex', gap: '6px' }}>
              {['5m', '15m', '1h', '4h', '1d'].map(tf => (
                <button key={tf} onClick={() => setTimeframe(tf)} style={{
                  padding: '6px 12px', borderRadius: '6px', border: `1px solid ${timeframe === tf ? '#00C896' : 'rgba(255,255,255,0.06)'}`,
                  background: timeframe === tf ? 'rgba(0,200,150,0.15)' : 'rgba(255,255,255,0.02)', color: timeframe === tf ? '#00C896' : '#555', cursor: 'pointer', fontSize: '11px', fontWeight: 700
                }}> {tf.toUpperCase()} </button>
              ))}
            </div>
          </div>
          <div style={{ flex: 1, padding: '10px' }}>
             <TradeMarkerChart
                symbol={focusPair} 
                timeframe={timeframe} 
                candles={candles} 
                activePosition={activePosition} 
                trades={trades} 
                height={460}
                basis={snap.basis} 
                upper_1={snap.upper_1} 
                lower_1={snap.lower_1}
                upper_6={snap.upper_6}
                lower_6={snap.lower_6}
                precision={PAIR_META[focusPair]?.decimals ?? 5}
                minMove={1 / Math.pow(10, PAIR_META[focusPair]?.decimals ?? 5)}
              />
          </div>
        </div>
        <ForexAnalysisPanel pair={focusPair} snap={snap} activePosition={activePosition} />
      </div>
    </div>
  )
}

function ForexPairCard({ pair, snap, isFocus, position, onClick }: any) {
  const meta = PAIR_META[pair] || {}
  const price = parseFloat(snap.price || 0)
  const zone = parseInt(snap.fibonacci_zone || 0)
  const sar = snap.sar_phase || 'neutral'
  const sarColor = sar === 'long' ? '#00C896' : sar === 'short' ? '#FF4757' : '#666'
  const hasPos = !!position
  const isBuy = position?.side?.toLowerCase() === 'long' || position?.side?.toLowerCase() === 'buy'

  return (
    <div
      onClick={onClick}
      style={{
        background: isFocus ? 'rgba(0,200,150,0.04)' : 'rgba(17, 24, 39, 0.4)',
        border: `1px solid ${hasPos ? (isBuy ? '#00C896' : '#FF4757') : (isFocus ? 'rgba(0,200,150,0.20)' : 'rgba(255,255,255,0.06)')}`,
        borderRadius: '12px',
        padding: '12px 14px',
        cursor: 'pointer',
        transition: 'all 0.3s ease',
        position: 'relative',
        boxShadow: hasPos ? `0 0 15px ${isBuy ? '#00C89622' : '#FF475722'}` : 'none'
      }}
    >
      {hasPos && (
          <div style={{ position: 'absolute', top: '8px', right: '8px', background: isBuy ? '#00C896' : '#FF4757', color: '#000', fontSize: '8px', fontWeight: 900, padding: '2px 5px', borderRadius: '4px' }}>
              {isBuy ? 'BUY' : 'SELL'}
          </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
        <span style={{ fontSize: '13px', fontWeight: 900, color: '#FFF' }}>{meta.flag} {pair}</span>
        <span style={{ fontSize: '9px', fontWeight: 900, color: zone > 0 ? '#00C896' : zone < 0 ? '#FF4757' : '#555' }}>ZONA {zone}</span>
      </div>
      <div style={{ fontSize: '18px', fontWeight: 900, color: price > 0 ? '#FFF' : '#333', marginBottom: '8px', fontFamily: 'monospace' }}>
        {price > 0 ? price.toFixed(meta.decimals || (pair === 'USDJPY' ? 3 : 5)) : '—'}
      </div>
      <div style={{ display: 'flex', gap: '6px', alignItems: 'center', background: 'rgba(0,0,0,0.2)', padding: '5px 8px', borderRadius: '6px' }}>
        <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: sarColor, boxShadow: `0 0 5px ${sarColor}` }} />
        <span style={{ fontSize: '9px', color: sarColor, fontWeight: 800 }}>FASE {sar.toUpperCase()}</span>
      </div>
    </div>
  )
}

function ForexAnalysisPanel({ pair, snap, activePosition }: any) {
  const meta = PAIR_META[pair] || {}
  const isBuy = activePosition?.side?.toLowerCase() === 'long' || activePosition?.side?.toLowerCase() === 'buy'
  const pnl = activePosition ? (activePosition.pnl_usd || activePosition.unrealized_pnl || 0) : 0
  const pnlColor = pnl >= 0 ? '#00C896' : '#FF4757'

  return (
    <div style={{
       background: 'rgba(17, 24, 39, 0.4)', backdropFilter: 'blur(12px)', border: '1px solid rgba(255, 255, 255, 0.04)', borderRadius: '16px', padding: '24px', flex: 1
    }}>
       <h3 style={{ fontSize: '11px', fontWeight: 900, color: '#555', textTransform: 'uppercase', letterSpacing: '0.15em', marginBottom: '20px' }}>Análisis — {pair}</h3>
       <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <AnalysisRow label="Sentimiento" value={snap.sar_phase === 'long' ? 'ALCISTA' : 'BAJISTA'} color={snap.sar_phase === 'long' ? '#00C896' : '#FF4757'} />
          <AnalysisRow label="Zona Actual" value={`Fibo ${snap.fibonacci_zone || 0}`} />
          <AnalysisRow label="SAR 15m" value={snap.sar_trend_15m > 0 ? 'LONG' : 'SHORT'} color={snap.sar_trend_15m > 0 ? '#00C896' : '#FF4757'} />
          <AnalysisRow label="Basis (EMA)" value={snap.basis ? parseFloat(snap.basis).toFixed(meta.decimals || 5) : '—'} />
          
          {activePosition && (
             <>
                <AnalysisRow label="Estrategia" value={activePosition.rule_code || 'Manual'} color="#4FC3F7" />
                <AnalysisRow label="Live P&L" value={`${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)} USD`} color={pnlColor} />
             </>
          )}

          <div style={{ marginTop: '10px', paddingTop: '15px', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
             <div style={{ fontSize: '10px', fontWeight: 900, color: '#555', textTransform: 'uppercase', marginBottom: '10px' }}>Estatus de Posición</div>
             {activePosition ? (
                <div style={{ 
                    background: isBuy ? 'rgba(0,200,150,0.1)' : 'rgba(255,71,87,0.1)', 
                    padding: '12px', 
                    borderRadius: '12px', 
                    border: `1px solid ${isBuy ? 'rgba(0,200,150,0.2)' : 'rgba(255,71,87,0.2)'}`,
                    boxShadow: `0 0 10px ${isBuy ? 'rgba(0,200,150,0.05)' : 'rgba(255,71,87,0.05)'}`
                }}>
                   <div style={{ color: isBuy ? '#00C896' : '#FF4757', fontSize: '11px', fontWeight: 900 }}>
                       COMPRADO: {activePosition.side.toUpperCase()}
                   </div>
                   <div style={{ color: '#AAA', fontSize: '10px', marginTop: '4px', fontFamily: 'monospace' }}>
                       Entry: {parseFloat(activePosition.entry_price).toFixed(meta.decimals || 5)}
                   </div>
                </div>
             ) : ( <div style={{ fontSize: '12px', color: '#555', fontWeight: 700 }}>SIN POSICIÓN ACTIVA</div> )}
          </div>
       </div>
    </div>
  )
}

function AnalysisRow({ label, value, color = '#CCC' }: any) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ fontSize: '11px', color: '#555', fontWeight: 600 }}>{label}</span>
      <span style={{ fontSize: '12px', color: color, fontWeight: 900 }}>{value}</span>
    </div>
  )
}
