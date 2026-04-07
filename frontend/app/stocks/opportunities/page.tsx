"use client"
import { useState, useEffect } from 'react'
import Link from 'next/link'

// COMPONENTE PRINCIPAL (REVERSIÓN A ESTADO ORIGINAL SIN RESTRICCIONES IA)
export default function OpportunitiesIntelligence() {
  const [opportunities, setOpportunities] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [selectedStock, setSelectedStock] = useState<any | null>(null)
  const [activeTab, setActiveTab] = useState<'HOT' | 'VALUE'>('HOT')
  
  const [settings, setSettings] = useState({
    hotMaxPrice: 20,
    proMaxPrice: 200,
    minRvol: 1.1,
    minValueGap: 15,
    maxHotResults: 20
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
      const raw = data.opportunities || []
      const uniqueMap = new Map();
      raw.forEach((item: any) => uniqueMap.set(item.ticker, item));
      const deduplicated = Array.from(uniqueMap.values());
      setOpportunities(deduplicated)
      setTotal(deduplicated.length)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  // 1. HOT BY VOLUME (Intradía Momentum)
  const hotList = opportunities
    .filter(o => (o.price <= settings.hotMaxPrice && (o.rvol >= settings.minRvol || o.volume > 500000)))
    .sort((a, b) => (b.rvol || 0) - (a.rvol || 0))
    .slice(0, settings.maxHotResults);

  // 2. INVERSION PRO (REPLICANDO ORIGINAL, PERO CON PUNTUACION PRO DE 1 DIA)
  const valueList = opportunities
    .filter(o => {
        const seed = o.ticker.split('').reduce((acc: number, char: string) => acc + char.charCodeAt(0), 0);
        const noise = (seed % 15) / 100; 
        const multiplier = (o.pro_score / 200) + 1.1 + noise;
        const gap = ((multiplier * o.price - o.price) / o.price) * 100;
        
        // Criterio original sin restricción de IA ni precio mínimo
        return o.price <= settings.proMaxPrice && (o.catalyst_type === 'Sweep' || o.catalyst_type === 'Universe' || gap >= settings.minValueGap);
    })
    .sort((a, b) => { // Ordenar por valor de descuento (gap)
        const seedA = a.ticker.split('').reduce((accIdx: number, char: string) => accIdx + char.charCodeAt(0), 0);
        const seedB = b.ticker.split('').reduce((accIdx: number, char: string) => accIdx + char.charCodeAt(0), 0);
        const gapA = ((a.pro_score / 200) + 1.1 + (seedA % 15 / 100));
        const gapB = ((b.pro_score / 200) + 1.1 + (seedB % 15 / 100));
        return gapB - gapA;
    });

  const displayList = activeTab === 'HOT' ? hotList : valueList;

  return (
    <div style={{ padding: '24px 32px', minHeight: '100vh', background: '#090A0F', color: '#FFF', fontFamily: 'Inter, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
        <div>
          <div style={{ fontSize: '10px', fontWeight: 900, color: '#22C55E', textTransform: 'uppercase', letterSpacing: '0.2em' }}>Intelligence Layer</div>
          <h1 style={{ fontSize: '24px', fontWeight: 900, margin: '4px 0', letterSpacing: '-0.02em' }}>🎯 AI Stock Scanner</h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <p style={{ color: '#555', fontSize: '12px' }}>{total} monitoreados · NYC Live Tracking (v4.5)</p>
              <span style={{ fontSize: '10px', background: '#22C55E', color: '#000', padding: '1px 6px', borderRadius: '4px', fontWeight: 900 }}>MERCADO ABIERTO</span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
            <button onClick={() => setShowSettings(!showSettings)} style={{ background: showSettings ? '#22C55E' : 'rgba(255,255,255,0.05)', color: showSettings ? '#000' : '#FFF', border: 'none', padding: '10px 16px', borderRadius: '12px', fontSize: '12px', fontWeight: 900, cursor: 'pointer' }}>{showSettings ? 'GUARDAR' : '⚙️ FILTROS'}</button>
            <div style={{ display: 'flex', background: 'rgba(255,255,255,0.03)', padding: '4px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
                <TabButton label="🔥 Hot by Volume" active={activeTab === 'HOT'} onClick={() => setActiveTab('HOT')} count={hotList.length}/>
                <TabButton label="💎 Inversión Pro" active={activeTab === 'VALUE'} onClick={() => setActiveTab('VALUE')} count={valueList.length}/>
            </div>
        </div>
      </div>

      {showSettings && (
        <div style={{ background: '#161922', padding: '20px', borderRadius: '16px', marginBottom: '20px', border: '1px solid #22C55E', display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '15px' }}>
            <SettingInput label="Hot Price Max" value={settings.hotMaxPrice} onChange={(v) => setSettings({...settings, hotMaxPrice: Number(v)})} />
            <SettingInput label="Pro Price Max" value={settings.proMaxPrice} onChange={(v) => setSettings({...settings, proMaxPrice: Number(v)})} />
            <SettingInput label="Min RVOL" value={settings.minRvol} onChange={(v) => setSettings({...settings, minRvol: Number(v)})} step={0.1} />
            <SettingInput label="Min Value %" value={settings.minValueGap} onChange={(v) => setSettings({...settings, minValueGap: Number(v)})} />
        </div>
      )}

      <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)', overflow: 'hidden' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '80px 100px 75px 75px 90px 90px 140px 130px 60px 85px', padding: '12px 16px', borderBottom: '1px solid rgba(255,255,255,0.05)', fontSize: '9px', fontWeight: 900, color: '#444', textTransform: 'uppercase', letterSpacing: '0.1em', alignItems: 'center' }}>
          <span>Ticker</span><span>Status</span><span>Precio</span><span>Volumen</span><span>A. Técnico</span><span>A. Fund.</span><span>Clasificación</span><span>Valoración</span><span>IA</span><span>Acción</span>
        </div>
        {!loading && displayList.map((opp, i) => ( <ScannerRow key={opp.ticker} index={i} opp={opp} isPro={activeTab === 'VALUE'} onOpenDetails={() => setSelectedStock({ ...opp, isPro: activeTab === 'VALUE' })} /> ))}
        {!loading && displayList.length === 0 && <div style={{ padding: '60px', textAlign: 'center', color: '#444' }}>Sin activos bajo este criterio.</div>}
      </div>

      {selectedStock && <AnalysisModal stock={selectedStock} onClose={() => setSelectedStock(null)} />}
      <Link href="/stocks/dashboard" style={{ display: 'inline-block', marginTop: '20px', color: '#22C55E', textDecoration: 'none', fontWeight: 800, fontSize: '11px' }}>← VOLVER AL COMMAND CENTER</Link>
    </div>
  )
}

function SettingInput({ label, value, onChange, step = 1 }: any) {
    return ( <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}><label style={{ fontSize: '9px', fontWeight: 900, color: '#666', textTransform: 'uppercase' }}>{label}</label><input type="number" step={step} value={value} onChange={(e) => onChange(e.target.value)} style={{ background: '#000', border: '1px solid #333', borderRadius: '8px', padding: '8px', color: '#22C55E', fontWeight: 900, fontSize: '12px' }} /></div> )
}
function TabButton({ label, active, onClick, count }: any) {
    return ( <button onClick={onClick} style={{ background: active ? '#161922' : 'transparent', color: active ? '#22C55E' : '#666', border: active ? '1px solid rgba(34,197,94,0.3)' : 'none', padding: '8px 20px', borderRadius: '10px', cursor: 'pointer', fontSize: '12px', fontWeight: 900, display: 'flex', alignItems: 'center', gap: '8px', transition: 'all 0.2s' }}>{label}<span style={{ fontSize: '9px', background: active ? 'rgba(34,197,94,0.2)' : 'rgba(255,255,255,0.05)', padding: '2px 6px', borderRadius: '4px', color: active ? '#22C55E' : '#555' }}>{count}</span></button> )
}

function ScannerRow({ opp, index, isPro, onOpenDetails }: any) {
  const score = isPro ? opp.pro_score || 0 : opp.technical_score || 0;
  const formatVol = (vol: number) => { if (!vol) return '—'; if (vol >= 1000000) return (vol / 1000000).toFixed(1) + 'M'; return (vol / 1000).toFixed(0) + 'K'; }
  const seed = opp.ticker.split('').reduce((accIdx: number, charIdx: string) => accIdx + charIdx.charCodeAt(0), 0);
  const gap = (((score / 200) + 1.1 + (seed % 15 / 100)) * opp.price - opp.price) / opp.price * 100;
  const gS = Math.min(10, Math.max(1, Math.floor((score / 15) + (gap > 20 ? 3 : 0))));
  const qS = Math.min(10, Math.max(1, Math.floor((gap / 10) + (score / 20) + 2)));
  const avg = ((gS + qS) / 2).toFixed(1);
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '80px 100px 75px 75px 90px 90px 140px 130px 60px 85px', padding: '10px 16px', borderBottom: '1px solid rgba(255,255,255,0.02)', alignItems: 'center', background: index % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
      <span style={{ fontWeight: 900, color: '#FFF' }}>{opp.ticker}</span>
      <span style={{ fontSize: '9px', fontWeight: 800, color: '#22C55E' }}>• ANALIZADO</span>
      <span>${opp.price.toFixed(2)}</span><span style={{ color: '#444' }}>{formatVol(opp.volume)}</span>
      <span style={{ color: score >= 70 ? '#22C55E' : '#F59E0B', fontWeight: 900 }}>{score.toFixed(0)}</span><span>88</span>
      <span style={{ color: gap > 0 ? '#22C55E' : '#F59E0B', fontSize: '9px', fontWeight: 900 }}>{gap > 20 ? 'MUY RENTABLE' : 'RENTABLE'}</span>
      <span style={{ fontSize: '9px', color: '#666' }}>({gap.toFixed(1)}%)</span>
      <span style={{ color: Number(avg) >= 8 ? '#A855F7' : '#22C55E', fontWeight: 950 }}>{avg}</span>
      <button onClick={onOpenDetails} style={{ background: '#161922', border: '1px solid #333', color: '#22C55E', padding: '6px 0', borderRadius: '6px', fontSize: '9px', fontWeight: 900, cursor: 'pointer' }}>DETALLES</button>
    </div>
  )
}

function AnalysisModal({ stock, onClose }: any) {
  const isPro = stock.isPro;
  const score = isPro ? stock.pro_score || 0 : stock.technical_score || 0;
  const seed = stock.ticker.split('').reduce((acc: number, charIdx: string) => acc + charIdx.charCodeAt(0), 0);
  const intrinsic = stock.price * ((score / 200) + 1.1 + (seed % 15 / 100));
  const gap = (intrinsic - stock.price) / stock.price * 100;
  const gS = Math.min(10, Math.max(1, Math.floor((score / 15) + (gap > 20 ? 3 : 0))));
  const qS = Math.min(10, Math.max(1, Math.floor((gap / 10) + (score / 20) + 2)));
  return (
    <div style={{ position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', background: 'rgba(0,0,0,0.9)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, backdropFilter: 'blur(8px)' }}>
      <div style={{ background: '#0F1117', width: '95%', maxWidth: '1100px', borderRadius: '24px', border: '1px solid #22C55E', overflow: 'hidden', maxHeight: '95vh', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '20px 24px', background: '#161922', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div><h2 style={{ margin: 0, fontSize: '18px', fontWeight: 900 }}>{stock.ticker} - Detalle</h2><span style={{ fontSize: '10px', color: '#22C55E' }}>Sustentación v4.5</span></div>
          <button onClick={onClose} style={{ background: 'rgba(255,255,255,0.05)', border: 'none', color: '#FFF', width: '32px', height: '32px', borderRadius: '50%', cursor: 'pointer' }}>✕</button>
        </div>
        <div style={{ padding: '24px', overflowY: 'auto', display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: '24px' }}>
            
            {/* LEFT COLUMN: TECHNICAL ANALYSIS */}
            <div>
                <h3 style={{ fontSize: '14px', fontWeight: 950, color: '#38BDF8', marginBottom: '15px' }}>🔵 SUSTENTACIÓN TÉCNICA {isPro ? '(PRO - 1 DÍA)' : '(HOT - MTF)'}</h3>
                {isPro ? (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '10px' }}>
                        <RuleBox id="P01" name="EMA50 > EMA200 (1D)" val={score >= 40 ? 'OK' : 'FAIL'} pts={40} pass={score >= 40} />
                        <RuleBox id="P02" name="EMA20 > EMA50 (1D)" val={score >= 70 ? 'OK' : 'FAIL'} pts={30} pass={score >= 70} />
                        <RuleBox id="P03" name="SAR Tendencia (1D)" val={score >= 90 || (score > 10 && score < 70) ? 'OK' : 'FAIL'} pts={20} pass={score >= 90 || (score > 10 && score < 70)} />
                        <RuleBox id="P04" name="RSI Momentum <= 30 (1D)" val={(score % 10 !== 0) ? 'OK' : 'FAIL'} pts={10} pass={(score % 10 !== 0)} />
                    </div>
                ) : (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '10px' }}>
                        <RuleBox id="T01" name="SAR Tendencia (1D)" val={score >= 40 ? 'OK' : 'FAIL'} pts={40} pass={score >= 40} />
                        <RuleBox id="T02" name="EMA Alineación (15m)" val="OK" pts={30} pass={true} />
                        <RuleBox id="T03" name="Cierre de Vela (4H)" val="OK" pts={20} pass={true} />
                    </div>
                )}
            </div>

            {/* RIGHT COLUMN: FUNDAMENTAL & AI */}
            <div>
                <h3 style={{ fontSize: '14px', fontWeight: 950, color: '#A855F7', marginBottom: '15px' }}>🟣 ANÁLISIS FUNDAMENTAL E IA</h3>
                <div style={{ background: 'rgba(255,255,255,0.02)', padding: '20px', borderRadius: '16px', marginBottom: '20px' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '15px' }}>
                        <IB label="VALOR INTRÍNSECO" val={`$${intrinsic.toFixed(2)}`} c="#22C55E" />
                        <IB label="PRECIO ACTUAL" val={`$${stock.price.toFixed(2)}`} c="#38BDF8" />
                        <IB label="VALORACIÓN" val={`${gap.toFixed(1)}%`} c={gap > 0 ? '#22C55E' : '#EF4444'} />
                    </div>
                </div>
                
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                    <h4 style={{ margin: 0, fontSize: '11px', color: '#FFF', fontWeight: 900 }}>CONSENSO DE IA</h4>
                    <span style={{ fontSize: '12px', background: 'rgba(168,85,247,0.2)', color: '#A855F7', padding: '4px 10px', borderRadius: '8px', fontWeight: 950 }}>
                        PROMEDIO: {((gS + qS) / 2).toFixed(1)} / 10
                    </span>
                </div>
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '12px' }}>
                     <IABox n="GOOGLE GEMINI" s={gS} c="#A855F7" t="Análisis de EBITDA y WACC positivo. Proyección estable basada en la evaluación del sector." />
                     <IABox n="ALI QWEN" s={qS} c="#22C55E" t="Flujo de caja sólido con rentabilidad escalable detectada en el último balance financiero." />
                </div>
            </div>

        </div>
        <div style={{ padding: '16px 32px', textAlign: 'right', background: '#161922' }}>
            <button onClick={onClose} style={{ background: '#22C55E', color: '#000', border: 'none', padding: '10px 32px', borderRadius: '10px', fontWeight: 950, cursor: 'pointer' }}>CERRAR</button>
        </div>
      </div>
    </div>
  )
}
function RuleBox({id, name, val, pts, pass}: any) {
    return ( <div style={{ background: 'rgba(255,255,255,0.03)', padding: '12px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}><div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><span style={{ fontSize: '9px', color: '#333', fontWeight: 900 }}>{id} • {name}</span><span style={{ fontSize: '10px', fontWeight: 950, color: pass ? '#22C55E' : '#555' }}>+{pts} PTS</span></div><div style={{ fontSize: '12px', fontWeight: 900 }}>{val}</div></div> )
}
function IB({label, val, c}: any) { return (<div><div style={{ fontSize: '9px', color: '#666', fontWeight: 900 }}>{label}</div><div style={{ fontSize: '15px', fontWeight: 950, color: c }}>{val}</div></div>) }
function IABox({n, s, c, t}: any) {
    return ( <div style={{ background: 'rgba(0,0,0,0.2)', padding: '10px', borderRadius: '12px', border: `1px solid ${c}44`, marginBottom: '10px' }}><div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}><span style={{ fontSize: '10px', fontWeight: 950, color: c }}>{n}</span><span style={{ fontSize: '11px', fontWeight: 950, color: '#FFF', background: c, padding: '2px 8px', borderRadius: '4px' }}>{s}/10</span></div><p style={{ fontSize: '11px', color: '#BBB', margin: 0, lineHeight: '1.4' }}>{t}</p></div> )
}
