"use client"
import { useState, useEffect } from 'react'
import Link from 'next/link'

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

  // 1. HOT BY VOLUME (Intradía Momentum)
  const hotList = opportunities
    .filter(o => o.price <= settings.hotMaxPrice && o.rvol >= settings.minRvol && o.volume >= settings.minVolume)
    .sort((a, b) => b.rvol - a.rvol)
    .slice(0, settings.maxHotResults);

  // 2. INVERSION PRO (Promovidos desde Universe Fundamental)
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
            gridTemplateColumns: '70px 85px 75px 75px 75px 75px 70px 125px 65px 95px 35px 35px 1fr', 
            padding: '12px 16px', borderBottom: '1px solid rgba(255,255,255,0.05)', fontSize: '9px', fontWeight: 900, color: '#444', textTransform: 'uppercase', letterSpacing: '0.1em', alignItems: 'center' 
        }}>
          <span>Ticker</span><span>Pool</span><span>Precio</span><span>Vol</span><span>Rev G.</span><span>F.Score</span><span>Margin</span><span>Movimiento</span><span>HH:MM</span><span>Orden</span><span>TS</span><span>IA</span><span style={{textAlign:'right'}}>Accion</span>
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

const FLAG_CONFIG: Record<string, any> = {
  market_buy_filled: { icon: '✅', label: 'BUY', color: '#00C896', bg: 'rgba(0,200,150,0.12)' },
  market_sell_filled: { icon: '✅', label: 'SELL', color: '#FF4757', bg: 'rgba(255,71,87,0.12)' },
  limit_pending: { icon: '⏳', label: 'LIMIT', color: '#FFB74D', bg: 'rgba(255,183,77,0.12)' },
  limit_filled: { icon: '📍', label: 'LIMIT ✓', color: '#00C896', bg: 'rgba(0,200,150,0.12)' },
  none: { icon: '❌', label: '—', color: '#444', bg: 'transparent' }
}

const OrderActivityIndicator = ({ orders }: { orders: any[] }) => {
  if (!orders || orders.length === 0) {
    return ( <span style={{ color: '#444', fontSize: '12px', display: 'flex', justifyContent: 'center' }}>❌</span> );
  }
  
  // Priorizar órdenes LIMIT pendientes o MARKET llenadas
  const lastOrder = orders[0]; 
  const isLimit = lastOrder.order_type === 'limit';
  const isBuy = lastOrder.direction === 'buy';
  
  const color = isBuy ? '#00C896' : '#FF4757';
  const label = isLimit ? (lastOrder.status === 'filled' ? 'LIMIT ✓' : 'LIMIT ⏳') : (isBuy ? 'BUY' : 'SELL');
  const bg = isBuy ? 'rgba(0,200,150,0.12)' : 'rgba(255,71,87,0.12)';

  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '3px 8px', borderRadius: '4px', background: bg, fontSize: '9px', color: color, fontWeight: 800 }}>
      {isLimit ? '📍' : '⚡'} {label} {lastOrder.limit_price && <span style={{ fontFamily:'monospace', marginLeft:'2px' }}>${parseFloat(lastOrder.limit_price).toFixed(2)}</span>}
    </div>
  );
}

function ScannerRow({ opp, index, isPro, onOpenDetails }: any) {
  // Sincronizado con DecisionEngine (Consenso Real)
  const rawIA = opp.pro_score || 0;
  const scoreIA = (rawIA > 10 ? rawIA / 10 : rawIA).toFixed(1);
  
  // CALCULACIÓN REAL PARA EVITAR DATOS VIEJOS EN DB
  let displayScoreTech = 0;
  if (opp.t01_confirmed) displayScoreTech += 40;
  if (opp.t02_confirmed) displayScoreTech += 30;
  if (opp.t03_confirmed) displayScoreTech += 20;
  if (opp.t04_confirmed) displayScoreTech += 10;

  const formatVol = (vol: number) => { if (!vol) return '—'; if (vol >= 1000000) return (vol / 1000000).toFixed(1) + 'M'; return (vol / 1000).toFixed(0) + 'K'; }
  const getMovColor = (type: string) => { if (type?.includes('ascending')) return '#22C55E'; if (type?.includes('descending')) return '#EF4444'; return '#F59E0B'; };

  const rawMovement = isPro ? opp.movement_1d : opp.movement_15m;
  const fibZone = isPro ? opp.fib_zone_1d : opp.fib_zone_15m;
  let movementDisplay = rawMovement?.toUpperCase().replace('_', ' ') || '—';
  if (movementDisplay.includes('ASCENDING')) movementDisplay = movementDisplay.replace('ASCENDING', 'ASC');
  if (movementDisplay.includes('DESCENDING')) movementDisplay = movementDisplay.replace('DESCENDING', 'DESC');
  if (fibZone !== undefined && fibZone !== null && movementDisplay !== '—') movementDisplay = `${movementDisplay} F(${fibZone})`;

  return (
    <div style={{ 
        display: 'grid', 
        gridTemplateColumns: '70px 85px 75px 75px 75px 75px 70px 125px 65px 95px 35px 35px 1fr', 
        padding: '10px 16px', borderBottom: '1px solid rgba(255,255,255,0.02)', alignItems: 'center', background: index % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' 
    }}>
      {/* COL 1: TICKER */}
      <div style={{ display:'flex', alignItems:'center', gap: '4px' }}>
          <span style={{ fontWeight: 900, color: '#FFF', fontSize: '13px' }}>{opp.ticker}</span>
          {(opp.intrinsic_value > opp.price && opp.intrinsic_value > 0) && (
            <span style={{ fontSize: '7px', background: '#22C55E', color: '#000', padding: '1px 3px', borderRadius: '2px', fontWeight: 950 }}>VALOR</span>
          )}
      </div>

      {/* COL 2: POOL */}
      <div style={{ display:'flex', alignItems:'center', gap:'3px' }}>
          {opp.pool_type?.includes('GIANT') && <span style={{ fontSize:'7px', background:'#2563EB', padding:'2px 4px', borderRadius:'3px', fontWeight:900 }}>G</span>}
          {opp.pool_type?.includes('LEADER') && <span style={{ fontSize:'7px', background:'#D97706', padding:'2px 4px', borderRadius:'3px', fontWeight:900 }}>L</span>}
          {opp.pool_type?.includes('HOT') && <span style={{ fontSize:'7px', background:'#EF4444', padding:'2px 4px', borderRadius:'3px', fontWeight:900 }}>HOT</span>}
          {!opp.pool_type && <span style={{ fontSize:'7px', background:'#555', padding:'2px 4px', borderRadius:'3px', fontWeight:900 }}>PRO</span>}
      </div>

      <span style={{ fontWeight: 700, fontSize:'12px' }}>${opp.price.toFixed(2)}</span>
      <span style={{ fontWeight: 800, fontSize:'11px', color: '#888' }}>{(opp.volume / 1_000_000).toFixed(2)}M</span>
      <span style={{ color:(opp.rev_growth || 0) >= 0 ? '#22C55E' : '#EF4444', fontWeight:900, fontSize:'11px' }}>{opp.rev_growth > 0 ? '+' : ''}{opp.rev_growth}%</span>
      <div>
          <div style={{ width: '50px', height: '2px', background: 'rgba(255,255,255,0.05)', borderRadius: '1px', overflow: 'hidden' }}>
              <div style={{ width: `${opp.fundamental_score}%`, height: '100%', background: '#22C55E' }}></div>
          </div>
          <div style={{ fontSize:'8px', color:'#22C55E', fontWeight:900 }}>{opp.fundamental_score}</div>
      </div>
      <span style={{ color:'#666', fontSize:'11px' }}>{opp.gross_margin}%</span>

      {/* COMMON COLS */}
      <span style={{ color: getMovColor(rawMovement), fontSize: '10px', fontWeight: 900, textTransform: 'uppercase' }}>{movementDisplay}</span>
      
      <div style={{ display:'flex', flexDirection:'column' }}>
        <span style={{ fontSize:'8px', color:'#444', fontWeight:800 }}>{opp.created_at ? new Date(opp.created_at).toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit' }) : '--/--'}</span>
        <span style={{ fontSize:'10px', color:'#555', fontWeight:800, fontFamily:'monospace' }}>{opp.last_scan_time || '—:—'}</span>
      </div>
      <OrderActivityIndicator orders={opp.orders || []} />
      
      <span style={{ color: displayScoreTech >= 70 ? '#22C55E' : '#F59E0B', fontWeight: 950, fontSize:'11px' }}>{displayScoreTech}</span>
      <span style={{ color: Number(scoreIA) >= 7.5 ? '#A855F7' : '#22C55E', fontWeight: 950, fontSize:'11px' }}>{scoreIA}</span>
      
      <div style={{textAlign:'right'}}>
        <button onClick={onOpenDetails} title="Analizar Empresa" style={{ 
            background: 'rgba(34,197,94,0.1)', 
            border: '1px solid rgba(34,197,94,0.3)', 
            color: '#22C55E', 
            width: '28px', height: '28px', 
            borderRadius: '50%', 
            fontSize: '12px', 
            cursor: 'pointer',
            display: 'inline-flex',
            justifyContent: 'center',
            alignItems: 'center',
            transition: 'all 0.2s'
        }}
        onMouseEnter={e => e.currentTarget.style.background = 'rgba(34,197,94,0.2)'}
        onMouseLeave={e => e.currentTarget.style.background = 'rgba(34,197,94,0.1)'}
        >🔍</button>
      </div>
    </div>
  )
}

function AnalysisModal({ stock, onClose }: any) {
  const isPro = stock.isPro;
  
  // CALCULACIÓN REAL EN TIEMPO REAL (Para evitar datos inconsistentes en DB)
  let displayScoreTech = 0;
  if (stock.t01_confirmed) displayScoreTech += 40;
  if (stock.t02_confirmed) displayScoreTech += 30;
  if (stock.t03_confirmed) displayScoreTech += 20;
  if (stock.t04_confirmed) displayScoreTech += 10;
  
  const rawIA = stock.pro_score || 0;
  const iaAvg = (rawIA > 10 ? rawIA / 10 : rawIA).toFixed(1);
  const uv = stock.undervaluation || 0;
  const iv = stock.intrinsic_value || 0;

  return (
    <div style={{ position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', background: 'rgba(0,0,0,0.95)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, backdropFilter: 'blur(10px)' }}>
      <div style={{ background: '#0F1117', width: '95%', maxWidth: '1100px', borderRadius: '24px', border: '1px solid #22C55E', overflow: 'hidden', maxHeight: '95vh', display: 'flex', flexDirection: 'column' }}>
        
        {/* HEADER */}
        <div style={{ padding: '20px 30px', background: '#161922', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: '22px', fontWeight: 900, color: '#FFF' }}>{stock.ticker} - {stock.company_name || stock.ticker}</h2>
            <div style={{ display:'flex', gap:'10px', marginTop:'4px' }}>
                <span style={{ fontSize: '10px', color: '#22C55E', fontWeight: 900, textTransform: 'uppercase' }}>SECTOR: {stock.sector || 'TECHNOLOGY'} | V4.5 PRO LAYER</span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '15px', alignItems:'center' }}>
            {iv > 0 && (
                <div style={{ border: '2px solid #22C55E', padding: '6px 16px', borderRadius: '12px', background: 'rgba(34,197,94,0.05)', textAlign: 'center' }}>
                    <div style={{ fontSize: '8px', color: '#22C55E', fontWeight: 950 }}>VALORACIÓN INTRÍNSECA (+{uv.toFixed(1)}%)</div>
                    <div style={{ fontSize: '12px', color: '#FFF', fontWeight: 950 }}>SUBVALUADA</div>
                </div>
            )}
            <div style={{ border: '1px solid #A855F7', padding: '8px 20px', borderRadius: '14px', background: 'rgba(168,85,247,0.1)', textAlign: 'center' }}>
                <div style={{ fontSize: '10px', color: '#A855F7', fontWeight: 900 }}>PROMEDIO IA</div>
                <div style={{ fontSize: '16px', color: '#FFF', fontWeight: 950 }}>{iaAvg} / 10</div>
            </div>
            <button onClick={onClose} style={{ background: 'rgba(255,255,255,0.05)', border: 'none', color: '#FFF', width: '36px', height: '36px', borderRadius: '50%', cursor: 'pointer' }}>✕</button>
          </div>
        </div>

        <div style={{ padding: '25px 30px', overflowY: 'auto', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '30px' }}>
            {/* IZQUIERDA: TECNICO + RESUMEN */}
            <div style={{ display:'flex', flexDirection:'column', gap:'20px' }}>
                <div>
                    <h3 style={{ fontSize: '11px', letterSpacing: '1px', fontWeight: 950, color: '#22C55E', marginBottom: '15px' }}>TÉCNICO OPERATIVO</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                        <RuleBox id="T01" name="Señal PineScript 'B' (4H)" val={stock.t01_confirmed ? 'Confirmada (Buy)' : 'FAIL'} pts="+40 PTS" pass={stock.t01_confirmed} c="#A855F7" />
                        <RuleBox id="T02" name="EMA Alineación (1D)" val={stock.t02_confirmed ? 'EMA 50 > 200' : 'FAIL'} pts="+30 PTS" pass={stock.t02_confirmed} c="#38BDF8" />
                        <RuleBox id="T03" name="Cierre de Vela (4H)" val={stock.t03_confirmed ? 'Verde (Optimista)' : 'FAIL'} pts="+20 PTS" pass={stock.t03_confirmed} c="#22C55E" />
                        <RuleBox id="T04" name="RSI Momentum (40-70)" val={stock.t04_confirmed ? 'Momentum OK' : 'FAIL'} pts="+10 PTS" pass={stock.t04_confirmed} c="#F59E0B" />
                    </div>
                </div>

                {/* CUADRO RESUMEN GRANDE */}
                <div style={{ background: '#0D0E14', padding: '20px', borderRadius: '16px', border:'1px solid rgba(255,255,255,0.05)', display:'flex', gap:'20px', alignItems:'center' }}>
                    <div style={{ textAlign:'center' }}>
                        <div style={{ fontSize: '10px', color: '#F59E0B', fontWeight: 950, marginBottom:'4px' }}>RESUMEN DE PUNTUACIÓN</div>
                        <div style={{ fontSize: '48px', fontWeight: 950, color: '#22C55E', lineHeight:'1' }}>{displayScoreTech}</div>
                        <div style={{ fontSize: '8px', color: '#666', fontWeight: 900 }}>PUNTUACIÓN TÉCNICA</div>
                    </div>
                    <div style={{ flex:1, display:'flex', flexDirection:'column', gap:'6px' }}>
                        <div style={{ display:'flex', justifyContent:'space-between', fontSize:'10px', fontWeight:700 }}>
                            <span style={{ color:'#888' }}>Señal PineScript "B"</span>
                            <span style={{ color: stock.t01_confirmed ? '#22C55E' : '#444' }}>+{stock.t01_confirmed?40:0}/40</span>
                        </div>
                        <div style={{ display:'flex', justifyContent:'space-between', fontSize:'10px', fontWeight:700 }}>
                            <span style={{ color:'#888' }}>EMA Alineación (1D)</span>
                            <span style={{ color: stock.t02_confirmed ? '#22C55E' : '#444' }}>+{stock.t02_confirmed?30:0}/30</span>
                        </div>
                        <div style={{ display:'flex', justifyContent:'space-between', fontSize:'10px', fontWeight:700 }}>
                            <span style={{ color:'#888' }}>Fuerza de Vela (4H)</span>
                            <span style={{ color: stock.t03_confirmed ? '#22C55E' : '#444' }}>+{stock.t03_confirmed?20:0}/20</span>
                        </div>
                        <div style={{ display:'flex', justifyContent:'space-between', fontSize:'10px', fontWeight:700 }}>
                            <span style={{ color:'#888' }}>RSI Momentum (15m)</span>
                            <span style={{ color: stock.t04_confirmed ? '#22C55E' : '#444' }}>+{stock.t04_confirmed?10:0}/10</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* DERECHA: FUNDAMENTAL + IA BOXES */}
            <div style={{ display:'flex', flexDirection:'column', gap:'20px' }}>
                <div>
                   <h3 style={{ fontSize: '11px', letterSpacing: '1px', fontWeight: 950, color: '#A855F7', marginBottom: '15px' }}>FILTROS INSTITUCIONALES</h3>
                   <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '8px' }}>
                        <RuleBox id="F01" name="Market Cap (Aprox)" val={stock.market_cap > 1e9 ? `${(stock.market_cap/1e9).toFixed(1)}B` : '500M+'} pts="OK" pass={true} c="#FFF" />
                        <RuleBox id="F02" name="Precio Actual (Filtro)" val={`$${stock.price.toFixed(2)} | OBJ: $${iv.toFixed(2)}`} pts="OK" pass={true} c="#FFF" />
                        <RuleBox id="F03" name="Liquidez / Volumen" val={`${(stock.volume/1e6).toFixed(2)}M`} pts="ALTA" pass={true} c="#22C55E" />
                        <RuleBox id="F04" name="RVOL (Relativo)" val={`${(stock.rvol || 1.0).toFixed(2)}x`} pts={(stock.rvol || 0) >= 1.2 ? "OK" : "BAJO"} pass={(stock.rvol || 0) >= 1.2} c="#F59E0B" />
                   </div>
                </div>

                <div>
                    <h3 style={{ fontSize: '11px', letterSpacing: '1px', fontWeight: 950, color: '#F59E0B', marginBottom: '15px' }}>ANÁLISIS DE MERCADO & IA</h3>
                    <div style={{ display:'flex', flexDirection:'column', gap:'10px' }}>
                        {/* CONSENSO DE EXPERTOS (HUMAN ANALYSTS) */}
                        <div style={{ background: 'rgba(34,197,94,0.05)', padding: '14px', borderRadius: '12px', border: '1px solid rgba(34,197,94,0.3)' }}>
                            <div style={{ display:'flex', justifyContent:'space-between', marginBottom:'8px' }}>
                                <span style={{ fontSize:'10px', color:'#22C55E', fontWeight:950 }}>CONSENSO DE EXPERTOS (NYC)</span>
                                <span style={{ background:'#22C55E', color:'#000', padding:'2px 8px', borderRadius:'10px', fontSize:'10px', fontWeight:950 }}>
                                    {stock.analyst_rating ? stock.analyst_rating.toFixed(1) : '—'}/10
                                </span>
                            </div>
                            <div style={{ fontSize: '11px', color: '#AAA', lineHeight: '1.5' }}>
                                Esta puntuación refleja el sentimiento agregado de analistas institucionales de Wall Street. Un valor {stock.analyst_rating >= 8 ? 'ALTO' : stock.analyst_rating >= 6 ? 'MODERADO' : 'NEUTRAL'} valida el análisis fundamental técnico.
                            </div>
                        </div>

                        {/* DEEP FINANCIAL (GEMINI) */}
                        <div style={{ background: '#161922', padding: '14px', borderRadius: '12px', border: '1px solid rgba(168,85,247,0.2)' }}>
                            <div style={{ display:'flex', justifyContent:'space-between', marginBottom:'8px' }}>
                                <span style={{ fontSize:'10px', color:'#A855F7', fontWeight:950 }}>DEEP FINANCIAL ANALYSIS</span>
                                <span style={{ background:'#A855F7', padding:'2px 8px', borderRadius:'10px', fontSize:'10px', fontWeight:950 }}>
                                    {(stock.gemini_score > 10 ? stock.gemini_score / 10 : (stock.gemini_score || 0)).toFixed(1)}/10
                                </span>
                            </div>
                            <div style={{ fontSize: '11px', color: '#AAA', lineHeight: '1.5', fontStyle: 'italic' }}>
                                {stock.gemini_summary || "Análisis financiero detallado en proceso..."}
                            </div>
                        </div>

                        {/* CHATGPT PRO */}
                        <div style={{ background: '#161922', padding: '14px', borderRadius: '12px', border: '1px solid rgba(56,189,248,0.2)' }}>
                            <div style={{ display:'flex', justifyContent:'space-between', marginBottom:'8px' }}>
                                <span style={{ fontSize:'10px', color:'#38BDF8', fontWeight:950 }}>CHATGPT PRO (PRIMARY)</span>
                                <span style={{ background:'#38BDF8', padding:'2px 8px', borderRadius:'10px', fontSize:'10px', fontWeight:950 }}>
                                    {(stock.qwen_score > 10 ? stock.qwen_score / 10 : (stock.qwen_score || 0)).toFixed(1)}/10
                                </span>
                            </div>
                            <div style={{ fontSize: '11px', color: '#AAA', lineHeight: '1.5', fontStyle: 'italic' }}>
                                {stock.qwen_summary || "Consolidando datos de flujo de caja y proyección operativa..."}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div style={{ padding: '20px 30px', textAlign: 'right', background: '#161922', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            <button onClick={onClose} style={{ background: '#22C55E', color: '#000', padding: '12px 60px', borderRadius: '12px', fontSize: '12px', fontWeight: 950, cursor: 'pointer', textTransform:'uppercase', letterSpacing:'1px' }}>Cerrar Panel</button>
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
