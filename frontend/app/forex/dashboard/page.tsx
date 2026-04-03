"use client"
import { useState, useEffect } from 'react'
import TradeMarkerChart from '@/components/TradeMarkerChart'
import Link from 'next/link'
import ForexWelcomeScreen from '../WelcomeScreen'

const FOREX_PAIRS = [
  'EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD'
]

const PAIR_META: Record<string, any> = {
  EURUSD: { flag: '🇪🇺🇺🇸', name: 'Euro/USD', decimals: 5 },
  GBPUSD: { flag: '🇬🇧🇺🇸', name: 'GBP/USD', decimals: 5 },
  USDJPY: { flag: '🇺🇸🇯🇵', name: 'USD/JPY', decimals: 3 },
  XAUUSD: { flag: '🥇', name: 'Oro/USD', decimals: 2 },
}

export default function ForexDashboard() {
  const [snapshots, setSnapshots] = useState<any>({})
  const [focusPair, setFocusPair] = useState('EURUSD')
  const [connected, setConnected] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    checkConnection()
    const interval = setInterval(fetchSnapshots, 15000)
    return () => clearInterval(interval)
  }, [])

  const checkConnection = async () => {
    try {
      const res = await fetch('/api/v1/forex/status')
      const data = await res.json()
      setConnected(data.connected)
      if (data.connected) fetchSnapshots()
    } catch (err) {
      console.error("Connection check failed", err)
    } finally {
      setLoading(false)
    }
  }

  const fetchSnapshots = async () => {
    try {
      const res = await fetch('/api/v1/forex/snapshots')
      const data = await res.json()
      setSnapshots(data)
    } catch (err) {
      console.error("Fetch snapshots failed", err)
    }
  }

  if (loading) {
    return <div style={{ padding: '24px', color: '#666' }}>Cargando Forex Dashboard...</div>
  }

  if (!connected) {
    return <ForexWelcomeScreen />
  }

  return (
    <div style={{ padding: '24px' }}>
      {/* HEADER */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '24px',
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
          IC Markets ACTIVE
        </div>
      </div>

      {/* PAIR CARDS */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
        gap: '16px',
        marginBottom: '24px',
      }}>
        {FOREX_PAIRS.map(pair => {
          const snap = snapshots[pair] || {}
          const isFocus = pair === focusPair

          return (
            <ForexPairCard
              key={pair}
              pair={pair}
              snap={snap}
              isFocus={isFocus}
              onClick={() => setFocusPair(pair)}
            />
          )
        })}
      </div>

      {/* CHART + ANALYSIS PANEL */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 1fr) 340px',
        gap: '24px',
      }}>
        {/* GRÁFICO */}
        <div style={{
          background: 'rgba(17, 24, 39, 0.4)',
          backdropFilter: 'blur(12px)',
          border: '1px solid rgba(255, 255, 255, 0.04)',
          borderRadius: '16px',
          padding: '20px',
          minHeight: '520px',
          display: 'flex',
          flexDirection: 'column'
        }}>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '20px',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span style={{ fontSize: '20px' }}>{PAIR_META[focusPair]?.flag}</span>
              <span style={{ color: '#FFF', fontWeight: 900, fontSize: '18px', letterSpacing: '-0.02em' }}>
                {focusPair} <span style={{ color: '#555', fontSize: '12px', fontWeight: 600, marginLeft: '8px' }}>— PRICE CHART</span>
              </span>
            </div>
            {/* Selector timeframe */}
            <div style={{ display: 'flex', gap: '6px' }}>
              {['5m', '15m', '1h', '4h', '1d'].map(tf => (
                <button 
                  key={tf} 
                  onClick={() => {}}
                  style={{
                    padding: '6px 12px',
                    borderRadius: '6px',
                    border: '1px solid rgba(255,255,255,0.06)',
                    background: tf === '15m' ? 'rgba(79,195,247,0.15)' : 'rgba(255,255,255,0.02)',
                    color: tf === '15m' ? '#4FC3F7' : '#555',
                    fontSize: '11px',
                    fontWeight: 700,
                    cursor: 'pointer',
                    transition: 'all 0.2s'
                  }}
                >
                  {tf.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
          <div style={{ flex: 1, position: 'relative' }}>
             <TradeMarkerChart
                symbol={focusPair}
                timeframe="15m"
                candles={[]} // TODO: Fetch candles
                trades={[]} // TODO: Fetch trades
                height={420}
                basis={snapshots[focusPair]?.basis}
                upper_6={snapshots[focusPair]?.upper_6}
                lower_6={snapshots[focusPair]?.lower_6}
              />
          </div>
        </div>

        {/* PANEL DE ANÁLISIS */}
        <ForexAnalysisPanel
          pair={focusPair}
          snap={snapshots[focusPair] || {}}
        />
      </div>
    </div>
  )
}

function ForexPairCard({ pair, snap, isFocus, onClick }: any) {
  const meta = PAIR_META[pair] || {}
  const price = parseFloat(snap.price || 0)
  const mtf = parseFloat(snap.mtf_score || 0)
  const zone = parseInt(snap.fibonacci_zone || 0)
  const sar = snap.sar_phase || 'neutral'
  const hasPos = snap.has_position

  const sarColor = sar === 'long' ? '#00C896' : sar === 'short' ? '#FF4757' : '#666'

  return (
    <div
      onClick={onClick}
      style={{
        background: isFocus ? 'rgba(79,195,247,0.08)' : 'rgba(17, 24, 39, 0.4)',
        border: `1px solid ${isFocus ? 'rgba(79,195,247,0.40)' : 'rgba(255,255,255,0.06)'}`,
        borderRadius: '12px',
        padding: '16px',
        cursor: 'pointer',
        transition: 'all 0.3s ease',
        transform: isFocus ? 'scale(1.02)' : 'none',
        boxShadow: isFocus ? '0 10px 25px rgba(0,0,0,0.2)' : 'none'
      }}
    >
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '12px',
      }}>
        <span style={{ fontSize: '16px', fontWeight: 900, color: '#FFF', letterSpacing: '-0.02em' }}>
          {meta.flag} {pair}
        </span>
        <span style={{
          fontSize: '10px',
          fontWeight: 900,
          color: zone >= 0 ? '#00C896' : '#FF4757',
          background: 'rgba(255,255,255,0.03)',
          padding: '3px 8px',
          borderRadius: '20px',
          border: '1px solid rgba(255,255,255,0.05)'
        }}>
          ZONA {zone > 0 ? '+' : ''}{zone}
        </span>
      </div>

      <div style={{
        fontSize: '22px',
        fontWeight: 900,
        color: '#FFF',
        marginBottom: '10px',
        fontFamily: 'monospace',
        letterSpacing: '-0.05em'
      }}>
        {price.toFixed(meta.decimals || 5)}
      </div>

      <div style={{
        display: 'flex',
        gap: '8px',
        alignItems: 'center',
        marginBottom: '12px',
        background: 'rgba(0,0,0,0.2)',
        padding: '6px 10px',
        borderRadius: '8px'
      }}>
        <div style={{
          width: '8px',
          height: '8px',
          borderRadius: '50%',
          background: sarColor,
          boxShadow: `0 0 8px ${sarColor}`
        }} />
        <span style={{
          fontSize: '10px',
          color: sarColor,
          fontWeight: 800,
          textTransform: 'uppercase',
          letterSpacing: '0.05em'
        }}>
          FASE {sar.toUpperCase()} (SAR 4h)
        </span>
      </div>

      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        fontSize: '11px',
        color: '#555',
        fontWeight: 700
      }}>
        <span style={{ letterSpacing: '0.05em' }}>MTF SCORE</span>
        <span style={{
          color: mtf > 0 ? '#00C896' : mtf < 0 ? '#FF4757' : '#666',
          fontWeight: 900,
          fontSize: '12px'
        }}>
          {mtf.toFixed(2)}
        </span>
      </div>

      {hasPos ? (
        <div style={{
          marginTop: '12px',
          padding: '6px',
          background: 'rgba(0,200,150,0.15)',
          border: '1px solid rgba(0,200,150,0.20)',
          borderRadius: '6px',
          color: '#00C896',
          fontSize: '10px',
          fontWeight: 900,
          textAlign: 'center',
          letterSpacing: '0.1em'
        }}>
          POSICIÓN ACTIVA
        </div>
      ) : (
        <div style={{
          marginTop: '12px',
          padding: '6px',
          background: 'rgba(255,255,255,0.03)',
          border: '1px solid rgba(255,255,255,0.05)',
          borderRadius: '6px',
          color: '#444',
          fontSize: '10px',
          fontWeight: 700,
          textAlign: 'center',
          letterSpacing: '0.05em'
        }}>
          ESPERANDO SEÑAL
        </div>
      )}
    </div>
  )
}

function ForexAnalysisPanel({ pair, snap }: any) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: '20px'
    }}>
       <div style={{
         background: 'rgba(17, 24, 39, 0.4)',
         backdropFilter: 'blur(12px)',
         border: '1px solid rgba(255, 255, 255, 0.04)',
         borderRadius: '16px',
         padding: '24px',
         flex: 1
       }}>
          <h3 style={{ fontSize: '11px', fontWeight: 900, color: '#555', textTransform: 'uppercase', letterSpacing: '0.15em', marginBottom: '20px' }}>Análisis de Mercado — {pair}</h3>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
             <AnalysisRow label="MTF Bias" value={snap.mtf_score > 0 ? 'Bullish' : 'Bearish'} color={snap.mtf_score > 0 ? '#00C896' : '#FF4757'} />
             <AnalysisRow label="Fibonacci" value={`Zona ${snap.fibonacci_zone || 0}`} />
             <AnalysisRow label="SAR 15m" value={snap.sar_trend_15m > 0 ? 'UP' : 'DOWN'} />
             <AnalysisRow label="ADX Strength" value={snap.adx > 25 ? 'Strong' : 'Weak'} color={snap.adx > 25 ? '#4FC3F7' : '#666'} />
          </div>

          <div style={{ marginTop: '30px', paddingTop: '20px', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
             <div style={{ fontSize: '10px', fontWeight: 900, color: '#555', textTransform: 'uppercase', marginBottom: '12px' }}>Regulaciones IC Markets</div>
             <div style={{ fontSize: '12px', color: '#888', lineHeight: '1.6' }}>
                Spread: <span style={{ color: '#CCC' }}>0.0 - 0.1 pips</span><br/>
                Comisión: <span style={{ color: '#CCC' }}>$3.50 por lote</span><br/>
                Apalancamiento: <span style={{ color: '#CCC' }}>30:1</span>
             </div>
          </div>
       </div>
    </div>
  )
}

function AnalysisRow({ label, value, color = '#CCC' }: any) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ fontSize: '12px', color: '#555', fontWeight: 600 }}>{label}</span>
      <span style={{ fontSize: '13px', color: color, fontWeight: 900, fontFamily: 'monospace' }}>{value}</span>
    </div>
  )
}
