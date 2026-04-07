"use client"
import { useState, useEffect } from 'react'
import Link from 'next/link'

// Helper for UI
const TICKER_META: Record<string, any> = {
  AAPL:  { name: 'Apple Inc.',      sector: 'Tech',       emoji: '🍎' },
  MSFT:  { name: 'Microsoft',       sector: 'Tech',       emoji: '🪟' },
  NVDA:  { name: 'NVIDIA Corp.',    sector: 'Semis',      emoji: '🟢' },
  AMZN:  { name: 'Amazon',          sector: 'E-Commerce', emoji: '📦' },
  GOOGL: { name: 'Alphabet',        sector: 'Tech',       emoji: '🔍' },
  TSLA:  { name: 'Tesla Inc.',      sector: 'EV',         emoji: '⚡' },
}

export default function StocksDashboard() {
  const [loading, setLoading] = useState(true)
  const [triggering, setTriggering] = useState(false)
  const [regime, setRegime] = useState<any>({})
  const [status, setStatus] = useState<any>({})
  const [positions, setPositions] = useState<any[]>([])
  const [opportunities, setOpportunities] = useState<any[]>([])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 10000) // Poll every 10s
    return () => clearInterval(interval)
  }, [])

  const fetchData = async () => {
    try {
      const [resStatus, resRegime, resPos, resOpp] = await Promise.all([
        fetch('/api/v1/stocks/status').then(r => r.json()),
        fetch('/api/v1/stocks/regime').then(r => r.json()),
        fetch('/api/v1/stocks/positions').then(r => r.json()),
        fetch('/api/v1/stocks/opportunities').then(r => r.json())
      ])
      setStatus(resStatus)
      setRegime(resRegime)
      setPositions(resPos.positions || [])
      setOpportunities(resOpp.opportunities || [])
    } catch (err) {
      console.error("Dashboard fetch failed", err)
    } finally {
      setLoading(false)
    }
  }

  const triggerPipeline = async () => {
    setTriggering(true)
    try {
      await fetch('/api/v1/stocks/pipeline', { method: 'POST' })
      await fetchData()
    } catch (err) {
      console.error(err)
    } finally {
      setTriggering(false)
    }
  }

  if (loading) {
    return (
      <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#090A0F' }}>
        <div style={{ color: '#22C55E', fontWeight: 900, letterSpacing: '0.2em' }}>INICIANDO AI LAYER...</div>
      </div>
    )
  }

  const regimeColor = regime.regime === 'bull' ? '#22C55E' : regime.regime === 'bear' ? '#FF4757' : '#F59E0B'

  return (
    <div style={{ padding: '32px', minHeight: '100vh', background: 'radial-gradient(ellipse at top right, rgba(34,197,94,0.05), transparent 40%), #090A0F', color: '#FFF', fontFamily: 'Inter, sans-serif' }}>
      
      {/* --- HEADER --- */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
        <div>
          <div style={{ display: 'flex', gap: '8px', fontSize: '11px', fontWeight: 900, color: '#666', textTransform: 'uppercase', letterSpacing: '0.2em' }}>
            <Link href="/" style={{ color: '#22C55E', textDecoration: 'none' }}>eTrader v4.5</Link> <span>/</span> <span style={{ color: '#aaa' }}>Stocks</span>
          </div>
          <h1 style={{ fontSize: '32px', fontWeight: 900, margin: '8px 0 0 0', letterSpacing: '-0.03em', background: 'linear-gradient(90deg, #FFF, #AAA)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            AI Command Center
          </h1>
        </div>

        <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
          <div style={{ background: `${regimeColor}15`, border: `1px solid ${regimeColor}40`, borderRadius: '20px', padding: '8px 20px', color: regimeColor, fontSize: '12px', fontWeight: 800, letterSpacing: '0.05em', boxShadow: `0 0 15px ${regimeColor}20` }}>
            <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', background: regimeColor, marginRight: '10px', boxShadow: `0 0 8px ${regimeColor}` }}></span>
            {regime.regime ? regime.regime.toUpperCase() : 'SIDEWAYS'} MARKET
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button 
              onClick={triggerPipeline}
              disabled={triggering}
              style={{
                background: triggering ? '#333' : 'linear-gradient(135deg, #22C55E 0%, #16A34A 100%)',
                border: 'none', borderRadius: '12px', padding: '10px 24px', color: '#FFF', fontSize: '13px', fontWeight: 800, cursor: triggering ? 'wait' : 'pointer', transition: 'all 0.2s', boxShadow: '0 4px 15px rgba(34,197,94,0.3)'
              }}>
              {triggering ? '🧠 EXECUTING AI PIPELINE...' : '🚀 FORCE AI RUN'}
            </button>
            <Link 
              href="/stocks/opportunities"
              style={{
                background: 'rgba(6, 182, 212, 0.1)', border: '1px solid rgba(6, 182, 212, 0.3)', borderRadius: '12px', padding: '10px 24px', color: '#22d3ee', fontSize: '13px', fontWeight: 800, textDecoration: 'none', transition: 'all 0.2s'
              }}>
              🎯 VER OPORTUNIDADES DETECTADAS
            </Link>
          </div>
        </div>
      </div>

      {/* --- TOP METRICS GRID --- */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '20px', marginBottom: '32px' }}>
        <MetricCard label="NET CAPITAL" value={`$${status.capital_usd?.toLocaleString() || '0'}`} sub="Available Power" />
        <MetricCard label="ACTIVE TRADES" value={positions.length.toString()} sub="Market Exposure" color="#4FC3F7" />
        <MetricCard label="AI OPPORTUNITIES" value={opportunities.filter(o => o.status === 'pending').length.toString()} sub="Pending Review" color="#F59E0B" />
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '16px', padding: '20px', backdropFilter: 'blur(10px)' }}>
          <div style={{ fontSize: '11px', fontWeight: 800, color: '#666', letterSpacing: '0.1em', marginBottom: '12px' }}>SYSTEM INFRA</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}><span style={{color: '#888'}}>Engine</span><strong style={{color: '#22C55E'}}>Qwen+Claude</strong></div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}><span style={{color: '#888'}}>Broker</span><strong style={{color: status.paper_mode ? '#F59E0B' : '#22C55E'}}>{status.paper_mode ? 'Paper' : 'IB TWS'}</strong></div>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: '24px' }}>
        
        {/* --- LEFT: ACTIVE POSITIONS --- */}
        <div>
          <h2 style={{ fontSize: '16px', fontWeight: 800, color: '#FFF', marginBottom: '16px', letterSpacing: '-0.02em', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '20px' }}>⚔️</span> Live Engagements
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {positions.length === 0 ? (
              <div style={{ padding: '32px', textAlign: 'center', color: '#555', fontSize: '13px', background: 'rgba(255,255,255,0.02)', borderRadius: '16px', border: '1px dashed rgba(255,255,255,0.05)' }}>
                No active positions. AI is scanning the market.
              </div>
            ) : (
              positions.map(pos => <PositionCard key={pos.id} position={pos} />)
            )}
          </div>
        </div>

        {/* --- RIGHT: AI PIPELINE PIPELINE --- */}
        <div>
           <h2 style={{ fontSize: '16px', fontWeight: 800, color: '#FFF', marginBottom: '16px', letterSpacing: '-0.02em', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '20px' }}>🧠</span> Intel Queue
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {opportunities.length === 0 ? (
              <div style={{ padding: '32px', textAlign: 'center', color: '#555', fontSize: '13px', background: 'rgba(255,255,255,0.02)', borderRadius: '16px', border: '1px dashed rgba(255,255,255,0.05)' }}>
                Queue clear.
              </div>
            ) : (
              opportunities.slice(0, 5).map(opp => <OpportunityCard key={opp.id} opportunity={opp} />)
            )}
          </div>
        </div>

      </div>
    </div>
  )
}

// --- SUBCOMPONENTS ---

function MetricCard({ label, value, sub, color = '#22C55E' }: { label: string, value: string, sub: string, color?: string }) {
  return (
    <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '16px', padding: '20px', backdropFilter: 'blur(10px)' }}>
      <div style={{ fontSize: '11px', fontWeight: 800, color: '#666', letterSpacing: '0.1em', marginBottom: '8px' }}>{label}</div>
      <div style={{ fontSize: '28px', fontWeight: 900, color: color, letterSpacing: '-0.04em', marginBottom: '4px' }}>{value}</div>
      <div style={{ fontSize: '11px', color: '#555', fontWeight: 600 }}>{sub}</div>
    </div>
  )
}

function PositionCard({ position }: { position: any }) {
  const meta = TICKER_META[position.ticker] || { emoji: '📈' }
  const pnl = parseFloat(position.unrealized_pnl || '0')
  const pnlColor = pnl >= 0 ? '#22C55E' : '#FF4757'
  
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '16px', padding: '16px 20px', transition: 'transform 0.2s', cursor: 'pointer' }}>
      <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
        <div style={{ fontSize: '24px' }}>{meta.emoji}</div>
        <div>
          <div style={{ fontSize: '16px', fontWeight: 900, color: '#FFF' }}>{position.ticker}</div>
          <div style={{ fontSize: '12px', color: '#888', marginTop: '2px' }}>{position.shares} Shares @ ${position.entry_price}</div>
        </div>
      </div>
      <div style={{ textAlign: 'right' }}>
        <div style={{ fontSize: '16px', fontWeight: 900, color: pnlColor }}>{pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}</div>
        <div style={{ fontSize: '11px', color: '#666', fontWeight: 800, marginTop: '2px', display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
          <span>SL ${position.stop_loss}</span>
          <span>TP ${position.target_1}</span>
        </div>
      </div>
    </div>
  )
}

function OpportunityCard({ opportunity }: { opportunity: any }) {
  const meta = TICKER_META[opportunity.ticker] || { emoji: '🎯' }
  const isPending = opportunity.status === 'pending'
  const isExecuted = opportunity.status === 'executed'

  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.02)', border: `1px solid ${isPending ? 'rgba(245,158,11,0.2)' : 'rgba(255,255,255,0.03)'}`, borderRadius: '16px', padding: '16px', position: 'relative', overflow: 'hidden' }}>
      {isPending && <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: '3px', background: '#F59E0B' }} />}
      {isExecuted && <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: '3px', background: '#22C55E' }} />}
      
      <div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span style={{ fontSize: '14px', fontWeight: 900, color: '#FFF' }}>{meta.emoji} {opportunity.ticker}</span>
          <span style={{ fontSize: '9px', fontWeight: 900, padding: '2px 6px', borderRadius: '4px', background: 'rgba(255,255,255,0.05)', color: '#888' }}>QUAD {opportunity.quadrant}</span>
        </div>
        <div style={{ fontSize: '11px', color: '#666', marginTop: '6px' }}>MetaScore: <span style={{color: '#FFF', fontWeight: 800}}>{opportunity.meta_score}</span></div>
      </div>
      <div style={{ textAlign: 'right' }}>
        <div style={{ fontSize: '10px', fontWeight: 900, color: isPending ? '#F59E0B' : isExecuted ? '#22C55E' : '#FF4757', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
          {opportunity.status}
        </div>
      </div>
    </div>
  )
}
