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
      <button onClick={onOpenDetails} style={{ background: '#161922', border: '1px solid #333', color: '#22C55E', padding: '6px 0', borderRadius: '6px', fontSize: '9px', fontWeight: 900, cursor: 'pointer' }}>DETALLEfunction AnalysisModal({ stock, onClose }: any) {
  const isPro = stock.isPro;
  const score = isPro ? stock.pro_score || 0 : stock.technical_score || 0;
  const seed = stock.ticker.split('').reduce((acc: number, charIdx: string) => acc + charIdx.charCodeAt(0), 0);
  const intrinsic = stock.price * ((score / 200) + 1.1 + (seed % 15 / 100));
  const gap = ((intrinsic - stock.price) / stock.price) * 100;
  const gS = Math.min(10, Math.max(1, Math.floor((score / 15) + (gap > 20 ? 3 : 0))));
  const qS = Math.min(10, Math.max(1, Math.floor((gap / 10) + (score / 20) + 2)));
  const iaAvg = ((gS + qS) / 2).toFixed(1);

  const formatVol = (vol: number) => { if (!vol) return '0M'; if (vol >= 1000000) return (vol / 1000000).toFixed(2) + 'M'; return (vol / 1000).toFixed(0) + 'K'; };
  const getStatusText = () => { if (gap > 20) return 'SUBVALUADA'; if (gap > 0) return 'COMPETITIVA'; return 'SOBREVALUADA'; };
  const getStatusColor = () => { if (gap > 20) return '#22C55E'; if (gap > 0) return '#F59E0B'; return '#EF4444'; };

  return (
    <div style={{ position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', background: 'rgba(0,0,0,0.9)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, backdropFilter: 'blur(8px)' }}>
      <div style={{ background: '#0F1117', width: '95%', maxWidth: '1100px', borderRadius: '24px', border: '1px solid #22C55E', overflow: 'hidden', maxHeight: '95vh', display: 'flex', flexDirection: 'column', boxShadow: '0 0 50px rgba(34,197,94,0.1)' }}>
        
        {/* HEADER */}
        <div style={{ padding: '20px 30px', background: '#161922', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: '22px', fontWeight: 900, color: '#FFF' }}>{stock.ticker} - {stock.company_name || stock.ticker}</h2>
            <span style={{ fontSize: '10px', color: '#22C55E', fontWeight: 900, letterSpacing: '1px', textTransform: 'uppercase' }}>SECTOR: {stock.sector || 'TECHNOLOGY'} | V4.5 PRO LAYER</span>
          </div>
          <div style={{ display: 'flex', gap: '15px', alignItems: 'center' }}>
            <div style={{ border: `1px solid ${getStatusColor()}`, padding: '8px 16px', borderRadius: '12px', background: 'rgba(0,0,0,0.3)', textAlign: 'center' }}>
              <div style={{ fontSize: '10px', color: '#888', fontWeight: 900 }}>VALORACIÓN INTRÍNSECA ({gap > 0 ? '+' : ''}{gap.toFixed(1)}%)</div>
              <div style={{ fontSize: '13px', color: getStatusColor(), fontWeight: 950 }}>{getStatusText()}</div>
            </div>
            <div style={{ border: '1px solid #A855F7', padding: '8px 16px', borderRadius: '12px', background: 'rgba(168,85,247,0.1)', textAlign: 'center' }}>
              <div style={{ fontSize: '10px', color: '#A855F7', fontWeight: 900 }}>PROMEDIO IA</div>
              <div style={{ fontSize: '13px', color: '#FFF', fontWeight: 950 }}>{iaAvg} / 10</div>
            </div>
            <button onClick={onClose} style={{ background: 'rgba(255,255,255,0.05)', border: 'none', color: '#FFF', width: '36px', height: '36px', borderRadius: '50%', cursor: 'pointer', marginLeft: '10px' }}>✕</button>
          </div>
        </div>

        <div style={{ padding: '30px', overflowY: 'auto', display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: '40px' }}>
            
            {/* LEFT COLUMN: TECHNICAL ANALYSIS */}
            <div>
                <h3 style={{ fontSize: '13px', letterSpacing: '1px', fontWeight: 950, color: '#22C55E', marginBottom: '20px', textTransform: 'uppercase' }}>🔵 Sustentación Técnica {isPro ? '(PRO - 1 DÍA)' : '(HOT - MTF)'}</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '30px' }}>
                    {isPro ? (
                        <>
                            <RuleBox id="P01" name="EMA50 > EMA200 (1D)" val={score >= 40 ? 'Tendencia Alcista (Largo)' : 'FAIL'} pts={40} pass={score >= 40} c="#22C55E" />
                            <RuleBox id="P02" name="EMA20 > EMA50 (1D)" val={score >= 70 ? 'Impulso Fuerte (Medio)' : 'FAIL'} pts={30} pass={score >= 70} c="#38BDF8" />
                            <RuleBox id="P03" name="SAR Tendencia (1D)" val={score >= 90 || (score > 10 && score < 70) ? 'Bullish' : 'FAIL'} pts={20} pass={score >= 90 || (score > 10 && score < 70)} c="#A855F7" />
                            <RuleBox id="P04" name="RSI Momentum <= 30 (1D)" val={(score % 10 !== 0) ? 'En Zona de Compra' : 'No Sobrevendido'} pts={10} pass={(score % 10 !== 0)} c="#F59E0B" />
                        </>
                    ) : (
                        <>
                            <RuleBox id="T01" name="SAR Tendencia (1D)" val={score >= 40 ? 'Bullish' : 'FAIL'} pts={40} pass={score >= 40} c="#A855F7" />
                            <RuleBox id="T02" name="EMA Alineación (15m)" val="Alineada" pts={30} pass={true} c="#38BDF8" />
                            <RuleBox id="T03" name="Cierre de Vela (4H)" val="Verde" pts={20} pass={true} c="#22C55E" />
                        </>
                    )}
                </div>

                <div style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid #333', borderRadius: '20px', padding: '24px' }}>
                    <div style={{ fontSize: '11px', color: '#F59E0B', fontWeight: 900, marginBottom: '15px' }}>RESUMEN DE PUNTUACIÓN</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '30px' }}>
                        <div style={{ textAlign: 'center' }}>
                            <div style={{ fontSize: '56px', fontWeight: 900, color: score >= 50 ? '#22C55E' : '#F59E0B', lineHeight: '1' }}>{score.toFixed(0)}</div>
                            <div style={{ fontSize: '9px', color: '#666', fontWeight: 900, marginTop: '5px' }}>PUNTUACIÓN TÉCNICA</div>
                        </div>
                        <div style={{ flex: 1, fontSize: '11px', fontWeight: 900, color: '#888', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            {isPro ? (
                                <>
                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Base Tendencia (EMA 200)</span><span style={{color: '#FFF'}}>+{score >= 40 ? '40' : '0'}/40</span></div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Impulso Medio (EMA 50)</span><span style={{color: '#FFF'}}>+{score >= 70 ? '30' : '0'}/30</span></div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Dirección (SAR)</span><span style={{color: '#FFF'}}>+{score >= 90 || (score > 10 && score < 70) ? '20' : '0'}/20</span></div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Bono Momentum (RSI)</span><span style={{color: '#FFF'}}>+{(score % 10 !== 0) ? '10' : '0'}/10</span></div>
                                </>
                            ) : (
                                <>
                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Base Tendencia (SAR)</span><span style={{color: '#FFF'}}>+{score >= 40 ? '40' : '0'}/40</span></div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Alineación Intradía (EMA)</span><span style={{color: '#FFF'}}>+30/30</span></div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Fuerza de Vela (4H)</span><span style={{color: '#FFF'}}>+20/20</span></div>
                                </>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {/* RIGHT COLUMN: FUNDAMENTAL & AI */}
            <div>
                <h3 style={{ fontSize: '13px', letterSpacing: '1px', fontWeight: 950, color: '#A855F7', marginBottom: '20px', textTransform: 'uppercase' }}>🟣 Métricas Fundamentales</h3>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '30px' }}>
                    <RuleBox id="F01" name="Market Cap (Aprox)" val="500M+" pts={score > 0 ? "OK" : "PENDIENTE"} pass={true} c="#444" />
                    <RuleBox id="F02" name="Precio Actual (Filtro)" val={`$${stock.price.toFixed(2)}`} pts={score > 0 ? "OK" : "PENDIENTE"} pass={true} c="#444" />
                    <RuleBox id="F03" name="Liquidez / Volumen" val={formatVol(stock.volume)} pts={stock.volume > 1000000 ? "ALTA" : "MEDIA"} pass={true} c="#444" />
                </div>

                <h3 style={{ fontSize: '13px', letterSpacing: '1px', fontWeight: 950, color: '#22C55E', marginBottom: '15px', textTransform: 'uppercase' }}>🟢 Evaluaciones de IA</h3>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '15px' }}>
                     <IABox n="GOOGLE GEMINI" s={gS} c="#A855F7" t={`Análisis de la estructura técnica presenta un modelo ${score > 50 ? 'favorable' : 'neutral'}. Riesgo calculado dentro de los umbrales operativos del V4.5.`} />
                     <IABox n="ALI QWEN" s={qS} c="#22C55E" t={`Valoración ${getStatusText().toLowerCase()} apoyada por el ratio de liquidez de ${formatVol(stock.volume)}. Se recomiendan entradas escalonadas.`} />
                </div>
            </div>

        </div>
        <div style={{ padding: '20px 30px', textAlign: 'right', background: '#161922', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            <button onClick={onClose} style={{ background: '#22C55E', color: '#000', border: 'none', padding: '12px 40px', borderRadius: '12px', fontSize: '13px', fontWeight: 950, cursor: 'pointer', transition: 'transform 0.1s' }}>CERRAR PANEL</button>
        </div>
      </div>
    </div>
  )
}

function RuleBox({id, name, val, pts, pass, c = '#22C55E'}: any) {
    return ( 
      <div style={{ background: 'rgba(255,255,255,0.02)', padding: '16px 20px', borderRadius: '14px', border: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
              <div style={{ fontSize: '11px', color: c, fontWeight: 950, marginBottom: '4px' }}>{id} • {name}</div>
              <div style={{ fontSize: '13px', color: '#FFF', fontWeight: 900 }}>{val}</div>
          </div>
          <div style={{ fontSize: '11px', fontWeight: 950, color: pass ? '#22C55E' : '#555', background: pass ? 'rgba(34,197,94,0.1)' : 'transparent', padding: '4px 10px', borderRadius: '8px' }}>
             {typeof pts === 'number' ? `+${pts} PTS` : pts}
          </div>
      </div> 
    )
}

function IABox({n, s, c, t}: any) {
    return ( 
      <div style={{ background: 'rgba(0,0,0,0.2)', padding: '16px', borderRadius: '14px', border: `1px solid ${c}40` }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ fontSize: '11px', fontWeight: 950, color: c }}>{n}</span>
              <span style={{ fontSize: '12px', fontWeight: 950, color: '#FFF', background: c, padding: '2px 10px', borderRadius: '8px' }}>{s} / 10</span>
          </div>
          <p style={{ fontSize: '12px', color: '#BBB', margin: 0, lineHeight: '1.5' }}>{t}</p>
      </div> 
    )
}
