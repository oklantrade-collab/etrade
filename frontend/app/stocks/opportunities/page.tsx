"use client"
import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import TradeMarkerChart from '@/components/TradeMarkerChart'
import toast from 'react-hot-toast'

// ════════════════════════════════════════════
// APEX Priority Queue Panel
// ════════════════════════════════════════════

function StatusBadge({ status, isOB }: { status: string, isOB: boolean }) {
  const configs: any = {
    'pending':  { label: 'PENDING',  color: '#F59E0B', bg: 'rgba(245,158,11,0.12)', icon: '⏳' },
    'buying':   { label: 'BUYING',   color: '#38BDF8', bg: 'rgba(56,189,248,0.15)', icon: '⚡' },
    'owned':    { label: 'OWNED',    color: '#22C55E', bg: 'rgba(34,197,94,0.15)',  icon: '💎' },
    'blocked':  { label: 'BLOCKED',  color: '#EF4444', bg: 'rgba(239,68,68,0.15)',  icon: '🚫' },
    'watching': { label: 'WATCHING', color: '#94A3B8', bg: 'rgba(148,163,184,0.1)', icon: '👁️' },
  };
  
  let s = status?.toLowerCase() || 'pending';
  if (isOB) s = 'blocked';
  
  const cfg = configs[s] || configs['pending'];
  
  return (
    <div style={{
      fontSize: '9px', fontWeight: 900,
      padding: '3px 10px', borderRadius: '6px',
      background: cfg.bg, color: cfg.color,
      minWidth: '85px', textAlign: 'center',
      border: `1px solid ${cfg.color}22`,
      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '5px',
      textTransform: 'uppercase', letterSpacing: '0.05em'
    }}>
      <span>{cfg.icon}</span>
      <span>{cfg.label}</span>
    </div>
  );
}

function PriorityQueuePanel({ queue, capital, summary }: { queue: any[], capital: any, summary: any }) {
  const hasQueue = queue && queue.length > 0;

  const capPct = capital?.capital_max_total > 0
    ? Math.round((capital.capital_invested / capital.capital_max_total) * 100)
    : 0;

  return (
    <div style={{
      background: 'linear-gradient(145deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%)',
      border: '1px solid rgba(255,255,255,0.08)',
      borderRadius: '16px', padding: '20px',
      marginBottom: '24px',
      boxShadow: '0 10px 30px rgba(0,0,0,0.2)'
    }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        alignItems: 'center', marginBottom: '18px',
      }}>
        <div style={{ display:'flex', alignItems:'center', gap:'12px' }}>
            <h3 style={{ color: '#FFF', fontSize: '15px', fontWeight: 900, margin: 0, letterSpacing: '-0.5px' }}>
              🎯 COLA DE ALTA PRIORIDAD APEX
            </h3>
            <span style={{ fontSize: '10px', color: '#444', fontWeight: 800 }}>V5.0 ORCHESTRATOR</span>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span style={{
            background: 'rgba(0,200,150,0.1)', color: '#00C896',
            fontSize: '10px', padding: '4px 12px', borderRadius: '20px', fontWeight: 800, border: '1px solid rgba(0,200,150,0.2)'
          }}>
            {summary?.active || 0} ACTIVAS
          </span>
          <span style={{
            background: 'rgba(79,195,247,0.1)', color: '#4FC3F7',
            fontSize: '10px', padding: '4px 12px', borderRadius: '20px', fontWeight: 800, border: '1px solid rgba(79,195,247,0.2)'
          }}>
            {summary?.with_signal || 0} SEÑAL
          </span>
        </div>
      </div>

      {/* Capital Allocation Bar */}
      {capital?.capital_max_total > 0 && (
        <div style={{ marginBottom: '20px', background: 'rgba(0,0,0,0.2)', padding: '12px 16px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.03)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#888', marginBottom: '8px', fontWeight: 700 }}>
            <div style={{ display:'flex', gap:'15px' }}>
                <span>INVESTED: <b style={{ color: '#FFF' }}>${capital.capital_invested?.toLocaleString()}</b></span>
                <span>MAX RISK: <b style={{ color: '#FFF' }}>${capital.capital_max_total?.toLocaleString()}</b></span>
            </div>
            <span style={{ color: '#22C55E' }}>AVAILABLE: <b>${capital.capital_available?.toLocaleString()}</b> ({capital.ops_possible} ops)</span>
          </div>
          <div style={{ height: '6px', background: 'rgba(255,255,255,0.05)', borderRadius: '3px', overflow: 'hidden' }}>
            <div style={{
              width: `${Math.min(100, capPct)}%`, height: '100%',
              background: 'linear-gradient(90deg, #22C55E 0%, #38BDF8 100%)',
              boxShadow: '0 0 10px rgba(34,197,94,0.3)',
              transition: 'width 0.8s cubic-bezier(0.4, 0, 0.2, 1)',
            }} />
          </div>
        </div>
      )}

      {!hasQueue ? (
        <div style={{ textAlign: 'center', padding: '30px', color: '#444', fontSize: '13px', fontWeight: 700, background: 'rgba(0,0,0,0.1)', borderRadius: '12px' }}>
          Esperando que el Orchestrator identifique candidatos de alta prioridad...
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '15px' }}>
            {queue.slice(0, 10).map((item: any, idx: number) => {
              const apex4h = item.apex_score_4h || 0;
              const retExp = item.return_expected || 0;
              const rank = item.composite_rank || 0;
              const isOB = item.is_overbought;
              const status = item.status || 'pending';

              return (
                <div key={item.ticker || idx} style={{
                  display: 'flex', alignItems: 'center', gap: '12px',
                  padding: '12px', borderRadius: '12px',
                  background: 'rgba(255,255,255,0.02)',
                  border: `1px solid ${idx === 0 ? 'rgba(245,158,11,0.2)' : 'rgba(255,255,255,0.04)'}`,
                  transition: 'transform 0.2s',
                }}>
                  <div style={{
                    width: '30px', height: '30px', borderRadius: '8px',
                    background: idx === 0 ? 'rgba(245,158,11,0.1)' : 'rgba(0,0,0,0.3)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: '12px', fontWeight: 900,
                    color: idx === 0 ? '#F59E0B' : '#444',
                  }}>
                    #{idx + 1}
                  </div>

                  <div style={{ minWidth: '60px' }}>
                    <div style={{ fontWeight: 900, fontSize: '15px', color: isOB ? '#EF4444' : '#FFF' }}>{item.ticker}</div>
                    <div style={{ fontSize: '10px', color: '#555', fontWeight: 800 }}>RANK {rank.toFixed(1)}</div>
                  </div>

                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <span style={{ color: '#4FC3F7', fontSize: '11px', fontWeight: 900 }}>{apex4h.toFixed(0)}% APEX</span>
                      <span style={{ color: retExp > 0 ? '#22C55E' : '#EF4444', fontSize: '11px', fontWeight: 800 }}>
                        {retExp > 0 ? '+' : ''}{retExp.toFixed(2)}%
                      </span>
                    </div>
                    <div style={{ height: '4px', background: 'rgba(255,255,255,0.05)', borderRadius: '2px' }}>
                      <div style={{
                        width: `${Math.min(100, apex4h)}%`, height: '100%',
                        background: apex4h >= 75 ? '#22C55E' : apex4h >= 60 ? '#38BDF8' : '#F59E0B',
                        borderRadius: '2px', transition: 'width 1s ease',
                      }} />
                    </div>
                  </div>

                  <StatusBadge status={status} isOB={isOB} />
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
}

const formatAbbreviated = (num: any) => {
    const val = parseFloat(num);
    if (!val || isNaN(val)) return '0.00';
    if (val >= 1_000_000_000) return (val / 1_000_000_000).toFixed(2) + 'B';
    if (val >= 1_000_000) return (val / 1_000_000).toFixed(2) + 'M';
    if (val >= 1_000) return (val / 1_000).toFixed(2) + 'K';
    return val.toFixed(2);
};

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
          "timezone": "America/Lima",
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
            "MASimple@tv-basicstudies"
          ],
          "studies_overrides": {
            "moving average.length": 3,
            "moving average.plot.color": "#E3FF00",
            "moving average.ma.color": "#E3FF00",
            "moving average.linewidth": 2
          },
          "overrides": {
            "mainSeriesProperties.style": 1,
          }
        });
      }
    };
    document.head.appendChild(script);
  }, [symbol, containerId]);

  return (
    <div ref={containerRef} id={containerId} style={{ height: '100%', width: '100%', borderRadius: '16px', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.1)' }} />
  );
}

function ChartModal({ symbol, onClose }: { symbol: string, onClose: () => void }) {
  return (
    <div 
      style={{ 
        position: 'fixed', 
        top: 0, 
        left: 0, 
        width: '100%', 
        height: '100%', 
        background: 'rgba(0,0,0,0.8)', 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center', 
        zIndex: 1100, 
        backdropFilter: 'blur(5px)' 
      }}
    >
        <div style={{ background: '#0F1117', width: '95%', height: '92%', borderRadius: '24px', border: '1px solid #38BDF8', overflow: 'hidden', display: 'flex', flexDirection: 'column', boxShadow: '0 0 50px rgba(56,189,248,0.2)' }}>
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

function PiotroskiBox({ label, pass }: { label: string, pass: boolean }) {
    return (
        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '10px', borderRadius: '10px', border: pass ? '1px solid rgba(34,197,94,0.3)' : '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '12px' }}>{pass ? '✅' : '❌'}</span>
            <span style={{ fontSize: '10px', fontWeight: 700, color: pass ? '#FFF' : '#444' }}>{label}</span>
        </div>
    )
}

function AnalysisModal({ stock, onClose }: any) {
  const [showChart, setShowChart] = useState(false);

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
    <div 
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        background: 'rgba(0,0,0,0.95)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        backdropFilter: 'blur(10px)'
      }}
    >
      <div style={{ background: '#0F1117', width: '95%', maxWidth: '1150px', borderRadius: '24px', border: '1px solid #22C55E', overflow: 'hidden', maxHeight: '95vh', display: 'flex', flexDirection: 'column', boxShadow: '0 0 50px rgba(34,197,94,0.2)' }}>
        <div style={{ padding: '20px 30px', background: '#161922', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: '22px', fontWeight: 900, color: '#FFF' }}>{stock.ticker} - {stock.company_name || stock.ticker}</h2>
            <div style={{ display:'flex', gap:'10px', marginTop:'4px' }}>
                <span style={{ fontSize: '10px', color: '#22C55E', fontWeight: 900, textTransform: 'uppercase' }}>SECTOR: {stock.sector || 'TECHNOLOGY'} | V4.5 PRO LAYER</span>
                <span style={{ fontSize: '10px', color: '#AAA', fontWeight: 700 }}>FUENTE: {stock.data_source?.toUpperCase()}</span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '15px', alignItems:'center' }}>
            <button 
                onClick={() => setShowChart(!showChart)}
                style={{ background: showChart ? '#FF4757' : '#38BDF8', color: '#000', border: 'none', padding: '10px 20px', borderRadius: '12px', fontSize: '11px', fontWeight: 950, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px' }}
            >
                <span>{showChart ? 'CERRAR GRÁFICO' : 'VER GRÁFICO'}</span>
                <span style={{ fontSize: '14px' }}>📊</span>
            </button>
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

        {showChart && <ChartModal symbol={stock.ticker} onClose={() => setShowChart(false)} />}

        <div style={{ flex: 1, padding: '25px 30px', overflowY: 'auto', display: 'grid', gridTemplateColumns: '380px 1fr', gap: '30px', minHeight: '300px' }}>
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
                        <div style={{ background: 'rgba(34,197,94,0.05)', padding: '20px', borderRadius: '16px', border: '1px solid rgba(34,197,94,0.3)' }}>
                            <div style={{ display:'flex', justifyContent:'space-between', marginBottom:'15px' }}>
                                <div style={{ display:'flex', alignItems:'center', gap:'8px' }}>
                                    <span style={{ fontSize:'11px', color:'#22C55E', fontWeight:950, letterSpacing:'1px' }}>CONSENSO DE EXPERTOS (NYC) - CAPA 4</span>
                                    <span style={{ fontSize:'10px', color:'#666', fontWeight:700 }}>• WALL STREET INSIGHTS</span>
                                </div>
                                <span style={{ background:'#22C55E', color:'#000', padding:'2px 10px', borderRadius:'10px', fontSize:'11px', fontWeight:950 }}>{stock.analyst_rating ? stock.analyst_rating.toFixed(1) : iaAvg} / 10</span>
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px' }}>
                                    <div>
                                        <div style={{ fontSize:'9px', color:'#A855F7', fontWeight:950, textTransform:'uppercase', marginBottom:'8px' }}>NIVELES OPERATIVOS (ESTRATEGIA 3-BLOQUES)</div>
                                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                                            <div style={{ background: 'rgba(34,197,94,0.1)', padding: '10px', borderRadius: '10px', border: '1px solid rgba(34,197,94,0.2)' }}>
                                                <div style={{ fontSize: '8px', color: '#22C55E', fontWeight: 900 }}>ENTRADA</div>
                                                <div style={{ fontSize: '13px', color: '#FFF', fontWeight: 950 }}>${(stock.entry_price || 0).toFixed(2)}</div>
                                            </div>
                                            <div style={{ background: 'rgba(239,68,68,0.1)', padding: '10px', borderRadius: '10px', border: '1px solid rgba(239,68,68,0.2)' }}>
                                                <div style={{ fontSize: '8px', color: '#EF4444', fontWeight: 900 }}>STOP LOSS</div>
                                                <div style={{ fontSize: '13px', color: '#FFF', fontWeight: 950 }}>${(stock.stop_loss || 0).toFixed(2)}</div>
                                            </div>
                                            <div style={{ background: 'rgba(255,215,0,0.1)', padding: '8px', borderRadius: '8px' }}>
                                                <div style={{ fontSize: '7px', color: '#FFD700', fontWeight: 900 }}>TP1 (50%)</div>
                                                <div style={{ fontSize: '12px', color: '#FFF', fontWeight: 900 }}>${(stock.tp_block1_price || stock.target_1 || 0).toFixed(2)}</div>
                                            </div>
                                            <div style={{ background: 'rgba(255,255,255,0.05)', padding: '8px', borderRadius: '8px' }}>
                                                <div style={{ fontSize: '7px', color: '#AAA', fontWeight: 900 }}>TP2 (25%)</div>
                                                <div style={{ fontSize: '12px', color: '#FFF', fontWeight: 900 }}>${(stock.tp_block2_price || 0).toFixed(2)}</div>
                                            </div>
                                            <div style={{ background: 'rgba(56,189,248,0.1)', padding: '8px', borderRadius: '8px', border: '1px solid rgba(56,189,248,0.2)', gridColumn: 'span 2' }}>
                                                <div style={{ fontSize: '7px', color: '#38BDF8', fontWeight: 900 }}>TP3 TRAILING (25%)</div>
                                                <div style={{ fontSize: '12px', color: '#FFF', fontWeight: 900 }}>${(stock.tp_block3_price || 0).toFixed(2)}</div>
                                            </div>
                                        </div>
                                    </div>
                                    <div>
                                        <div style={{ fontSize:'9px', color:'#666', fontWeight:800, textTransform:'uppercase', marginBottom:'4px' }}>ESTRUCTURA DE MERCADO (C1 & C2)</div>
                                        <div style={{ fontSize:'11px', color:'#DDD', display:'flex', flexDirection:'column', gap:'4px' }}>
                                            <div title="Market Capitalization">
                                                • <span style={{ borderBottom:'1px dashed #444', cursor:'help' }}>MCap</span>: <span style={{ color:'#FFF', fontWeight:700 }}>${formatAbbreviated(stock.market_cap)}</span>
                                            </div>
                                            <div title="Technical Rules">
                                                • <span style={{ borderBottom:'1px dashed #444', cursor:'help' }}>Reglas (T)</span>: 
                                                <span style={{ color: stock.t01_confirmed ? '#22C55E' : '#FF4757', marginLeft:'5px' }}>T1:{stock.t01_confirmed ? 'OK':'F'}</span>
                                                <span style={{ color: stock.t02_confirmed ? '#22C55E' : '#FF4757', marginLeft:'8px' }}>T2:{stock.t02_confirmed ? 'OK':'F'}</span>
                                                <span style={{ color: stock.t03_confirmed ? '#22C55E' : '#FF4757', marginLeft:'8px' }}>T3:{stock.t03_confirmed ? 'OK':'F'}</span>
                                            </div>
                                        </div>
                                    </div>
                            </div>
                            <div style={{ marginTop:'20px', padding:'15px', background:'rgba(255,255,255,0.02)', borderRadius:'12px', border:'1px solid rgba(255,255,255,0.05)' }}>
                                <div style={{ color:'#22C55E', fontWeight:950, fontSize:'10px', marginBottom:'10px', textTransform:'uppercase', letterSpacing:'1px' }}>📋 DIAGNÓSTICO ESTRATÉGICO</div>
                                <div style={{ display:'flex', flexDirection:'column', gap:'8px', fontSize:'11px', color:'#CCC' }}>
                                    <div>
                                        <span style={{ color:'#888', fontWeight:700 }}>• SALUD FINANCIERA:</span> El pilar Piotroski muestra un <span style={{ color: stock.piotroski_score >= 6 ? '#22C55E' : '#FFB74D', fontWeight:900 }}>{stock.piotroski_score}/9</span>.
                                    </div>
                                    <div>
                                        <span style={{ color:'#888', fontWeight:700 }}>• RIESGO DE QUIEBRA:</span> Altman Z-Score de <span style={{ color: stock.altman_z_score > 2.9 ? '#22C55E' : '#FF4757', fontWeight:900 }}>{stock.altman_z_score?.toFixed(2)}</span>.
                                    </div>
                                    <div>
                                        <span style={{ color:'#888', fontWeight:700 }}>• POTENCIAL:</span> Proyección DCF indica un estado de <span style={{ color:'#FFF', fontWeight:900 }}>{stock.valuation_status?.replace('_', ' ').toUpperCase()}</span>.
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <div style={{ padding: '20px 30px', textAlign: 'right', background: '#161922', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            <button onClick={onClose} style={{ background: '#22C55E', color: '#000', padding: '12px 60px', borderRadius: '12px', fontSize: '12px', fontWeight: 950, cursor: 'pointer', textTransform:'uppercase' }}>Cerrar Panel de Análisis</button>
        </div>
      </div>
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

const ApexBadge = ({ score4h, score1d, signal, confidence, edge }: {
  score4h: number | null, score1d: number | null,
  signal: string | null, confidence: string | null, edge: number | null
}) => {
  if (!score4h && score4h !== 0) return <span style={{color:'#333', fontSize:'10px'}}>—</span>

  const signalConfig: Record<string, {color: string, bg: string, label: string}> = {
    STRONG_BUY: { color:'#00C896', bg:'rgba(0,200,150,0.12)', label:'STRONG BUY' },
    STRONG_BUY_BLUE: { color:'#4169E1', bg:'rgba(65,105,225,0.12)', label:'STRONG BUY' },
    BUY:        { color:'#4FC3F7', bg:'rgba(79,195,247,0.12)', label:'BUY' },
    NEUTRAL:    { color:'#FFB74D', bg:'rgba(255,183,77,0.12)', label:'NEUTRAL' },
    CAUTION:    { color:'#FF8A65', bg:'rgba(255,138,101,0.12)', label:'CAUTION' },
    AVOID:      { color:'#FF4757', bg:'rgba(255,71,87,0.12)', label:'AVOID' },
  }
  const cfg = signalConfig[signal || 'NEUTRAL'] || signalConfig.NEUTRAL
  const confIcon: Record<string, string> = { high: '⬆️', medium: '➡️', low: '⬇️' }
  const edgeVal = edge || 0

  return (
    <div style={{
      background: cfg.bg, border: `1px solid ${cfg.color}33`,
      borderRadius: '8px', padding: '5px 8px', minWidth: '100px',
    }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'3px' }}>
        <span style={{ fontSize:'16px', fontWeight:900, color: cfg.color, fontFamily:'monospace' }}>
          {score4h}%
        </span>
        <span style={{ fontSize:'10px', color:'#666' }}>{confIcon[confidence || 'low']}</span>
      </div>
      <div style={{ fontSize:'8px', fontWeight:700, color: cfg.color, letterSpacing:'0.8px', marginBottom:'3px' }}>
        {cfg.label}
      </div>
      <div style={{ display:'flex', justifyContent:'space-between', fontSize:'8px', color:'#666' }}>
        <span>edge</span>
        <span style={{ color: edgeVal > 0 ? '#00C896' : '#FF4757', fontWeight:600 }}>
          {edgeVal > 0 ? '+' : ''}{edgeVal.toFixed(1)}%
        </span>
      </div>
      <div style={{ display:'flex', justifyContent:'space-between', fontSize:'8px', color:'#555', marginTop:'1px' }}>
        <span>1D</span>
        <span>{score1d || 0}%</span>
      </div>
    </div>
  )
}

function ScannerRow({ opp, index, isPro, onOpenDetails, onDelete }: any) {
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
    <div className="scanner-row" style={{ 
      display: 'grid', 
      gridTemplateColumns: '80px 90px 80px 80px 70px 1fr 70px 40px 40px 40px 115px 95px 80px', 
      padding: '12px 16px', 
      borderBottom: '1px solid rgba(255,255,255,0.03)', 
      alignItems: 'center', 
      transition: 'all 0.2s ease',
      background: index % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' 
    }}>
      <div style={{ display:'flex', alignItems:'center', gap: '6px' }}>
          <span style={{ fontWeight: 900, color: '#FFF', fontSize: '14px', letterSpacing: '-0.5px' }}>{opp.ticker}</span>
          {(opp.intrinsic_value > opp.price && opp.intrinsic_value > 0) && (
            <span style={{ fontSize: '8px', background: '#22C55E', color: '#000', padding: '1px 4px', borderRadius: '3px', fontWeight: 950 }}>VAL</span>
          )}
      </div>
      
      <div style={{ display:'flex', alignItems:'center' }}>
          <span style={{ color:(opp.change_pct || 0) >= 0 ? '#22C55E' : '#EF4444', fontWeight:900, fontSize:'13px' }}>
            {opp.change_pct > 0 ? '+' : ''}{(opp.change_pct || 0).toFixed(2)}%
          </span>
      </div>

      <span style={{ fontWeight: 700, fontSize:'13px', color: '#EEE' }}>${opp.price.toFixed(2)}</span>
      
      <span style={{ fontWeight: 800, fontSize:'11px', color: '#888' }}>
        {(opp.volume / 1_000_000).toFixed(2)}M
      </span>

      <PiotroskiBadge score={opp.piotroski_score} detail={opp.piotroski_detail} />

      <span style={{ color: getMovColor(rawMovement), fontSize: '10px', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
        {movementDisplay}
      </span>

      <div style={{ display:'flex', flexDirection:'column', justifyContent: 'center' }}>
        <span style={{ fontSize:'9px', color:'#555', fontWeight:800 }}>{opp.created_at ? new Date(opp.created_at).toLocaleDateString('es-PE', { day: '2-digit', month: '2-digit' }) : '--/--'}</span>
        <span style={{ fontSize:'11px', color:'#22C55E', fontWeight:900, fontFamily:'monospace', marginTop: '1px' }}>{opp.last_scan_time || '—:—'}</span>
      </div>

      <span style={{ color: displayScoreTech >= 70 ? '#22C55E' : '#F59E0B', fontWeight: 950, fontSize:'11px', textAlign: 'center' }}>{displayScoreTech}</span>
      <span style={{ color: Number(scoreIA) >= 7.5 ? '#A855F7' : '#22C55E', fontWeight: 950, fontSize:'11px', textAlign: 'center' }}>{scoreIA}</span>
      <span style={{ color: Number(opp.sm_score) >= 7.5 ? '#FF4757' : (Number(opp.sm_score) >= 5 ? '#F59E0B' : '#666'), fontWeight: 950, fontSize:'11px', textAlign: 'center' }}>{opp.sm_score?.toFixed(1) || '1.0'}</span>
      
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <ApexBadge score4h={opp.apex_4h} score1d={opp.apex_1d} signal={opp.apex_signal} confidence={opp.apex_conf} edge={opp.apex_edge} />
      </div>

      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <StatusBadge status={opp.queue_status} isOB={opp.is_overbought_queue} />
      </div>

      <div style={{textAlign:'right', display: 'flex', justifyContent: 'flex-end', gap: '8px'}}>
        <button onClick={onOpenDetails} title="Analizar Empresa" style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)', color: '#22C55E', width: '32px', height: '32px', borderRadius: '50%', fontSize: '14px', cursor: 'pointer', display: 'inline-flex', justifyContent: 'center', alignItems: 'center', transition: 'all 0.2s' }}>🔍</button>
        {isPro && (
            <button onClick={onDelete} title="Eliminar de PRO" style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#EF4444', width: '32px', height: '32px', borderRadius: '50%', fontSize: '14px', cursor: 'pointer', display: 'inline-flex', justifyContent: 'center', alignItems: 'center', transition: 'all 0.2s' }}>—</button>
        )}
      </div>
    </div>
  )
}

function SettingInput({ label, value, onChange, step = 1 }: any) {
    return ( <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}><label style={{ fontSize: '9px', fontWeight: 900, color: '#666', textTransform: 'uppercase' }}>{label}</label><input type="number" step={step} value={value} onChange={(e) => onChange(e.target.value)} style={{ background: '#000', border: '1px solid #333', borderRadius: '8px', padding: '8px', color: '#22C55E', fontWeight: 900, fontSize: '12px' }} /></div> )
}

function TabButton({ label, active, onClick, count }: any) {
    return ( <button onClick={onClick} style={{ background: active ? '#161922' : 'transparent', color: active ? '#22C55E' : '#666', border: active ? '1px solid rgba(34,197,94,0.3)' : 'none', padding: '8px 20px', borderRadius: '10px', cursor: 'pointer', fontSize: '12px', fontWeight: 900, display: 'flex', alignItems: 'center', gap: '8px' }}>{label}<span style={{ fontSize: '9px', background: active ? 'rgba(34,197,94,0.2)' : 'rgba(255,255,255,0.05)', padding: '2px 6px', borderRadius: '4px', color: active ? '#22C55E' : '#555' }}>{count}</span></button> )
}

export default function OpportunitiesIntelligence() {
  const [opportunities, setOpportunities] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [selectedStock, setSelectedStock] = useState<any | null>(null)
  const [activeTab, setActiveTab] = useState<'HOT' | 'VALUE'>('HOT')
  const [marketStatus, setMarketStatus] = useState({ is_open: false, status: 'CARGANDO...' })
  const [priorityQueue, setPriorityQueue] = useState<any[]>([])
  const [pqCapital, setPqCapital] = useState<any>({})
  const [pqSummary, setPqSummary] = useState<any>({})
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
  const [showAddModal, setShowAddModal] = useState(false);
  const [searchTicker, setSearchTicker] = useState("");
  const [searchResult, setSearchResult] = useState<any>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isAdding, setIsAdding] = useState(false);

  useEffect(() => {
    fetchData()
    fetchPriorityQueue()
    const interval = setInterval(() => { fetchData(); fetchPriorityQueue(); }, 30000)
    return () => clearInterval(interval)
  }, [])

  const fetchPriorityQueue = async () => {
    try {
      const res = await fetch(`/api/v1/stocks/priority-queue?t=${Date.now()}`)
      const data = await res.json()
      setPriorityQueue(data.queue || [])
      setPqCapital(data.capital || {})
      setPqSummary(data.summary || {})
    } catch (err) {
      console.error('PQ fetch error:', err)
    }
  }

  const fetchData = async () => {
    try {
      const res = await fetch(`/api/v1/stocks/opportunities?t=${Date.now()}`)
      const data = await res.json()
      if (data.market_status) setMarketStatus(data.market_status)
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

  const handleSearch = async (e: any) => {
    e.preventDefault();
    if (!searchTicker) return;
    setIsSearching(true);
    setSearchResult(null);
    try {
        const res = await fetch(`/api/v1/stocks/search?q=${searchTicker}`);
        const data = await res.json();
        setSearchResult(data);
    } catch (err) {
        console.error(err);
    } finally {
        setIsSearching(false);
    }
  };

  const handleAddTicker = async () => {
    if (!searchResult?.ticker) return;
    setIsAdding(true);
    try {
        const res = await fetch('/api/v1/stocks/watchlist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticker: searchResult.ticker })
        });
        if (res.ok) {
            setShowAddModal(false);
            setSearchTicker("");
            setSearchResult(null);
            fetchData();
        } else {
            const err = await res.json();
            alert(`Error: ${err.detail}`);
        }
    } catch (err) {
        console.error(err);
    } finally {
        setIsAdding(false);
    }
  };

  const handleDeleteTicker = async (ticker: string) => {
    if (!confirm(`¿Estás seguro de eliminar ${ticker} de la lista PRO?`)) return;
    try {
        const res = await fetch(`/api/v1/stocks/watchlist/${ticker}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.status === 'ok') {
            fetchData();
        } else {
            alert(data.message || "Error al eliminar");
        }
    } catch (err) {
        console.error(err);
    }
  };

  // Merge priority queue items into opportunities so they always appear in the general table
  const mergedOpportunities = (() => {
    const existingTickers = new Set(opportunities.map(o => o.ticker));
    const merged = [...opportunities];
    
    // Add priority queue items that aren't already in the main list
    for (const pq of priorityQueue) {
      if (!existingTickers.has(pq.ticker)) {
        merged.push({
          ticker: pq.ticker,
          price: pq.price_at_rank || 0,
          rvol: 0,
          volume: 0,
          apex_4h: pq.apex_score_4h || 0,
          apex_1d: pq.apex_score_1d || 0,
          apex_signal: '',
          apex_conf: pq.confidence || '',
          queue_status: pq.status || 'watching',
          last_scan_time: '--:--',
          _from_priority_queue: true,
        });
        existingTickers.add(pq.ticker);
      }
    }
    return merged;
  })();

  const hotList = mergedOpportunities
    .filter(o => o._from_priority_queue || (o.price <= settings.hotMaxPrice && o.rvol >= settings.minRvol && o.volume >= settings.minVolume))
    .sort((a, b) => {
      // Sort by APEX Score 4H descending (primary), then by RVOL (secondary)
      const apexA = parseFloat(a.apex_4h) || 0;
      const apexB = parseFloat(b.apex_4h) || 0;
      if (apexB !== apexA) return apexB - apexA;
      return (b.rvol || 0) - (a.rvol || 0);
    })
    .slice(0, settings.maxHotResults);

  const valueList = mergedOpportunities.filter(o => o.is_pro_member);
  const displayList = activeTab === 'HOT' ? hotList : valueList;

  return (
    <div style={{ padding: '24px 32px', minHeight: '100vh', background: '#090A0F', color: '#FFF', fontFamily: 'Inter, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
        <div>
          <div style={{ fontSize: '10px', fontWeight: 900, color: '#22C55E', textTransform: 'uppercase', letterSpacing: '0.2em' }}>Intelligence Layer v4.5 • APEX Score v1.0</div>
          <h1 style={{ fontSize: '24px', fontWeight: 900, margin: '4px 0', letterSpacing: '-0.02em' }}>🎯 AI Stock Scanner</h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <p style={{ color: '#555', fontSize: '12px' }}>{total} monitoreados · NYC Live Tracking</p>
               <span style={{ fontSize: '10px', background: marketStatus.is_open ? '#22C55E' : '#EF4444', color: '#000', padding: '1px 8px', borderRadius: '4px', fontWeight: 950, textTransform: 'uppercase' }}>
                {marketStatus.is_open ? '🟢' : '🔴'} MERCADO {marketStatus.status}
              </span>
              {opportunities.length > 0 && (
                <span style={{ fontSize: '10px', color: '#888', fontWeight: 700 }}>
                  ÚLTIMO PROCESO: <span style={{ color: '#22C55E' }}>{opportunities[0].last_scan_time || 'RECIBIENDO...'}</span>
                </span>
              )}
          </div>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
            <button onClick={() => setShowSettings(!showSettings)} style={{ background: showSettings ? '#22C55E' : 'rgba(255,255,255,0.05)', color: showSettings ? '#000' : '#FFF', border: 'none', padding: '10px 16px', borderRadius: '12px', fontSize: '12px', fontWeight: 900, cursor: 'pointer' }}>⚙️ FILTROS</button>
            <div style={{ display: 'flex', background: 'rgba(255,255,255,0.03)', padding: '4px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)', alignItems: 'center' }}>
                <TabButton label="🔥 Hot by Volume" active={activeTab === 'HOT'} onClick={() => setActiveTab('HOT')} count={hotList.length}/>
                <TabButton label="💎 Inversión Pro" active={activeTab === 'VALUE'} onClick={() => setActiveTab('VALUE')} count={valueList.length}/>
                <button onClick={() => setShowAddModal(true)} style={{ background: '#22C55E', color: '#000', border: 'none', width: '28px', height: '28px', borderRadius: '8px', marginLeft: '8px', cursor: 'pointer', fontWeight: 900, fontSize: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>+</button>
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

      {/* APEX Priority Queue Panel */}
      <PriorityQueuePanel queue={priorityQueue} capital={pqCapital} summary={pqSummary} />

      <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)', overflow: 'hidden' }}>
        <style jsx>{`
          .scanner-row:hover {
            background: rgba(34, 197, 94, 0.05) !important;
            transform: translateX(4px);
          }
        `}</style>
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: '80px 90px 80px 80px 70px 1fr 70px 40px 40px 40px 115px 95px 80px', 
          padding: '14px 16px', 
          borderBottom: '1px solid rgba(255,255,255,0.08)', 
          fontSize: '10px', 
          fontWeight: 900, 
          color: '#555', 
          textTransform: 'uppercase', 
          letterSpacing: '0.15em', 
          alignItems: 'center',
          background: 'rgba(0,0,0,0.2)'
        }}>
          <span>Ticker</span>
          <span>Retorno</span>
          <span>Precio</span>
          <span>Volumen</span>
          <span>F.Score</span>
          <span>Movimiento Taller</span>
          <span>Escaneo</span>
          <span style={{textAlign:'center'}}>TS</span>
          <span style={{textAlign:'center'}}>IA</span>
          <span style={{textAlign:'center'}}>SM</span>
          <span style={{color:'#4FC3F7', textAlign:'center'}}>APEX Score</span>
          <span style={{textAlign:'center'}}>Estado</span>
          <span style={{textAlign:'right'}}>Acción</span>
        </div>
        {!loading && displayList.map((opp, i) => ( 
            <ScannerRow 
                key={opp.ticker} 
                index={i} 
                opp={opp} 
                isPro={activeTab === 'VALUE'} 
                onOpenDetails={() => setSelectedStock({ ...opp, isPro: activeTab === 'VALUE' })} 
                onDelete={() => handleDeleteTicker(opp.ticker)}
            /> 
        ))}
      </div>

      {showAddModal && (
        <div style={{ position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', background: 'rgba(0,0,0,0.8)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 2000, backdropFilter: 'blur(5px)' }}>
            <div style={{ background: '#161922', width: '400px', borderRadius: '20px', border: '1px solid #22C55E', padding: '30px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                    <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 900 }}>Agregar Acción PRO</h3>
                    <button onClick={() => { setShowAddModal(false); setSearchResult(null); setSearchTicker(""); }} style={{ background: 'transparent', border: 'none', color: '#666', cursor: 'pointer', fontSize: '20px' }}>✕</button>
                </div>
                <form onSubmit={handleSearch} style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
                    <input autoFocus type="text" placeholder="Símbolo" value={searchTicker} onChange={(e) => setSearchTicker(e.target.value.toUpperCase())} style={{ flex: 1, background: '#000', border: '1px solid #333', borderRadius: '10px', padding: '12px', color: '#22C55E', fontWeight: 900 }} />
                    <button type="submit" disabled={isSearching} style={{ background: 'rgba(255,255,255,0.05)', color: '#FFF', border: 'none', padding: '0 20px', borderRadius: '10px', cursor: 'pointer', fontWeight: 800 }}>{isSearching ? '...' : 'BUSCAR'}</button>
                </form>
                {searchResult?.found && (
                    <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '12px', padding: '15px', marginBottom: '25px' }}>
                        <div style={{ fontSize: '16px', fontWeight: 900, color: '#FFF' }}>{searchResult.company_name}</div>
                        <button onClick={handleAddTicker} disabled={isAdding} style={{ width: '100%', background: '#22C55E', color: '#000', border: 'none', padding: '12px', borderRadius: '10px', marginTop: '20px', fontWeight: 950, cursor: 'pointer' }}>{isAdding ? 'PROCESANDO...' : 'AGREGAR A PRO'}</button>
                    </div>
                )}
            </div>
        </div>
      )}
      {selectedStock && <AnalysisModal stock={selectedStock} onClose={() => setSelectedStock(null)} />}
      <Link href="/stocks/universe" style={{ display: 'inline-block', marginTop: '20px', color: '#22C55E', textDecoration: 'none', fontWeight: 800, fontSize: '11px' }}>← VOLVER AL UNIVERSE BUILDER</Link>
    </div>
  )
}
