"use client"
import { useState, useEffect } from 'react'
import Link from 'next/link'

const formatAbbreviated = (num: any) => {
    const val = parseFloat(num);
    if (!val || isNaN(val)) return '0.00';
    if (val >= 1_000_000_000) return (val / 1_000_000_000).toFixed(2) + 'B';
    if (val >= 1_000_000) return (val / 1_000_000).toFixed(2) + 'M';
    if (val >= 1_000) return (val / 1_000).toFixed(2) + 'K';
    return val.toFixed(2);
};

export default function OpportunitiesIntelligence() {
  const [opportunities, setOpportunities] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [selectedStock, setSelectedStock] = useState<any | null>(null)
  const [activeTab, setActiveTab] = useState<'HOT' | 'VALUE'>('HOT')
  
  const [marketStatus, setMarketStatus] = useState({ is_open: true, status: 'ABIERTO' })
  
  const [settings, setSettings] = useState({
    hotMaxPrice: 50,
    proMaxPrice: 500,
    minRvol: 0.1,
    minVolume: 0,
    minMarketCap: 0,
    minValueGap: 15,
    maxHotResults: 50
  })
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 10000)
    return () => clearInterval(interval)
  }, [])

  const fetchData = async () => {
    try {
      const res = await fetch('/api/v1/stocks/opportunities')
      const data = await res.json()
      
      if (data.market_status) {
          setMarketStatus(data.market_status)
      }

      const raw = data.opportunities || []
      const uniqueMap = new Map();
      raw.forEach((item: any) => uniqueMap.set(item.ticker, item));
      setOpportunities(Array.from(uniqueMap.values()))
      setTotal(uniqueMap.size)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const hotList = opportunities
    .filter(o => o.price <= settings.hotMaxPrice && o.rvol >= settings.minRvol && o.volume >= settings.minVolume)
    .sort((a, b) => b.rvol - a.rvol)
    .slice(0, settings.maxHotResults);

  const valueList = opportunities.filter(o => o.is_pro_member);

  const displayList = activeTab === 'HOT' ? hotList : valueList;

  return (
    <div style={{ padding: '24px 32px', minHeight: '100vh', background: '#090A0F', color: '#FFF', fontFamily: 'Inter, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
        <div>
          <div style={{ fontSize: '10px', fontWeight: 900, color: '#22C55E', textTransform: 'uppercase', letterSpacing: '0.2em' }}>Intelligence Layer v4.5</div>
          <h1 style={{ fontSize: '24px', fontWeight: 900, margin: '4px 0', letterSpacing: '-0.02em' }}>🎯 AI Stock Scanner</h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <p style={{ color: '#555', fontSize: '12px' }}>{total} monitoreados · NYC Live Tracking</p>
              <span style={{ 
                fontSize: '10px', 
                background: marketStatus.is_open ? '#22C55E' : '#EF4444', 
                color: '#000', 
                padding: '1px 8px', 
                borderRadius: '4px', 
                fontWeight: 950, 
                textTransform: 'uppercase' 
              }}>
                {marketStatus.is_open ? '🟢' : '🔴'} MERCADO {marketStatus.status} | {new Date().toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' })}
              </span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
            <button onClick={() => setShowSettings(!showSettings)} style={{ background: showSettings ? '#22C55E' : 'rgba(255,255,255,0.05)', color: showSettings ? '#000' : '#FFF', border: 'none', padding: '10px 16px', borderRadius: '12px', fontSize: '12px', fontWeight: 900, cursor: 'pointer' }}>⚙️ FILTROS</button>
            <div style={{ display: 'flex', background: 'rgba(255,255,255,0.03)', padding: '4px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
                <TabButton label="🔥 Hot by Volume" active={activeTab === 'HOT'} onClick={() => setActiveTab('HOT')} count={hotList.length}/>
                <TabButton label="💎 Inversión Pro" active={activeTab === 'VALUE'} onClick={() => setActiveTab('VALUE')} count={valueList.length}/>
            </div>
        </div>
      </div>

      {showSettings && (
        <div style={{ background: '#161922', padding: '20px', borderRadius: '16px', marginBottom: '20px', border: '1px solid #22C55E', display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '15px' }}>
            <SettingInput label="Hot Price Max" value={settings.hotMaxPrice} onChange={(v:any) => setSettings({...settings, hotMaxPrice: Number(v)})} />
            <SettingInput label="Min RVOL" value={settings.minRvol} onChange={(v:any) => setSettings({...settings, minRvol: Number(v)})} step={0.1} />
            <SettingInput label="Min Volume" value={settings.minVolume} onChange={(v:any) => setSettings({...settings, minVolume: Number(v)})} step={100000} />
            <SettingInput label="Min Market Cap" value={settings.minMarketCap} onChange={(v:any) => setSettings({...settings, minMarketCap: Number(v)})} step={100000000} />
        </div>
      )}

      <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)', overflow: 'hidden' }}>
        <div style={{ 
            display: 'grid', 
            gridTemplateColumns: '70px 85px 75px 75px 75px 75px 70px 125px 65px 95px 35px 35px 35px 1fr', 
            padding: '12px 16px', borderBottom: '1px solid rgba(255,255,255,0.05)', fontSize: '9px', fontWeight: 900, color: '#444', textTransform: 'uppercase', letterSpacing: '0.1em', alignItems: 'center' 
        }}>
          <span title="Ticker de la acción">Ticker</span>
          <span title="Price Change: Variación del precio desde la apertura del día">% PRC</span>
          <span title="Precio actual de mercado">Precio</span>
          <span title="Volumen operado hoy (en millones de acciones)">Vol</span>
          <span title="Revenue Growth: Crecimiento de ingresos año tras año (YoY)">Rev G.</span>
          <span title="Fundamental Score: Salud financiera basada en el modelo Piotroski F-Score">F.Score</span>
          <span title="Estado de valoración intrínseca (Subvalorada/Sobrevalorada)">Valuation</span>
          <span title="Tipo de movimiento técnico y zona Fibonacci actual">Movimiento</span>
          <span title="Hora del último escaneo (NYC Time)">HH:MM</span>
          <span title="Indicador de actividad de órdenes abiertas">Orden</span>
          <span title="Technical Score: Puntuación de indicadores técnicos (0-100)">TS</span>
          <span title="Inteligencia Artificial: Score de sentimiento y análisis de catalizadores (0-10)">IA</span>
          <span title="Sentimiento de Mercado: Score de momentum intradiario (1-10)">SM</span>
          <span style={{textAlign:'right'}}>Accion</span>
        </div>
        {!loading && displayList.map((opp, i) => ( <ScannerRow key={opp.ticker} index={i} opp={opp} isPro={activeTab === 'VALUE'} onOpenDetails={() => setSelectedStock({ ...opp, isPro: activeTab === 'VALUE' })} /> ))}
        {!loading && displayList.length === 0 && <div style={{ padding: '60px', textAlign: 'center', color: '#444' }}>Monitoreando señales...</div>}
      </div>

      {selectedStock && <AnalysisModal stock={selectedStock} onClose={() => setSelectedStock(null)} />}
      <Link href="/stocks/universe" style={{ display: 'inline-block', marginTop: '20px', color: '#22C55E', textDecoration: 'none', fontWeight: 800, fontSize: '11px' }}>← VOLVER AL UNIVERSE BUILDER</Link>
    </div>
  )
}

function SettingInput({ label, value, onChange, step = 1 }: any) {
    return ( <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}><label style={{ fontSize: '9px', fontWeight: 900, color: '#666', textTransform: 'uppercase' }}>{label}</label><input type="number" step={step} value={value} onChange={(e) => onChange(e.target.value)} style={{ background: '#000', border: '1px solid #333', borderRadius: '8px', padding: '8px', color: '#22C55E', fontWeight: 900, fontSize: '12px' }} /></div> )
}
function TabButton({ label, active, onClick, count }: any) {
    return ( <button onClick={onClick} style={{ background: active ? '#161922' : 'transparent', color: active ? '#22C55E' : '#666', border: active ? '1px solid rgba(34,197,94,0.3)' : 'none', padding: '8px 20px', borderRadius: '10px', cursor: 'pointer', fontSize: '12px', fontWeight: 900, display: 'flex', alignItems: 'center', gap: '8px', transition: 'all 0.2s' }}>{label}<span style={{ fontSize: '9px', background: active ? 'rgba(34,197,94,0.2)' : 'rgba(255,255,255,0.05)', padding: '2px 6px', borderRadius: '4px', color: active ? '#22C55E' : '#555' }}>{count}</span></button> )
}

const OrderActivityIndicator = ({ orders }: { orders: any[] }) => {
  if (!orders || orders.length === 0) {
    return ( <span style={{ color: '#444', fontSize: '12px', display: 'flex', justifyContent: 'center' }}>❌</span> );
  }
  const lastOrder = orders[0]; 
  const isLimit = lastOrder.order_type === 'limit';
  const isBuy = lastOrder.direction === 'buy';
  const isFilled = lastOrder.status === 'filled';
  const isCancelled = lastOrder.status === 'cancelled' || lastOrder.status === 'expired';
  
  const color = isCancelled ? '#666' : (isBuy ? '#00C896' : '#FF4757');
  const label = isLimit ? (isFilled ? 'LIMIT ✓' : 'LIMIT ⏳') : (isBuy ? 'BUY' : 'SELL');
  const statusLabel = isFilled ? '' : (isCancelled ? ' (X)' : ' (?)');
  
  const bg = isBuy ? 'rgba(0,200,150,0.12)' : 'rgba(255,71,87,0.12)';
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '3px 8px', borderRadius: '4px', background: bg, fontSize: '9px', color: color, fontWeight: 800 }}>
      {isLimit ? '📍' : '⚡'} {label}{statusLabel} {lastOrder.limit_price && <span style={{ fontFamily:'monospace', marginLeft:'2px' }}>${parseFloat(lastOrder.limit_price).toFixed(2)}</span>}
    </div>
  );
}

const PiotroskiBadge = ({ score, detail }: { score: number, detail: any }) => {
  const [showTooltip, setShowTooltip] = useState(false)
  const color = score >= 7 ? '#00C896' : score >= 5 ? '#FFB74D' : score >= 3 ? '#FF8A65' : '#FF4757'
  return (
    <div style={{ position:'relative' }}>
      <div onMouseEnter={() => setShowTooltip(true)} onMouseLeave={() => setShowTooltip(false)} style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'help' }}>
        <span style={{ fontWeight: 700, color: color, fontFamily: 'monospace' }}>{score || 0}/9</span>
        <span style={{ fontSize: '9px', color: '#555' }}>F</span>
      </div>
      {showTooltip && detail && (
        <div style={{ position: 'absolute', top: '24px', left: '0', zIndex: 100, background: '#0D1117', border: '1px solid #333', borderRadius: '8px', padding: '12px', width: '280px', fontSize: '11px', boxShadow: '0 4px 20px rgba(0,0,0,0.5)' }}>
          <div style={{ fontWeight: 700, color:'#FFF', marginBottom:'8px' }}>Piotroski F-Score: {score}/9</div>
          {Object.entries(detail || {}).map(([key, val]: any) => (
            <div key={key} style={{ display:'flex', justifyContent:'space-between', padding:'2px 0', color: val.passed ? '#00C896' : '#FF4757' }}>
              <span>{val.passed ? '✓' : '✗'} {val.description}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const ValuationBadge = ({ intrinsic, price, margin, source }: any) => {
  if (!intrinsic) return <span style={{color:'#444'}}>—</span>
  const isUnder = price < intrinsic
  const color = isUnder ? '#00C896' : '#FF4757'
  return (
    <div style={{ fontSize:'11px' }}>
      <div style={{ color, fontWeight:700 }}>${formatAbbreviated(intrinsic)}</div>
      <div style={{ color:'#555', fontSize:'10px' }}>
        {margin > 0 ? '+' : ''}{parseFloat(margin).toFixed(1)}%{' '}
        <span style={{ color: source?.includes('ia') ? '#CE93D8' : '#4FC3F7', fontSize:'9px' }}>
          {source?.includes('ia') ? '⚡IA' : '📐'}
        </span>
      </div>
    </div>
  )
}

function ScannerRow({ opp, index, isPro, onOpenDetails }: any) {
  const rawIA = opp.pro_score || 0;
  const scoreIA = (rawIA > 10 ? rawIA / 10 : rawIA).toFixed(1);
  let displayScoreTech = 0;
  if (opp.t01_confirmed) displayScoreTech += 40;
  if (opp.t02_confirmed) displayScoreTech += 30;
  if (opp.t03_confirmed) displayScoreTech += 20;
  if (opp.t04_confirmed) displayScoreTech += 10;
  const getMovColor = (type: string) => { if (type?.includes('ascending')) return '#22C55E'; if (type?.includes('descending')) return '#EF4444'; return '#F59E0B'; };
  const rawMovement = isPro ? opp.movement_1d : opp.movement_15m;
  const fibZone = isPro ? opp.fib_zone_1d : opp.fib_zone_15m;
  let movementDisplay = rawMovement?.toUpperCase().replace('_', ' ') || '—';
  if (movementDisplay.includes('ASCENDING')) movementDisplay = movementDisplay.replace('ASCENDING', 'ASC');
  if (movementDisplay.includes('DESCENDING')) movementDisplay = movementDisplay.replace('DESCENDING', 'DESC');
  if (fibZone !== undefined && fibZone !== null && movementDisplay !== '—') movementDisplay = `${movementDisplay} F(${fibZone})`;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '70px 85px 75px 75px 75px 75px 70px 125px 65px 95px 35px 35px 35px 1fr', padding: '10px 16px', borderBottom: '1px solid rgba(255,255,255,0.02)', alignItems: 'center', background: index % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
      <div style={{ display:'flex', alignItems:'center', gap: '4px' }}>
          <span style={{ fontWeight: 900, color: '#FFF', fontSize: '13px' }}>{opp.ticker}</span>
          {(opp.intrinsic_value > opp.price && opp.intrinsic_value > 0) && (
            <span style={{ fontSize: '7px', background: '#22C55E', color: '#000', padding: '1px 3px', borderRadius: '2px', fontWeight: 950 }}>VALOR</span>
          )}
      </div>
      <div style={{ display:'flex', alignItems:'center', gap:'3px' }}>
          <span style={{ color:(opp.change_pct || 0) >= 0 ? '#22C55E' : '#EF4444', fontWeight:950, fontSize:'12px' }}>
            {opp.change_pct > 0 ? '+' : ''}{(opp.change_pct || 0).toFixed(2)}%
          </span>
      </div>
      <span style={{ fontWeight: 700, fontSize:'12px' }}>${opp.price.toFixed(2)}</span>
      <span style={{ fontWeight: 800, fontSize:'11px', color: '#888' }}>{(opp.volume / 1_000_000).toFixed(2)}M</span>
      <span style={{ color:(opp.rev_growth || 0) >= 0 ? '#22C55E' : '#EF4444', fontWeight:900, fontSize:'11px' }}>{opp.rev_growth > 0 ? '+' : ''}{opp.rev_growth}%</span>
      <PiotroskiBadge score={opp.piotroski_score} detail={opp.piotroski_detail} />
      <ValuationBadge intrinsic={opp.composite_intrinsic} price={opp.price} margin={opp.margin_of_safety} source={opp.data_source} />
      <span style={{ color: getMovColor(rawMovement), fontSize: '10px', fontWeight: 900, textTransform: 'uppercase' }}>{movementDisplay}</span>
      <div style={{ display:'flex', flexDirection:'column' }}>
        <span style={{ fontSize:'8px', color:'#444', fontWeight:800 }}>{opp.created_at ? new Date(opp.created_at).toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit' }) : '--/--'}</span>
        <span style={{ fontSize:'10px', color:'#555', fontWeight:800, fontFamily:'monospace' }}>{opp.last_scan_time || '—:—'}</span>
      </div>
      <OrderActivityIndicator orders={opp.orders || []} />
      <span style={{ color: displayScoreTech >= 70 ? '#22C55E' : '#F59E0B', fontWeight: 950, fontSize:'11px' }}>{displayScoreTech}</span>
      <span style={{ color: Number(scoreIA) >= 7.5 ? '#A855F7' : '#22C55E', fontWeight: 950, fontSize:'11px' }}>{scoreIA}</span>
      <span style={{ color: Number(opp.sm_score) >= 7.5 ? '#FF4757' : (Number(opp.sm_score) >= 5 ? '#F59E0B' : '#666'), fontWeight: 950, fontSize:'11px' }}>{opp.sm_score?.toFixed(1) || '1.0'}</span>
      <div style={{textAlign:'right'}}>
        <button onClick={onOpenDetails} title="Analizar Empresa" style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)', color: '#22C55E', width: '28px', height: '28px', borderRadius: '50%', fontSize: '12px', cursor: 'pointer', display: 'inline-flex', justifyContent: 'center', alignItems: 'center', transition: 'all 0.2s' }} onMouseEnter={e => e.currentTarget.style.background = 'rgba(34,197,94,0.2)'} onMouseLeave={e => e.currentTarget.style.background = 'rgba(34,197,94,0.1)'} >🔍</button>
      </div>
    </div>
  )
}

function AnalysisModal({ stock, onClose }: any) {
  let displayScoreTech = 0;
  if (stock.t01_confirmed) displayScoreTech += 40;
  if (stock.t02_confirmed) displayScoreTech += 30;
  if (stock.t03_confirmed) displayScoreTech += 20;
  if (stock.t04_confirmed) displayScoreTech += 10;
  const rawIA = stock.pro_score || 0;
  const iaAvg = (rawIA > 10 ? rawIA / 10 : rawIA).toFixed(1);
  const uv = stock.margin_of_safety || 0;
  const iv = stock.composite_intrinsic || 0;

  return (
    <div style={{ position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', background: 'rgba(0,0,0,0.95)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, backdropFilter: 'blur(10px)' }}>
      <div style={{ background: '#0F1117', width: '95%', maxWidth: '1150px', borderRadius: '24px', border: '1px solid #22C55E', overflow: 'hidden', maxHeight: '95vh', display: 'flex', flexDirection: 'column', boxShadow: '0 0 50px rgba(34,197,94,0.2)' }}>
        
        {/* HEADER */}
        <div style={{ padding: '20px 30px', background: '#161922', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: '22px', fontWeight: 900, color: '#FFF' }}>{stock.ticker} - {stock.company_name || stock.ticker}</h2>
            <div style={{ display:'flex', gap:'10px', marginTop:'4px' }}>
                <span style={{ fontSize: '10px', color: '#22C55E', fontWeight: 900, textTransform: 'uppercase' }}>SECTOR: {stock.sector || 'TECHNOLOGY'} | V4.5 PRO LAYER</span>
                <span style={{ fontSize: '10px', color: '#AAA', fontWeight: 700 }}>FUENTE: {stock.data_source?.toUpperCase()}</span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '15px', alignItems:'center' }}>
            {iv > 0 && (
                <div style={{ border: '2px solid #22C55E', padding: '6px 16px', borderRadius: '12px', background: 'rgba(34,197,94,0.05)', textAlign: 'center' }}>
                    <div style={{ fontSize: '8px', color: '#22C55E', fontWeight: 950 }}>VALORACIÓN INTRÍNSECA ({uv > 0 ? '+' : ''}{uv.toFixed(1)}%)</div>
                    <div style={{ fontSize: '12px', color: '#FFF', fontWeight: 950 }}>{stock.valuation_status?.toUpperCase() || 'FAIR VALUE'}</div>
                </div>
            )}
            <div style={{ border: '1px solid #A855F7', padding: '8px 20px', borderRadius: '14px', background: 'rgba(168,85,247,0.1)', textAlign: 'center' }}>
                <div style={{ fontSize: '10px', color: '#A855F7', fontWeight: 900 }}>PRO SCORE (IA + MATH)</div>
                <div style={{ fontSize: '22px', color: '#FFF', fontWeight: 950 }}>{iaAvg} / 10</div>
            </div>
            <button onClick={onClose} style={{ background: 'rgba(255,255,255,0.05)', border: 'none', color: '#FFF', width: '36px', height: '36px', borderRadius: '50%', cursor: 'pointer' }}>✕</button>
          </div>
        </div>

        <div style={{ padding: '25px 30px', overflowY: 'auto', display: 'grid', gridTemplateColumns: '380px 1fr', gap: '30px' }}>
            {/* IZQUIERDA: CAPA 1 & 2 (TÉCNICO Y UNIVERSO) */}
            <div style={{ display:'flex', flexDirection:'column', gap:'20px' }}>
                <div>
                    <h3 style={{ fontSize: '11px', letterSpacing: '1px', fontWeight: 950, color: '#22C55E', marginBottom: '15px' }}>CAPA 2: TÉCNICO OPERATIVO</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                        <RuleBox id="T01" name="Señal PineScript 'B' (4H)" val={stock.t01_confirmed ? 'Confirmada (Buy)' : 'FAIL'} pts="+40 PTS" pass={stock.t01_confirmed} c="#A855F7" />
                        <RuleBox id="T02" name="EMA Alineación (1D)" val={stock.t02_confirmed ? 'EMA 50 > 200' : 'FAIL'} pts="+30 PTS" pass={stock.t02_confirmed} c="#38BDF8" />
                        <RuleBox id="T03" name="Cierre de Vela (4H)" val={stock.t03_confirmed ? 'Verde (Optimista)' : 'FAIL'} pts="+20 PTS" pass={stock.t03_confirmed} c="#22C55E" />
                        <RuleBox id="T04" name="RSI Momentum (40-70)" val={stock.t04_confirmed ? 'Momentum OK' : 'FAIL'} pts="+10 PTS" pass={stock.t04_confirmed} c="#F59E0B" />
                    </div>
                </div>

                <div style={{ background: '#0D0E14', padding: '20px', borderRadius: '16px', border:'1px solid rgba(255,255,255,0.05)', display:'flex', gap:'20px', alignItems:'center' }}>
                    <div style={{ textAlign:'center' }}>
                        <div style={{ fontSize: '10px', color: '#F59E0B', fontWeight: 950, marginBottom:'4px' }}>RESUMEN TÉCNICO</div>
                        <div style={{ fontSize: '48px', fontWeight: 950, color: '#22C55E', lineHeight:'1' }}>{displayScoreTech}</div>
                        <div style={{ fontSize: '8px', color: '#666', fontWeight: 900 }}>PUNTUACIÓN CAPA 2</div>
                    </div>
                    <div style={{ flex:1, display:'flex', flexDirection:'column', gap:'6px' }}>
                        <div style={{ display:'flex', justifyContent:'space-between', fontSize:'10px', fontWeight:700 }}>
                            <span style={{ color:'#888' }}>Pool Universo (Capa 1)</span>
                            <span style={{ color: '#FFF' }}>{stock.pool_type || 'STANDARD'}</span>
                        </div>
                        <div style={{ display:'flex', justifyContent:'space-between', fontSize:'10px', fontWeight:700 }}>
                            <span style={{ color:'#888' }}>Market Cap (Capa 1)</span>
                            <span style={{ color: '#FFF' }}>${formatAbbreviated(stock.market_cap)}</span>
                        </div>
                        <div style={{ display:'flex', justifyContent:'space-between', fontSize:'10px', fontWeight:700 }}>
                            <span style={{ color:'#888' }}>RVOL (Relativo)</span>
                            <span style={{ color: (stock.rvol||0) >= 1.2 ? '#22C55E' : '#FFF' }}>{stock.rvol?.toFixed(1) || '1.0'}x</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* DERECHA: CAPA 3, 4 & 5 (VALUATION, EXPERTS, AI) */}
            <div style={{ display:'flex', flexDirection:'column', gap:'20px' }}>
                <div>
                   <h3 style={{ fontSize: '11px', letterSpacing: '1px', fontWeight: 950, color: '#A855F7', marginBottom: '15px' }}>CAPA 3: VALORACIÓN MATEMÁTICA (ENGINE)</h3>
                   <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
                        <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
                            <div style={{ fontSize:'9px', color:'#AAA', fontWeight:800 }}>PIOTROSKI F-SCORE</div>
                            <div style={{ fontSize:'20px', color: stock.piotroski_score >= 7 ? '#00C896' : '#FFB74D', fontWeight:900 }}>{stock.piotroski_score || 0}/9</div>
                        </div>
                        <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
                            <div style={{ fontSize:'9px', color:'#AAA', fontWeight:800 }}>ALTMAN Z-SCORE</div>
                            <div style={{ fontSize:'20px', color: stock.altman_zone === 'safe' ? '#00C896' : '#FF4757', fontWeight:900 }}>{stock.altman_z_score?.toFixed(2) || '0.00'}</div>
                        </div>
                        <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
                            <div style={{ fontSize:'9px', color:'#AAA', fontWeight:800 }}>GRAHAM NUMBER</div>
                            <div style={{ fontSize:'16px', color: '#FFF', fontWeight:900 }}>${formatAbbreviated(stock.graham_number)}</div>
                        </div>
                        <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
                            <div style={{ fontSize:'9px', color:'#AAA', fontWeight:800 }}>DCF INTRINSIC</div>
                            <div style={{ fontSize:'16px', color: '#FFF', fontWeight:900 }}>${formatAbbreviated(stock.dcf_intrinsic)}</div>
                        </div>
                   </div>
                </div>

                <div>
                    <h3 style={{ fontSize: '11px', letterSpacing: '1px', fontWeight: 950, color: '#F59E0B', marginBottom: '15px' }}>CAPA 4 & 5: SUSTENTO DE INTELIGENCIA E IA</h3>
                    <div style={{ display:'flex', flexDirection:'column', gap:'12px' }}>
                        {/* CAPA 4: EXPERTS */}
                        <div style={{ background: 'rgba(34,197,94,0.05)', padding: '16px', borderRadius: '12px', border: '1px solid rgba(34,197,94,0.3)' }}>
                            <div style={{ display:'flex', justifyContent:'space-between', marginBottom:'10px' }}>
                                <span style={{ fontSize:'10px', color:'#22C55E', fontWeight:950 }}>CONSENSO DE EXPERTOS (NYC) - CAPA 4</span>
                                <span style={{ background:'#22C55E', color:'#000', padding:'2px 8px', borderRadius:'10px', fontSize:'10px', fontWeight:950 }}>{stock.analyst_rating ? stock.analyst_rating.toFixed(1) : '—'}/10</span>
                            </div>
                            <div style={{ fontSize: '12px', color: '#DDD', lineHeight: '1.6', whiteSpace: 'pre-wrap' }}>
                                {stock.ai_rationale || (
                                    <>
                                        Puntaje matemático de valoración: <span style={{color:'#FFF', fontWeight:700}}>{stock.math_score?.toFixed(1) || '0.0'} / 10</span>. 
                                        Sustentado en Piotroski (Salud), Graham (Valor) y DCF (Futuro). 
                                        {stock.data_source?.includes('ia') ? ' Validado por consenso de analistas de Wall Street.' : ' Modo matemático puro activo por redundancia.'}
                                    </>
                                )}
                            </div>
                        </div>
                        {/* CAPA 6: MOMENTUM (SM) */}
                        <div style={{ background: 'rgba(239,68,68,0.05)', padding: '16px', borderRadius: '12px', border: '1px solid rgba(239,68,68,0.2)' }}>
                            <div style={{ display:'flex', justifyContent:'space-between', marginBottom:'10px' }}>
                                <span style={{ fontSize:'10px', color:'#EF4444', fontWeight:950 }}>SCORING DE MOMENTUM INTRADIARIO (IB) - SM</span>
                                <span style={{ background:'#EF4444', color:'#000', padding:'2px 8px', borderRadius:'10px', fontSize:'10px', fontWeight:950 }}>{stock.sm_score?.toFixed(1) || '1.0'}/10</span>
                            </div>
                            <div style={{ fontSize: '11px', color: '#DDD', lineHeight: '1.6' }}>
                                <div style={{ marginBottom: '8px', fontWeight: 700 }}>Fórmula: (V1*0.3 + V2*0.2 + V3*0.1 + V4*0.25 + V5*0.15) × 10</div>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                                    <div style={{ color: '#AAA' }} title="Relative Volume: Volumen actual comparado con su promedio de 3 meses.">
                                        • <span style={{ borderBottom: '1px dashed #555', cursor: 'help' }}>RVOL (V1)</span>: <span style={{ color: '#FFF' }}>{stock.rvol?.toFixed(2)}x</span>
                                    </div>
                                    <div style={{ color: '#AAA' }} title="Sentiment Score: Tendencia del sentimiento social diario (-3 a +3).">
                                        • <span style={{ borderBottom: '1px dashed #555', cursor: 'help' }}>S Score (V2)</span>: <span style={{ color: '#FFF' }}>{stock.s_score?.toFixed(1) || '0.0'}</span>
                                    </div>
                                    <div style={{ color: '#AAA' }} title="Social Volume Score: Intensidad de la conversación social (0 a 10).">
                                        • <span style={{ borderBottom: '1px dashed #555', cursor: 'help' }}>SV Score (V3)</span>: <span style={{ color: '#FFF' }}>{stock.sv_score?.toFixed(1) || '5.0'}</span>
                                    </div>
                                    <div style={{ color: '#AAA' }} title="Catalyst Score: Relevancia de noticias, reportes o eventos recientes.">
                                        • <span style={{ borderBottom: '1px dashed #555', cursor: 'help' }}>Catalyst (V4)</span>: <span style={{ color: '#FFF' }}>{stock.catalyst_score}/10</span>
                                    </div>
                                    <div style={{ color: '#AAA' }} title="Technical Score: Puntuación basada en indicadores de precio (RSI, EMAs, Velas).">
                                        • <span style={{ borderBottom: '1px dashed #555', cursor: 'help' }}>Technical (V5)</span>: <span style={{ color: '#FFF' }}>{displayScoreTech}/100</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* CAPA 5: AI */}
                        <div style={{ background: '#161922', padding: '16px', borderRadius: '12px', border: '1px solid rgba(168,85,247,0.2)' }}>
                            <div style={{ display:'flex', justifyContent:'space-between', marginBottom:'10px' }}>
                                <span style={{ fontSize:'10px', color:'#A855F7', fontWeight:950 }}>IA ENRICHMENT (LAYER 5) - SUSTENTO NARRATIVO</span>
                                <span style={{ background:'#A855F7', padding:'2px 8px', borderRadius:'10px', fontSize:'10px', fontWeight:950 }}>{(stock.ia_score || 0).toFixed(1)}/10</span>
                            </div>
                            <div style={{ fontSize: '12px', color: '#BBB', lineHeight: '1.6', fontStyle: 'italic' }}>
                                {stock.gemini_summary || stock.qwen_summary || stock.ai_summary || "La IA procesa en tiempo real noticias, reportes de ganancias y sentimiento de mercado para validar si el 'momentum' técnico y el valor fundamental tienen un catalizador real."}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div style={{ padding: '20px 30px', textAlign: 'right', background: '#161922', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            <button onClick={onClose} style={{ background: '#22C55E', color: '#000', padding: '12px 60px', borderRadius: '12px', fontSize: '12px', fontWeight: 950, cursor: 'pointer', textTransform:'uppercase', letterSpacing:'1px' }}>Cerrar Panel de Análisis</button>
        </div>
      </div>
    </div>
  )
}

function RuleBox({id, name, val, pts, pass, c = '#22C55E'}: any) {
    return ( 
      <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px 16px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
              <div style={{ fontSize: '10px', color: c, fontWeight: 950, marginBottom: '2px' }}>{id} • {name}</div>
              <div style={{ fontSize: '12px', color: '#FFF', fontWeight: 700 }}>{val}</div>
          </div>
          <div style={{ fontSize: '10px', fontWeight: 950, color: pass ? '#22C55E' : '#555' }}>
             {typeof pts === 'number' ? `+${pts}` : pts}
          </div>
      </div> 
    )
}
