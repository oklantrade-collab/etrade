"use client"
import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import TradeMarkerChart from '@/components/TradeMarkerChart'

export default function StocksDashboard() {
  const [loading, setLoading] = useState(true)
  const [triggering, setTriggering] = useState(false)
  const [status, setStatus] = useState<any>({
    capital_usd: 5000,
    universe_size: 0,
    daily_pnl: 0,
    paper_mode: true
  })
  const [regime, setRegime] = useState<any>({ regime: 'sideways', sm_avg: 4.5 })
  const [positions, setPositions] = useState<any[]>([])
  const [opportunities, setOpportunities] = useState<any[]>([])
  const [showChart, setShowChart] = useState(false)
  const [selectedTicker, setSelectedTicker] = useState('')

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 15000) 
    return () => clearInterval(interval)
  }, [])

  const fetchData = async () => {
    try {
      const [resStatus, resRegime, resPos, resOpp] = await Promise.all([
        fetch('/api/v1/stocks/status').then(r => r.ok ? r.json() : null),
        fetch('/api/v1/stocks/regime').then(r => r.ok ? r.json() : { regime: 'sideways', sm_avg: 4.2 }),
        fetch('/api/v1/stocks/positions').then(r => r.ok ? r.json() : { positions: [] }),
        fetch('/api/v1/stocks/opportunities').then(r => r.ok ? r.json() : { opportunities: [] })
      ])
      
      if (resStatus) setStatus(resStatus)
      if (resRegime) setRegime(resRegime)
      setPositions(resPos?.positions || [])
      setOpportunities(resOpp?.opportunities || [])
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
        <div style={{ color: '#22C55E', fontWeight: 900, letterSpacing: '0.2em', textAlign:'center' }}>
            <div style={{ fontSize:'24px', marginBottom:'10px' }}>🧠</div>
            INICIANDO COMANDO CENTRAL V5.0...
        </div>
      </div>
    )
  }

  const totalUnrealized = positions.reduce((acc, p) => acc + parseFloat(p.unrealized_pnl || 0), 0)
  const regimeColor = regime.regime === 'bull' ? '#22C55E' : regime.regime === 'bear' ? '#FF4757' : '#F59E0B'

  return (
    <div style={{ padding: '32px', minHeight: '100vh', background: 'radial-gradient(circle at 0% 0%, rgba(34,197,94,0.08), transparent 40%), #090A0F', color: '#FFF', fontFamily: 'Inter, sans-serif' }}>
      
      {/* HEADER SECTION */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '40px' }}>
        <div>
          <div style={{ display: 'flex', gap: '8px', fontSize: '10px', fontWeight: 950, color: '#444', textTransform: 'uppercase', letterSpacing: '0.2em', marginBottom:'8px' }}>
            STOCKS ENGINE <span style={{ color: '#22C55E' }}>• V5.0 PRO</span>
          </div>
          <h1 style={{ fontSize: '40px', fontWeight: 950, margin: 0, letterSpacing: '-0.04em', color:'#FFF' }}>
            Command Center
          </h1>
        </div>

        <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
           <div style={{ textAlign:'right', marginRight:'10px' }}>
                <div style={{ fontSize:'10px', color:'#666', fontWeight:900, textTransform:'uppercase', letterSpacing:'1px' }}>Market Sentiment</div>
                <div style={{ fontSize:'18px', fontWeight:950, color:regimeColor }}>{regime.sm_avg?.toFixed(1) || '4.2'} SM <span style={{fontSize:'12px', color:'#444', marginLeft:'5px'}}>{regime.regime?.toUpperCase()}</span></div>
           </div>
           <button 
              onClick={triggerPipeline}
              disabled={triggering}
              style={{
                background: triggering ? '#1A1D26' : '#22C55E',
                border: 'none', borderRadius: '14px', padding: '14px 28px', color: triggering ? '#444' : '#000', fontSize: '12px', fontWeight: 950, cursor: triggering ? 'wait' : 'pointer', transition: 'all 0.3s', boxShadow: triggering ? 'none' : '0 4px 20px rgba(34,197,94,0.3)'
              }}>
              {triggering ? '🧠 SYNCING...' : '🚀 FORCE FULL SCAN'}
            </button>
        </div>
      </div>

      {/* STRATEGIC METRICS */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '20px', marginBottom: '25px' }}>
        <MetricCard 
            label="UNIVERSE SCOPE" 
            value={status.universe_size || '120'} 
            sub="Stocks under surveillance" 
            icon="🌐"
        />
        <MetricCard 
            label="PORTFOLIO PULSE" 
            value={`$${totalUnrealized.toFixed(2)}`} 
            sub="Active Unrealized P&L" 
            color={totalUnrealized >= 0 ? '#22C55E' : '#FF4757'}
            icon="📈"
        />
        <MetricCard 
            label="PRO OPPORTUNITIES" 
            value={opportunities.length.toString()} 
            sub="Detected & Filtered" 
            color="#A855F7"
            icon="🎯"
        />
        <div style={{ background: '#161922', borderRadius: '24px', padding: '24px', border: '1px solid rgba(255,255,255,0.05)', display:'flex', flexDirection:'column', justifyContent:'center' }}>
            <div style={{ fontSize: '10px', fontWeight: 900, color: '#555', letterSpacing: '0.1em', marginBottom: '12px', textTransform:'uppercase' }}>System Status</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <StatusRow label="Environment" val={status.paper_mode ? 'PAPER' : 'LIVE'} color={status.paper_mode ? '#F59E0B' : '#22C55E'} />
                <StatusRow label="AI Models" val="Qwen + Gemini" color="#A855F7" />
                <StatusRow label="Execution" val="Automated" color="#38BDF8" />
            </div>
        </div>
      </div>
      
      {/* CAPITAL ALLOCATION PANEL */}
      <div style={{ background: 'linear-gradient(90deg, #161922, #0D0F14)', borderRadius: '24px', padding: '24px 32px', border: '1px solid rgba(34,197,94,0.1)', marginBottom: '40px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', gap: '40px' }}>
              <div>
                  <div style={{ fontSize: '10px', fontWeight: 900, color: '#555', letterSpacing: '0.1em', marginBottom: '8px', textTransform:'uppercase' }}>Total Capital</div>
                  <div style={{ fontSize: '24px', fontWeight: 950, color: '#FFF' }}>${status.capital_usd?.toLocaleString() || '5,000.00'}</div>
              </div>
              <div style={{ borderLeft: '1px solid rgba(255,255,255,0.05)', paddingLeft: '40px' }}>
                  <div style={{ fontSize: '10px', fontWeight: 900, color: '#555', letterSpacing: '0.1em', marginBottom: '8px', textTransform:'uppercase' }}>Used Capital</div>
                  <div style={{ fontSize: '24px', fontWeight: 950, color: '#F59E0B' }}>${positions.reduce((acc, p) => acc + (parseFloat(p.avg_price || 0) * parseInt(p.shares || 0)), 0).toLocaleString(undefined, {minimumFractionDigits: 2})}</div>
              </div>
              <div style={{ borderLeft: '1px solid rgba(255,255,255,0.05)', paddingLeft: '40px' }}>
                  <div style={{ fontSize: '10px', fontWeight: 900, color: '#22C55E', letterSpacing: '0.1em', marginBottom: '8px', textTransform:'uppercase' }}>Trading Enabled (60% Limit)</div>
                  <div style={{ fontSize: '24px', fontWeight: 950, color: '#22C55E' }}>
                      ${(
                          (parseFloat(status.capital_usd || 5000) * (status.max_risk_pct || 60) / 100) - 
                          positions.reduce((acc, p) => acc + (parseFloat(p.avg_price || 0) * parseInt(p.shares || 0)), 0)
                      ).toLocaleString(undefined, {minimumFractionDigits: 2})}
                  </div>
              </div>
          </div>
          <div style={{ width: '200px' }}>
                <div style={{ display:'flex', justifyContent:'space-between', marginBottom:'8px', fontSize:'10px', fontWeight:900, color:'#444' }}>
                    <span>RISK EXPOSURE ({status.max_risk_pct || 60}%)</span>
                    <span>{((positions.reduce((acc, p) => acc + (parseFloat(p.avg_price || 0) * parseInt(p.shares || 0)), 0) / parseFloat(status.capital_usd || 5000)) * 100).toFixed(1)}%</span>
                </div>
                <div style={{ width:'100%', height:'6px', background:'rgba(255,255,255,0.03)', borderRadius:'10px', overflow:'hidden' }}>
                    <div style={{ 
                        width: `${Math.min(100, (positions.reduce((acc, p) => acc + (parseFloat(p.avg_price || 0) * parseInt(p.shares || 0)), 0) / (parseFloat(status.capital_usd || 5000) * (status.max_risk_pct || 60) / 100)) * 100)}%`, 
                        height:'100%', 
                        background: (positions.reduce((acc, p) => acc + (parseFloat(p.avg_price || 0) * parseInt(p.shares || 0)), 0) > (parseFloat(status.capital_usd || 5000) * (status.max_risk_pct || 60) / 100)) ? '#FF4757' : '#22C55E', 
                        boxShadow: '0 0 10px rgba(34,197,94,0.4)' 
                    }}></div>
                </div>
          </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: '30px' }}>
        
        {/* LEFT: LIVE ENGAGEMENTS (POSITIONS) */}
        <div>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom: '20px' }}>
            <h2 style={{ fontSize: '18px', fontWeight: 950, color: '#FFF', letterSpacing: '-0.02em', display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ color: '#22C55E' }}>⚔️</span> Active Engagements
            </h2>
            <Link href="/stocks/positions" style={{ fontSize:'11px', color:'#666', textDecoration:'none', fontWeight:800 }}>VIEW ALL POSITIONS →</Link>
          </div>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
            {positions.length === 0 ? (
              <EmptyState icon="🛰️" text="No active positions. Scanning deep universe for high-conviction entries..." />
            ) : (
              positions.map((pos, idx) => <PositionRow key={pos.id || `pos-${pos.ticker}-${idx}`} pos={pos} onOpenChart={(ticker: string) => { setSelectedTicker(ticker); setShowChart(true); }} />)
            )}
          </div>
        </div>

        {/* RIGHT: OPPORTUNITY RADAR */}
        <div>
           <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom: '20px' }}>
            <h2 style={{ fontSize: '18px', fontWeight: 950, color: '#FFF', letterSpacing: '-0.02em', display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ color: '#A855F7' }}>🎯</span> Opportunity Radar
            </h2>
            <Link href="/stocks/opportunities" style={{ fontSize:'11px', color:'#666', textDecoration:'none', fontWeight:800 }}>GO TO SCANNER →</Link>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {opportunities.length === 0 ? (
              <EmptyState icon="🧠" text="Processing Layer 5 intelligence. No high-score opportunities in the immediate queue." />
            ) : (
              opportunities.slice(0, 6).map((opp, idx) => <RadarRow key={opp.id || `opp-${opp.ticker}-${idx}`} opp={opp} />)
            )}
          </div>
        </div>

      </div>
      {showChart && <ChartModal symbol={selectedTicker} onClose={() => setShowChart(false)} />}
    </div>
  )
}

// --- REUSABLE COMPONENTS ---

function MetricCard({ label, value, sub, icon, color = '#FFF' }: any) {
    return (
        <div style={{ background: '#161922', borderRadius: '24px', padding: '24px', border: '1px solid rgba(255,255,255,0.05)', position:'relative', overflow:'hidden' }}>
            <div style={{ fontSize:'24px', position:'absolute', top:'20px', right:'24px', opacity:0.1 }}>{icon}</div>
            <div style={{ fontSize: '10px', fontWeight: 900, color: '#555', letterSpacing: '0.1em', marginBottom: '10px', textTransform:'uppercase' }}>{label}</div>
            <div style={{ fontSize: '32px', fontWeight: 950, color: color, letterSpacing: '-0.05em', marginBottom: '6px' }}>{value}</div>
            <div style={{ fontSize: '11px', color: '#666', fontWeight: 700 }}>{sub}</div>
        </div>
    )
}

function StatusRow({ label, val, color }: any) {
    return (
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', fontWeight:800 }}>
            <span style={{color: '#444'}}>{label}</span>
            <span style={{color: color}}>{val}</span>
        </div>
    )
}

function PositionRow({ pos, onOpenChart }: any) {
    const pnl = parseFloat(pos.unrealized_pnl || 0)
    const pnlColor = pnl >= 0 ? '#22C55E' : '#FF4757'
    
    return (
        <div style={{ background: '#1A1D26', borderRadius: '20px', padding: '20px', border: '1px solid rgba(255,255,255,0.03)', display:'flex', justifyContent:'space-between', alignItems:'center' }}>
            <div style={{ display:'flex', gap:'15px', alignItems:'center' }}>
                <div style={{ width:'44px', height:'44px', background:'rgba(255,255,255,0.02)', borderRadius:'12px', display:'flex', alignItems:'center', justifyContent:'center', fontSize:'18px', fontWeight:950, color:'#FFF', border:'1px solid rgba(255,255,255,0.05)' }}>
                    {pos.ticker?.[0]}
                </div>
                <div>
                    <div style={{ fontSize:'16px', fontWeight:950, color:'#FFF' }}>{pos.ticker}</div>
                    <div style={{ fontSize:'11px', color:'#666', fontWeight:800 }}>Entry: <span style={{color:'#CCC'}}>${parseFloat(pos.avg_price || 0).toFixed(2)}</span> • Shares: <span style={{color:'#22C55E'}}>{pos.shares}</span></div>
                </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center' }}>
                <button 
                    onClick={() => onOpenChart(pos.ticker)}
                    style={{ background: '#38BDF8', color: '#000', border: 'none', padding: '8px 14px', borderRadius: '10px', fontSize: '10px', fontWeight: 950, cursor: 'pointer', marginRight: '20px', display: 'flex', alignItems: 'center', gap: '5px', transition: 'all 0.2s' }}
                    onMouseEnter={e => e.currentTarget.style.transform = 'scale(1.05)'}
                    onMouseLeave={e => e.currentTarget.style.transform = 'scale(1)'}
                >
                    VER GRÁFICO 📊
                </button>
                <div style={{ textAlign:'right' }}>
                    <div style={{ fontSize:'18px', fontWeight:950, color:pnlColor }}>{pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}</div>
                    <div style={{ fontSize:'10px', color:'#444', fontWeight:900, marginTop:'4px' }}>MOS: {pos.margin_of_safety || '0'}%</div>
                </div>
            </div>
        </div>
    )
}

function TradingViewWidget({ symbol }: { symbol: string }) {
  const containerId = `tv-chart-${symbol}`;
  const containerRef = useRef<HTMLDivElement>(null);
  
  useEffect(() => {
    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/tv.js";
    script.async = true;
    script.onload = () => {
      if ((window as any).TradingView && containerRef.current) {
        new (window as any).TradingView.widget({
          "autosize": true,
          "symbol": symbol,
          "interval": "D",
          "timezone": "Etc/UTC",
          "theme": "dark",
          "style": "1",
          "locale": "es",
          "toolbar_bg": "#161922",
          "enable_publishing": false,
          "allow_symbol_change": true,
          "container_id": containerId,
          "backgroundColor": "#0F1117",
          "gridColor": "rgba(255, 255, 255, 0.05)",
          "hide_side_toolbar": false,
          "studies": [
            "BB@tv-basicstudies",
            "MAExp@tv-basicstudies",
            "MAExp@tv-basicstudies"
          ],
          "overrides": {
            "mainSeriesProperties.style": 1,
          }
        });
      }
    };
    document.head.appendChild(script);
  }, [symbol, containerId]);

  return (
    <div ref={containerRef} id={containerId} style={{ height: '450px', width: '100%', borderRadius: '16px', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.1)' }} />
  );
}

function ChartModal({ symbol, onClose }: { symbol: string, onClose: () => void }) {
  return (
    <div style={{ position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', background: 'rgba(0,0,0,0.8)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100, backdropFilter: 'blur(5px)' }}>
        <div style={{ background: '#0F1117', width: '90%', height: '85%', borderRadius: '24px', border: '1px solid #38BDF8', overflow: 'hidden', display: 'flex', flexDirection: 'column', boxShadow: '0 0 50px rgba(56,189,248,0.2)' }}>
            <div style={{ padding: '15px 25px', background: '#161922', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                <h3 style={{ margin: 0, color: '#FFF', fontSize: '16px', fontWeight: 900 }}>GRÁFICO TÉCNICO: {symbol}</h3>
                <button onClick={onClose} style={{ background: '#EF4444', border: 'none', color: '#FFF', padding: '6px 15px', borderRadius: '8px', fontSize: '10px', fontWeight: 900, cursor: 'pointer' }}>CERRAR GRÁFICO</button>
            </div>
            <div style={{ flex: 1, background: '#000' }}>
                <TradingViewWidget symbol={symbol} />
            </div>
        </div>
    </div>
  )
}

function RadarRow({ opp }: any) {
    const score = opp.pro_score || opp.meta_score || 0
    return (
        <div style={{ background: 'rgba(255,255,255,0.01)', borderRadius: '16px', padding: '16px', border: '1px solid rgba(255,255,255,0.03)', display:'flex', justifyContent:'space-between', alignItems:'center' }}>
            <div style={{ display:'flex', gap:'12px', alignItems:'center' }}>
                <div style={{ fontSize:'14px', fontWeight:950, color:'#FFF' }}>{opp.ticker}</div>
                <div style={{ fontSize:'9px', color:'#A855F7', fontWeight:900, padding:'2px 6px', background:'rgba(168,85,247,0.1)', borderRadius:'6px' }}>SCORE: {score}</div>
            </div>
            <div style={{ fontSize:'10px', color:'#444', fontWeight:900, textTransform:'uppercase' }}>
                {opp.movement_type || 'ASCENDING'}
            </div>
        </div>
    )
}

function EmptyState({ icon, text }: any) {
    return (
        <div style={{ padding: '50px 30px', textAlign: 'center', background: 'rgba(255,255,255,0.01)', borderRadius: '24px', border: '1px dashed rgba(255,255,255,0.05)' }}>
            <div style={{ fontSize: '32px', marginBottom: '15px' }}>{icon}</div>
            <div style={{ fontSize: '12px', color: '#444', fontWeight: 800, maxWidth: '280px', margin: '0 auto', lineHeight: '1.6' }}>{text}</div>
        </div>
    )
}
