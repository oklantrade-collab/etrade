"use client"
import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import TradeMarkerChart from '@/components/TradeMarkerChart'
import toast from 'react-hot-toast'
import MarketBellButton from '@/components/MarketBellButton'
import { useMarketBell } from '@/context/MarketBellContext'

// ════════════════════════════════════════════
// APEX Priority Queue Panel
// ════════════════════════════════════════════

function GapRunnerStocksBadge({ isRunner, gapPct }: { isRunner?: boolean; gapPct?: number }) {
  if (!isRunner) return null;
  const pctStr = gapPct != null && gapPct !== 0 ? ` +${Math.abs(gapPct).toFixed(1)}%` : '';
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 5,
      padding: '3px 8px',
      borderRadius: 6,
      background: 'rgba(34, 197, 94, 0.22)',
      color: '#22C55E',
      fontWeight: 900,
      fontSize: 10,
      letterSpacing: '0.3px',
      border: '1px solid rgba(34, 197, 94, 0.5)',
      boxShadow: '0 0 10px rgba(34,197,94,0.3)',
      textTransform: 'uppercase',
      whiteSpace: 'nowrap',
    }}>
      <span style={{ fontSize: 11 }}>🚀</span>
      <span>OPEN GAP UP</span>
      {pctStr && <span style={{ opacity: 0.9 }}>{pctStr}</span>}
      <span style={{
        fontSize: 8,
        background: '#22C55E',
        color: '#000',
        padding: '1px 4px',
        borderRadius: 3,
        fontWeight: 900,
      }}>
        +25 PTS
      </span>
    </span>
  );
}

function StructuralRegimeStocksBadge({ regime, regimeCode, regimeLabel }: { regime?: any; regimeCode?: string; regimeLabel?: string }) {
  const code = regimeCode || regime?.regime_code;
  const label = regimeLabel || regime?.regime_label;
  if (!code && !label) return null;

  let bg = 'rgba(148, 163, 184, 0.15)';
  let color = '#94A3B8';
  let border = 'rgba(148, 163, 184, 0.3)';
  let icon = '⚪';
  let displayTxt = label || code;

  if (code === 'BULL_TREND_EXPANSION') {
    bg = 'rgba(34, 197, 94, 0.18)';
    color = '#22C55E';
    border = 'rgba(34, 197, 94, 0.45)';
    icon = '🟢';
    displayTxt = 'BULL EXPANSION';
  } else if (code === 'COUNTER_TREND_BOUNCE') {
    bg = 'rgba(251, 191, 36, 0.18)';
    color = '#FBBF24';
    border = 'rgba(251, 191, 36, 0.45)';
    icon = '🟡';
    displayTxt = 'REBOTE TÁCTICO';
  } else if (code === 'DEEP_BEAR_WINTER') {
    bg = 'rgba(239, 68, 68, 0.18)';
    color = '#EF4444';
    border = 'rgba(239, 68, 68, 0.45)';
    icon = '⛔';
    displayTxt = 'DEEP BEAR';
  } else if (code === 'COMPRESSION_CHOP') {
    bg = 'rgba(168, 85, 247, 0.18)';
    color = '#C084FC';
    border = 'rgba(168, 85, 247, 0.45)';
    icon = '🟣';
    displayTxt = 'SQUEEZE';
  }

  return (
    <span
      title={regime?.action_note || label}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 3,
        padding: '2px 6px',
        borderRadius: 4,
        background: bg,
        color,
        fontWeight: 900,
        fontSize: '8px',
        border: `1px solid ${border}`,
        letterSpacing: '0.2px',
        whiteSpace: 'nowrap',
      }}
    >
      <span>{icon}</span>
      <span>{displayTxt}</span>
    </span>
  );
}

function StatusBadge({ status, isOB }: { status: string, isOB: boolean }) {
  const configs: any = {
    'pending':    { label: 'PENDING',    color: '#F59E0B', bg: 'rgba(245,158,11,0.12)', icon: '⏳' },
    'buying':     { label: 'BUYING',     color: '#38BDF8', bg: 'rgba(56,189,248,0.15)', icon: '⚡' },
    'owned':      { label: 'OWNED',      color: '#22C55E', bg: 'rgba(34,197,94,0.15)',  icon: '💎' },
    'blocked':    { label: 'BLOCKED',    color: '#EF4444', bg: 'rgba(239,68,68,0.15)',  icon: '🚫' },
    'exhaustion': { label: 'GAP >25%',   color: '#EAB308', bg: 'rgba(234,179,8,0.15)',  icon: '⚠️' },
    'watching':   { label: 'WATCHING',   color: '#94A3B8', bg: 'rgba(148,163,184,0.1)', icon: '👁️' },
  };
  
  let s = status?.toLowerCase() || 'pending';
  if (isOB && s !== 'exhaustion') s = 'blocked';
  
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

function PriorityQueuePanel({ 
  queue, 
  capital, 
  summary,
  activeTab = 'TOP3',
  activeLimit = 3
}: { 
  queue: any[], 
  capital: any, 
  summary: any,
  activeTab?: string,
  activeLimit?: number
}) {
  const isGapUp = activeTab === 'GAP_UP';
  const isTop3 = activeTab === 'TOP3';
  const isQueue = activeTab === 'QUEUE';
  // Filtrar terminantemente activos bloqueados, trampas o en Deep Bear Winter de la cola activa
  const validQueue = (queue || []).filter((item: any) => {
    const st = String(item.status || item.queue_status || '').toLowerCase();
    return st !== 'blocked' && !item.is_deep_bear_excluded && !item.is_trap;
  });
  const displayQueue = (isTop3 || isGapUp) ? validQueue.slice(0, activeLimit) : validQueue.slice(0, 10);
  const hasQueue = displayQueue && displayQueue.length > 0;

  const title = isGapUp
    ? `🚀 OPEN GAP UP RUNNERS (Prioridad 1 Institucional para el BOT)`
    : (isTop3 
      ? `🎯 TOP ${activeLimit || 3} FOCO DE COMPRA (Líderes para Entrada del BOT)`
      : (isQueue ? '📊 EN COLA APEX (Acciones con Mayor APEX Score del Día)' : '🎯 COLA DE COMPRA DEL BOT (Rally & Fuerza Compradora)'));

  const badgeText = isGapUp ? 'PRIORIDAD 1 INSTITUCIONAL' : (isTop3 ? `TOP ${activeLimit || 3} FOCO ACTIVO` : 'MOMENTUM V5.5');

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
              {title}
            </h3>
            <span style={{ fontSize: '10px', color: '#22C55E', fontWeight: 800 }}>{badgeText}</span>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span style={{
            background: 'rgba(0,200,150,0.1)', color: '#00C896',
            fontSize: '10px', padding: '4px 12px', borderRadius: '20px', fontWeight: 800, border: '1px solid rgba(0,200,150,0.2)'
          }}>
            {isTop3 ? `${displayQueue.length} LÍDERES` : `${summary?.active || 0} ACTIVAS`}
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
        <div style={{ display: 'grid', gridTemplateColumns: isTop3 ? 'repeat(auto-fit, minmax(280px, 1fr))' : 'repeat(2, 1fr)', gap: '15px' }}>
            {displayQueue.map((item: any, idx: number) => {
              const apex4h = item.apex_score_4h || item.apex_4h || 0;
              const retExp = item.return_expected || item.change_pct || 0;
              const rank = item.composite_rank || parseFloat(item.rank_score) || 0;
              const status = item.status || item.queue_status || 'pending';
              const isOB = item.is_overbought || status === 'blocked';

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
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                      <span style={{ fontWeight: 900, fontSize: '15px', color: isOB ? '#EF4444' : '#FFF' }}>{item.ticker}</span>
                      <GapRunnerStocksBadge isRunner={item.is_gap_runner} gapPct={item.gap_pct} />
                      <StructuralRegimeStocksBadge regime={item.structural_regime} regimeCode={item.regime_code} regimeLabel={item.regime_label} />
                      {item.entry_reason?.includes('high_growth') && (
                        <span style={{ fontSize: '7px', background: 'linear-gradient(90deg, #F59E0B, #EF4444)', color: '#FFF', padding: '1px 3px', borderRadius: '3px', fontWeight: 950 }}>🔥 ALTA</span>
                      )}
                    </div>
                    <div style={{ fontSize: '10px', color: '#555', fontWeight: 800 }}>
                      RANK {rank.toFixed(1)}{item.rvol ? ` · ${item.rvol}x` : ''}
                    </div>
                  </div>

                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <span style={{ color: '#38BDF8', fontSize: '11px', fontWeight: 900 }}>
                        {item.buying_force_score ? `⚡ BF: ${item.buying_force_score}/100` : (rank > 0 ? `⚡ SCORE: ${rank.toFixed(0)}` : `${apex4h.toFixed(0)}% APEX`)}
                      </span>
                      <span style={{ color: retExp > 0 ? '#22C55E' : '#EF4444', fontSize: '11px', fontWeight: 800 }}>
                        {retExp > 0 ? '+' : ''}{retExp.toFixed(2)}%
                      </span>
                    </div>
                    <div style={{ height: '4px', background: 'rgba(255,255,255,0.05)', borderRadius: '2px' }}>
                      <div style={{
                        width: `${Math.min(100, item.buying_force_score || apex4h)}%`, height: '100%',
                        background: (item.buying_force_score || apex4h) >= 75 ? '#22C55E' : (item.buying_force_score || apex4h) >= 50 ? '#38BDF8' : '#F59E0B',
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
        const tvTimezone = typeof window !== "undefined" ? (localStorage.getItem("app_timezone") || "America/Lima") : "America/Lima";

        new (window as any).TradingView.widget({
          "autosize": true,
          "symbol": symbol,
          "interval": "D",
          "timezone": tvTimezone,
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

function RankingHeaderTooltip() {
  const [showTip, setShowTip] = useState(false);

  return (
    <div 
      style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', cursor: 'help' }}
      onMouseEnter={() => setShowTip(true)}
      onMouseLeave={() => setShowTip(false)}
    >
      <span style={{ color: '#4FC3F7', borderBottom: '1px dashed #4FC3F7', paddingBottom: '1px' }}>
        # RANK ⓘ
      </span>

      {showTip && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, marginTop: '8px',
          width: '350px', background: '#11141C', border: '1px solid #38BDF8',
          borderRadius: '12px', padding: '14px 16px', zIndex: 3000,
          boxShadow: '0 10px 30px rgba(0,0,0,0.8)', color: '#FFF',
          fontSize: '11px', textTransform: 'none', letterSpacing: 'normal', fontWeight: 'normal'
        }}>
          <div style={{ fontWeight: 900, color: '#38BDF8', marginBottom: '6px', fontSize: '12px' }}>
            🎯 FÓRMULA DEL RANKING DINÁMICO
          </div>
          <div style={{
            background: 'rgba(56,189,248,0.1)', padding: '6px 10px', borderRadius: '6px',
            fontFamily: 'monospace', fontSize: '10px', color: '#E0F2FE', marginBottom: '10px',
            border: '1px solid rgba(56,189,248,0.2)'
          }}>
            Rank = BF(5m) 40% + RVOL 20% + Noticia 25% + Vela 15%
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', color: '#CCC', fontSize: '10px' }}>
            <div><b style={{ color: '#FFF' }}>• Fuerza Compradora (5m):</b> Velocidad y dirección de empuje en 5 minutos (castigo inmediato si ΔP 5m es negativo).</div>
            <div><b style={{ color: '#FFF' }}>• RVOL (Volumen Relativo):</b> Aceleración del volumen vs promedio del día.</div>
            <div><b style={{ color: '#FFF' }}>• Catalizador Noticia:</b> Bonus por eventos de hoy/ayer (Tier 1 FDA/Patente +25, Tier 2 Earnings +15, Tier 3 PR +10).</div>
            <div><b style={{ color: '#EAB308' }}>• Candado Gap &gt; 25%:</b> -20 pts y bloqueo de apertura (09:30-10:15 ET) (Anti-LQDA / Clímax).</div>
            <div><b style={{ color: '#10B981' }}>• Sweet Spot (+5% a +25%):</b> +30 pts con confirmación 5m y Piramidación en 3 Tercios (Caso WFF).</div>
            <div><b style={{ color: '#EF4444' }}>• Candado EMA3 1H:</b> -45 pts si la EMA3 de 1H está plana o descendente (🚫 PROHIBIDO COMPRAR / AGOTAMIENTO).</div>
            <div><b style={{ color: '#94A3B8' }}>• Candado EMA3 &gt; EMA9:</b> -10 pts y bloqueo si EMA3 &le; EMA9 en 1H (falta confirmación alcista horaria).</div>
            <div><b style={{ color: '#F59E0B' }}>• Rechazo SIPV 1H:</b> -15 pts si la vela 1H viva tiene mecha superior &gt; 40% (absorción vendedora).</div>
            <div><b style={{ color: '#10B981' }}>• Bonus Pullback:</b> +25 pts si retrocede sanamente a soporte pero EXCLUSIVAMENTE con EMA3 1H ascendente Y EMA3 &gt; EMA9.</div>
          </div>
        </div>
      )}
    </div>
  );
}

function NewsModal({ stock, onClose, defaultTranslate = true, defaultLang = 'es' }: { stock: any, onClose: () => void, defaultTranslate?: boolean, defaultLang?: string }) {
  const [newsData, setNewsData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [translateToEs, setTranslateToEs] = useState<boolean>(defaultTranslate && defaultLang === 'es');
  const [modalTab, setModalTab] = useState<'news' | 'ai'>('news');

  useEffect(() => {
    if (!stock?.ticker) return;
    const loadNews = async () => {
      try {
        const res = await fetch(`/api/v1/stocks/news/${stock.ticker}`);
        const data = await res.json();
        setNewsData(data);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    loadNews();
  }, [stock?.ticker]);

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
      background: 'rgba(0,0,0,0.88)', display: 'flex', alignItems: 'center',
      justifyContent: 'center', zIndex: 2100, backdropFilter: 'blur(8px)'
    }}>
      <div style={{
        background: '#0D111A', width: '92%', maxWidth: '720px',
        borderRadius: '20px', border: '1px solid #38BDF8',
        overflow: 'hidden', boxShadow: '0 0 50px rgba(56,189,248,0.25)',
        display: 'flex', flexDirection: 'column', maxHeight: '88vh'
      }}>
        {/* Header */}
        <div style={{
          padding: '18px 24px', background: '#131826',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          borderBottom: '1px solid rgba(255,255,255,0.08)'
        }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h3 style={{ margin: 0, color: '#FFF', fontSize: '20px', fontWeight: 950, letterSpacing: '-0.3px' }}>
                📰 NOTICIAS & CATALIZADORES: {stock.ticker}
              </h3>
              {stock.catalyst_badge && (
                <span style={{
                  background: `${stock.badge_color || '#10B981'}25`,
                  border: `1px solid ${stock.badge_color || '#10B981'}70`,
                  color: stock.badge_color || '#10B981',
                  fontSize: '11px', fontWeight: 950, padding: '3px 10px', borderRadius: '6px'
                }}>
                  {stock.catalyst_badge}
                </span>
              )}
            </div>
            <div style={{ fontSize: '13px', color: '#94A3B8', marginTop: '4px', fontWeight: 600 }}>
              {stock.company_name || stock.ticker} • Feed de Inteligencia (Últimas 48h)
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              onClick={() => setTranslateToEs(!translateToEs)}
              title="Alternar traducción a Español / Inglés original"
              style={{
                background: translateToEs ? 'rgba(34,197,94,0.18)' : 'rgba(255,255,255,0.06)',
                border: `1px solid ${translateToEs ? '#22C55E' : 'rgba(255,255,255,0.2)'}`,
                color: translateToEs ? '#22C55E' : '#CBD5E1',
                fontSize: '11px',
                fontWeight: 900,
                padding: '6px 12px',
                borderRadius: '8px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}
            >
              <span>🌐</span>
              <span>{translateToEs ? 'ESPAÑOL' : 'ENGLISH'}</span>
            </button>
            <button onClick={onClose} style={{
              background: 'rgba(255,255,255,0.08)', border: 'none', color: '#FFF',
              width: '36px', height: '36px', borderRadius: '50%', cursor: 'pointer', fontWeight: 900,
              fontSize: '15px'
            }}>✕</button>
          </div>
        </div>

        {/* 2 Navigation Tabs */}
        <div style={{
          display: 'flex', borderBottom: '1px solid rgba(255,255,255,0.08)',
          background: '#0B0F19', padding: '0 20px', gap: '10px'
        }}>
          <button
            onClick={() => setModalTab('news')}
            style={{
              padding: '13px 20px', background: 'transparent', border: 'none',
              borderBottom: modalTab === 'news' ? '3px solid #38BDF8' : '3px solid transparent',
              color: modalTab === 'news' ? '#38BDF8' : '#94A3B8',
              fontSize: '14px', fontWeight: 900, cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '8px',
              transition: 'all 0.2s ease'
            }}
          >
            <span style={{ fontSize: '16px' }}>📰</span>
            <span>NOTICIAS EN ESPAÑOL</span>
            {newsData?.articles && (
              <span style={{
                background: 'rgba(56,189,248,0.18)', color: '#38BDF8',
                fontSize: '11px', padding: '2px 7px', borderRadius: '10px', fontWeight: 900
              }}>
                {newsData.articles.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setModalTab('ai')}
            style={{
              padding: '13px 20px', background: 'transparent', border: 'none',
              borderBottom: modalTab === 'ai' ? '3px solid #10B981' : '3px solid transparent',
              color: modalTab === 'ai' ? '#10B981' : '#94A3B8',
              fontSize: '14px', fontWeight: 900, cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '8px',
              transition: 'all 0.2s ease'
            }}
          >
            <span style={{ fontSize: '16px' }}>🤖</span>
            <span>INTERPRETACIÓN GEMINI & CATALIZADOR</span>
            <span style={{
              background: 'rgba(16,185,129,0.2)', color: '#10B981',
              fontSize: '11px', padding: '2px 8px', borderRadius: '10px', fontWeight: 950
            }}>
              +{newsData?.bonus_points || stock.catalyst_bonus || 10} PTS
            </span>
          </button>
        </div>

        {/* Content Body */}
        <div style={{ padding: '22px 24px', overflowY: 'auto', flex: 1 }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: '50px 20px', color: '#94A3B8', fontSize: '15px', fontWeight: 700 }}>
              <div style={{ fontSize: '30px', marginBottom: '12px' }}>⏳</div>
              Consultando noticias y evaluando catalizador con IA para {stock.ticker}...
            </div>
          ) : modalTab === 'news' ? (
            /* ══ PESTAÑA 1: NOTICIAS EN ESPAÑOL (Alta Legibilidad para Miopía) ══ */
            (!newsData?.articles || newsData.articles.length === 0) ? (
              <div style={{ textAlign: 'center', padding: '50px 20px', color: '#64748B' }}>
                <div style={{ fontSize: '36px', marginBottom: '12px' }}>📭</div>
                <div style={{ fontSize: '16px', fontWeight: 800, color: '#E2E8F0' }}>Sin noticias recientes en las últimas 48 horas</div>
                <div style={{ fontSize: '13px', color: '#94A3B8', marginTop: '6px' }}>
                  El movimiento del ticker responde a factores técnicos, volumen de escáner o rotación de mercado.
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                {newsData.articles.map((art: any, i: number) => {
                  const titleToDisplay = (translateToEs && art.title_es) ? art.title_es : art.title;
                  const summaryToDisplay = (translateToEs && art.summary_es) ? art.summary_es : art.summary;
                  return (
                    <div key={i} style={{
                      background: 'rgba(255,255,255,0.03)', padding: '16px 20px',
                      borderRadius: '14px', border: '1px solid rgba(255,255,255,0.08)',
                      display: 'flex', flexDirection: 'column', gap: '10px',
                      boxShadow: '0 4px 15px rgba(0,0,0,0.2)'
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{
                          fontSize: '11px', fontWeight: 950,
                          background: `${art.color}25`, color: art.color,
                          border: `1px solid ${art.color}60`, padding: '3px 8px', borderRadius: '6px'
                        }}>
                          {art.label} (+{art.bonus} pts)
                        </span>
                        <span style={{ fontSize: '12px', color: '#94A3B8', fontWeight: 700 }}>
                          {art.publisher} • {art.published_at}
                        </span>
                      </div>
                      <div style={{ fontSize: '16px', fontWeight: 800, color: '#FFFFFF', lineHeight: '1.45' }}>
                        {titleToDisplay}
                      </div>
                      {summaryToDisplay && summaryToDisplay !== titleToDisplay && (
                        <div style={{ fontSize: '13px', color: '#CBD5E1', lineHeight: '1.55', fontWeight: 500 }}>
                          {summaryToDisplay}
                        </div>
                      )}
                      {art.url && (
                        <div style={{ alignSelf: 'flex-start', marginTop: '2px' }}>
                          <a href={art.url} target="_blank" rel="noopener noreferrer" style={{
                            color: '#38BDF8', fontSize: '12px', fontWeight: 900,
                            textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '4px'
                          }}>
                            <span>Leer artículo original</span>
                            <span>↗</span>
                          </a>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )
          ) : (
            /* ══ PESTAÑA 2: INTERPRETACIÓN GEMINI & JUSTIFICACIÓN DEL CATALIZADOR ══ */
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* Card 1: Puntuación Cuantitativa */}
              <div style={{
                background: 'linear-gradient(135deg, rgba(56,189,248,0.14) 0%, rgba(16,185,129,0.14) 100%)',
                border: '1px solid rgba(56,189,248,0.4)', borderRadius: '16px', padding: '20px',
                boxShadow: '0 8px 24px rgba(0,0,0,0.3)'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '20px' }}>⚡</span>
                    <span style={{ fontSize: '13px', fontWeight: 950, color: '#38BDF8', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                      Puntuación Asignada al Catalizador
                    </span>
                  </div>
                  <span style={{
                    fontSize: '18px', fontWeight: 950, color: '#10B981',
                    background: 'rgba(16,185,129,0.22)', padding: '4px 14px', borderRadius: '10px',
                    border: '1px solid rgba(16,185,129,0.5)'
                  }}>
                    +{newsData?.bonus_points || stock.catalyst_bonus || 10} / 30 PTS
                  </span>
                </div>
                <div style={{ fontSize: '16px', color: '#FFFFFF', fontWeight: 700, lineHeight: '1.5', marginBottom: '10px' }}>
                  {newsData?.catalyst_summary_es || stock.catalyst_summary_es || 'Impulso respaldado por flujo informativo relevante.'}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', color: '#94A3B8', fontWeight: 700 }}>
                  <span>Modelo de IA: <b style={{ color: '#38BDF8' }}>{newsData?.source_model || 'Google Gemini 1.5 Flash'}</b></span>
                  <span style={{ color: '#10B981', fontWeight: 800 }}>Impacto en Ranking: Ponderación Activa</span>
                </div>
              </div>

              {/* Card 2: Justificación Detallada */}
              <div style={{
                background: 'rgba(56,189,248,0.06)', border: '1px solid rgba(56,189,248,0.25)',
                borderRadius: '16px', padding: '18px 20px',
                boxShadow: '0 4px 15px rgba(0,0,0,0.2)'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontWeight: 950, color: '#38BDF8', marginBottom: '8px' }}>
                  <span>⚖️</span>
                  <span>JUSTIFICACIÓN DE LA PUNTUACIÓN OTORGADA:</span>
                </div>
                <div style={{ fontSize: '14px', color: '#E2E8F0', lineHeight: '1.65', fontWeight: 500 }}>
                  {newsData?.score_justification || (
                    stock.catalyst_badge?.includes('FDA')
                      ? 'Puntuación de +25 pts otorgada por tratarse de un catalizador regulatorio de primer orden (FDA / Ensayo Clínico). Genera barrera de entrada comercial, exclusividad de mercado y flujo de ingresos recurrente no dependiente del ciclo económico.'
                      : (stock.catalyst_badge?.includes('Contrato') || stock.catalyst_badge?.includes('M&A'))
                        ? 'Puntuación de +25 pts asignada por acuerdo contractual vinculante o transacción corporativa que expande de inmediato la facturación y el Ebitda proyectado del ejercicio actual.'
                        : 'Puntuación asignada por presencia mediática relevante y volumen comprador que respalda la ruptura técnica del día.'
                  )}
                </div>
              </div>

              {/* Card 3: Catalizador Oculto & Proyección Intradía */}
              <div style={{
                background: 'linear-gradient(135deg, rgba(245,158,11,0.14) 0%, rgba(239,68,68,0.08) 100%)',
                border: '1px solid rgba(245,158,11,0.4)',
                borderRadius: '16px', padding: '18px 20px',
                boxShadow: '0 4px 20px rgba(245,158,11,0.1)'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontWeight: 950, color: '#F59E0B' }}>
                    <span>🔍</span>
                    <span>CATALIZADOR OCULTO & PROYECCIÓN INTRADÍA:</span>
                  </div>
                  <span style={{
                    fontSize: '11px', fontWeight: 950, color: '#F59E0B',
                    background: 'rgba(245,158,11,0.22)', padding: '3px 10px', borderRadius: '6px',
                    border: '1px solid rgba(245,158,11,0.4)'
                  }}>
                    {newsData?.projected_impact || 'ALTO / EXPLOSIVO'}
                  </span>
                </div>
                <div style={{ fontSize: '14px', color: '#FEF3C7', lineHeight: '1.65', fontWeight: 600 }}>
                  {newsData?.hidden_catalyst || (
                    'Estructura de bajo float y alta concentración compradora: la noticia atrae liquidez institucional que absorbe rápidamente la oferta disponible, proyectando un incremento considerable de precio para la sesión sin techos técnicos inmediatos.'
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: '14px 24px', background: '#131826', borderTop: '1px solid rgba(255,255,255,0.08)', textAlign: 'right' }}>
          <button onClick={onClose} style={{
            background: '#38BDF8', color: '#000', border: 'none',
            padding: '10px 24px', borderRadius: '10px', fontWeight: 950, fontSize: '12px', cursor: 'pointer',
            letterSpacing: '0.05em'
          }}>CERRAR</button>
        </div>
      </div>
    </div>
  );
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

                {/* Régimen Estructural 1D (EMA 3/9/20/50/200 & Bollinger) */}
                {(stock.structural_regime?.regime_code || stock.regime_code) && (
                  <div style={{ background: '#0D0E14', padding: '14px', borderRadius: '14px', border: '1px solid rgba(255,255,255,0.06)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px', flexWrap: 'wrap', gap: '6px' }}>
                      <span style={{ fontSize: '9px', fontWeight: 950, color: '#38BDF8', letterSpacing: '0.5px' }}>
                        📐 RÉGIMEN ESTRUCTURAL 1D
                      </span>
                      <StructuralRegimeStocksBadge regime={stock.structural_regime} regimeCode={stock.regime_code} regimeLabel={stock.regime_label} />
                    </div>
                    {stock.structural_regime?.action_note && (
                      <div style={{ fontSize: '10px', color: '#BBB', marginBottom: '8px', fontStyle: 'italic', background: 'rgba(255,255,255,0.02)', padding: '5px 8px', borderRadius: '4px' }}>
                        {stock.structural_regime.action_note}
                      </div>
                    )}
                    {stock.structural_regime?.emas && (
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '4px', textAlign: 'center' }}>
                        <div style={{ background: 'rgba(255,255,255,0.02)', padding: '4px', borderRadius: '4px' }}>
                          <span style={{ fontSize: '7.5px', color: '#777', display: 'block' }}>EMA 3</span>
                          <b style={{ color: '#FFF', fontSize: '9.5px' }}>${stock.structural_regime.emas.ema3}</b>
                        </div>
                        <div style={{ background: 'rgba(255,255,255,0.02)', padding: '4px', borderRadius: '4px' }}>
                          <span style={{ fontSize: '7.5px', color: '#777', display: 'block' }}>EMA 9</span>
                          <b style={{ color: '#FFF', fontSize: '9.5px' }}>${stock.structural_regime.emas.ema9}</b>
                        </div>
                        <div style={{ background: 'rgba(255,255,255,0.02)', padding: '4px', borderRadius: '4px' }}>
                          <span style={{ fontSize: '7.5px', color: '#777', display: 'block' }}>EMA 20</span>
                          <b style={{ color: '#FBBF24', fontSize: '9.5px' }}>${stock.structural_regime.emas.ema20}</b>
                        </div>
                        <div style={{ background: 'rgba(255,255,255,0.02)', padding: '4px', borderRadius: '4px' }}>
                          <span style={{ fontSize: '7.5px', color: '#777', display: 'block' }}>EMA 50</span>
                          <b style={{ color: '#38BDF8', fontSize: '9.5px' }}>${stock.structural_regime.emas.ema50}</b>
                        </div>
                        <div style={{ background: 'rgba(255,255,255,0.02)', padding: '4px', borderRadius: '4px' }}>
                          <span style={{ fontSize: '7.5px', color: '#777', display: 'block' }}>EMA 200</span>
                          <b style={{ color: '#EF4444', fontSize: '9.5px' }}>${stock.structural_regime.emas.ema200}</b>
                        </div>
                      </div>
                    )}
                    {stock.structural_regime?.target_ceiling && (
                      <div style={{ marginTop: '6px', fontSize: '9.5px', color: '#888', display: 'flex', justifyContent: 'space-between', borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '4px' }}>
                        <span>Techo Técnico (Muro):</span>
                        <b style={{ color: '#FFD700' }}>${stock.structural_regime.target_ceiling}</b>
                      </div>
                    )}
                  </div>
                )}
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

                            {/* CAPA 6: INTRADAY ALPHA, TRAP SHIELD & ADUANA EXITS */}
                            <div style={{ marginTop:'15px', padding:'15px', background:'rgba(56,189,248,0.03)', borderRadius:'12px', border:'1px solid rgba(56,189,248,0.2)' }}>
                                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'10px' }}>
                                    <span style={{ color:'#38BDF8', fontWeight:950, fontSize:'10px', textTransform:'uppercase', letterSpacing:'1px' }}>🚀 MOTOR INTRADÍA ALPHA & ESCUDO ANTI-TRAMPAS</span>
                                    {stock.is_trap ? (
                                        <span style={{ background:'rgba(239,68,68,0.2)', border:'1px solid #EF4444', color:'#EF4444', fontSize:'9px', padding:'2px 8px', borderRadius:'4px', fontWeight:900 }}>🚫 BLOQUEADO POR TRAP SHIELD</span>
                                    ) : stock.is_intraday_alpha ? (
                                        <span style={{ background:'linear-gradient(90deg, #10B981, #06B6D4)', color:'#000', fontSize:'9px', padding:'2px 8px', borderRadius:'4px', fontWeight:950 }}>🚀 ALPHA CANDIDATE</span>
                                    ) : (
                                        <span style={{ background:'rgba(255,255,255,0.05)', color:'#888', fontSize:'9px', padding:'2px 8px', borderRadius:'4px', fontWeight:800 }}>ESTÁNDAR</span>
                                    )}
                                </div>
                                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'10px', fontSize:'11px', color:'#CCC', marginBottom:'10px' }}>
                                    <div style={{ background:'rgba(0,0,0,0.3)', padding:'10px', borderRadius:'8px' }}>
                                        <div style={{ fontSize:'8px', color:'#888', fontWeight:800 }}>APERTURA & SWEET SPOT</div>
                                        <div style={{ fontSize:'12px', fontWeight:900, color: (stock.gap_pct || 0) > 35 ? '#EF4444' : '#22C55E' }}>
                                            Gap: {(stock.gap_pct || 0) >= 0 ? '+' : ''}{(stock.gap_pct || 0).toFixed(1)}% {((stock.gap_pct || 0) <= 35 && (stock.gap_pct || 0) >= -3) ? '✅ Sweet Spot' : '⚠️ Fuera de Rango'}
                                        </div>
                                        <div style={{ fontSize:'9px', color:'#666', marginTop:'2px' }}>Potencial Intradía: +{(stock.growth_potential_pct || 5).toFixed(1)}%</div>
                                    </div>
                                    <div style={{ background:'rgba(0,0,0,0.3)', padding:'10px', borderRadius:'8px' }}>
                                        <div style={{ fontSize:'8px', color:'#888', fontWeight:800 }}>SALIDAS ADUANA FIBONACCI</div>
                                        <div style={{ fontSize:'12px', fontWeight:900, color:'#38BDF8' }}>
                                            TP1 (50%): ${stock.target_upper5 ? stock.target_upper5.toFixed(2) : '—'} (UPPER_5)
                                        </div>
                                        <div style={{ fontSize:'9px', color:'#888', marginTop:'2px' }}>
                                            Clímax Total: ${stock.target_upper6 ? stock.target_upper6.toFixed(2) : '—'} (UPPER_6) | Hard-Exit: 15:50 ET
                                        </div>
                                    </div>
                                </div>
                                {stock.catalyst_name && stock.catalyst_name !== 'NO_RECENT_NEWS' && (
                                    <div style={{ fontSize:'10px', color:'#AAA', background:'rgba(255,255,255,0.02)', padding:'8px', borderRadius:'6px' }}>
                                        <b style={{ color: stock.catalyst_tier === 0 ? '#EF4444' : stock.catalyst_tier === 1 ? '#00C896' : '#38BDF8' }}>
                                            {stock.catalyst_tier === 0 ? '🚫 PELIGRO DILUCIÓN: ' : stock.catalyst_tier === 1 ? '⚡ CATALIZADOR TIER 1: ' : '📰 EVENTO TIER 2: '}
                                        </b>
                                        {stock.catalyst_headline || stock.catalyst_reason}
                                    </div>
                                )}
                                {stock.pullback_triggered && (
                                    <div style={{ marginTop:'10px', fontSize:'10px', color:'#CCC', background:'rgba(139,92,246,0.1)', border:'1px solid rgba(139,92,246,0.3)', padding:'8px', borderRadius:'6px' }}>
                                        <b style={{ color: '#A78BFA' }}>🎯 RETROCESO DETECTADO ({stock.pullback_type || 'PULLBACK'}): </b>
                                        {stock.pullback_reason}
                                        {stock.pullback_limit_orders && stock.pullback_limit_orders.length > 0 && (
                                            <div style={{ marginTop:'4px', display:'flex', gap:'8px', fontSize:'9px', color:'#FFF' }}>
                                                {stock.pullback_limit_orders.map((lo: any, idx: number) => (
                                                    <span key={idx} style={{ background:'rgba(255,255,255,0.08)', padding:'2px 6px', borderRadius:'4px' }}>
                                                        Orden LIMIT {lo.ema_target}: <b>${lo.limit_price}</b> (TTL: {lo.ttl_minutes}m)
                                                    </span>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>

                            {/* ESCUDO DEFENSIVO ADUANA GAP RUNNER (STOCKS) */}
                            {Boolean(stock.is_gap_runner) && (
                                <div style={{ marginTop:'15px', padding:'15px', background:'rgba(34,197,94,0.08)', borderRadius:'12px', border:'1px solid rgba(34,197,94,0.3)', boxShadow:'0 0 15px rgba(34,197,94,0.1)' }}>
                                    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'8px' }}>
                                        <div style={{ display:'flex', alignItems:'center', gap:'6px' }}>
                                            <span style={{ fontSize:'14px' }}>🛡️</span>
                                            <span style={{ color:'#22C55E', fontWeight:950, fontSize:'11px', textTransform:'uppercase', letterSpacing:'1px' }}>ESCUDO DEFENSIVO ADUANA GAP RUNNER (STOCKS)</span>
                                        </div>
                                        <span style={{ background:'#22C55E', color:'#000', fontSize:'9px', padding:'2px 8px', borderRadius:'4px', fontWeight:950 }}>
                                            PRIORIDAD 1 INSTITUCIONAL
                                        </span>
                                    </div>
                                    <div style={{ fontSize:'11px', color:'#CCC', lineHeight:1.6 }}>
                                        <div><b>• Hard Stop Loss:</b> Cierre de vela de 15m por debajo de EMA9 15m.</div>
                                        <div><b>• Trailing Stop Dinámico:</b> Activación al midpoint 1H tras superar R1 (+1.5R de ganancia) para proteger el trade.</div>
                                        <div><b>• Toma de Beneficios (3 Tranches):</b> 50% en Upper 5 | 25% en Upper 6 | 25% trailing libre hasta Clímax RSI 1H &gt; 85 o 15:50 ET liquidación obligatoria.</div>
                                        <div><b>• Anti-Trap Shield:</b> Sin dilución pendiente (S-3/ATM), confirmación de apertura libre de trampa bajista.</div>
                                    </div>
                                </div>
                            )}
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

function ScannerRow({ opp, index, isPro, onOpenDetails, onDelete, onOpenNews }: any) {
  const rank = opp.rank || index + 1;
  const medal = rank === 1 ? '🥇' : (rank === 2 ? '🥈' : (rank === 3 ? '🥉' : ''));
  const rankScore = parseFloat(opp.rank_score) || parseFloat(opp.buying_force_5m) || 50;

  // Semáforo info
  const semColor = opp.semaphore_color || (opp.semaphore === 'PULLBACK' ? '#10B981' : (opp.semaphore === 'CLIMAX' ? '#F59E0B' : '#94A3B8'));
  const semLabel = opp.semaphore_label || (opp.semaphore === 'PULLBACK' ? '🟢 PULLBACK' : (opp.semaphore === 'CLIMAX' ? '🟡 CLÍMAX' : '⚪ MONITOREO'));
  const semTip = opp.semaphore_tip || 'Evaluación técnica 5m';

  // Fuerza Compradora 5m
  const bf5m = parseInt(opp.buying_force_5m) || 50;
  const delta5m = opp.delta_p_5m !== undefined ? opp.delta_p_5m : 0.0;

  // News / Catalizador
  const hasNews = Boolean(opp.has_news && opp.catalyst_badge);
  const badgeLabel = opp.catalyst_badge || '';
  const badgeColor = opp.badge_color || '#38BDF8';
  const newsBonus = opp.news_bonus || 0;

  return (
    <div className="scanner-row" style={{ 
      display: 'grid', 
      gridTemplateColumns: '70px 105px 110px 100px 125px 150px 1fr 105px 90px 55px', 
      padding: '12px 16px', 
      borderBottom: '1px solid rgba(255,255,255,0.03)', 
      alignItems: 'center', 
      transition: 'all 0.2s ease',
      background: index % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' 
    }}>
      {/* 1. # Rank */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <span style={{
            fontSize: '12px', fontWeight: 950,
            color: rank <= 3 ? '#F59E0B' : '#888',
            fontFamily: 'monospace'
          }}>
            #{rank}
          </span>
          {medal && <span style={{ fontSize: '12px' }}>{medal}</span>}
        </div>
        <span style={{ fontSize: '10px', color: '#38BDF8', fontWeight: 800 }}>
          {rankScore.toFixed(0)} pts
        </span>
      </div>

      {/* 2. Ticker & Badges */}
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{ display:'flex', alignItems:'center', gap: '4px', flexWrap: 'wrap' }}>
          <span style={{ fontWeight: 950, color: '#FFF', fontSize: '14px', letterSpacing: '-0.5px' }}>{opp.ticker}</span>
          <GapRunnerStocksBadge isRunner={opp.is_gap_runner} gapPct={opp.gap_pct} />
          <StructuralRegimeStocksBadge regime={opp.structural_regime} regimeCode={opp.regime_code} regimeLabel={opp.regime_label} />
          {opp.queue_rank && (
            <span style={{ fontSize: '8px', background: 'rgba(56,189,248,0.2)', border: '1px solid #38BDF8', color: '#38BDF8', padding: '1px 5px', borderRadius: '4px', fontWeight: 950 }}>🎯 COLA #{opp.queue_rank}</span>
          )}
          {opp.is_high_growth_opp && (
            <span style={{ fontSize: '7px', background: 'linear-gradient(90deg, #F59E0B, #EF4444)', color: '#FFF', padding: '1px 3px', borderRadius: '3px', fontWeight: 950 }}>🔥 ALTA</span>
          )}
          {opp.is_intraday_alpha && (
            <span style={{ fontSize: '7px', background: 'linear-gradient(90deg, #10B981, #06B6D4)', color: '#000', padding: '1px 3px', borderRadius: '3px', fontWeight: 950 }}>🚀</span>
          )}
          {opp.room_to_bb_upper_1d !== undefined && opp.room_to_bb_upper_1d !== null && (
            <span style={{
              fontSize: '7.5px',
              background: opp.room_to_bb_upper_1d >= 20 ? 'rgba(34,197,94,0.18)' : 'rgba(56,189,248,0.18)',
              border: `1px solid ${opp.room_to_bb_upper_1d >= 20 ? '#22C55E' : '#38BDF8'}`,
              color: opp.room_to_bb_upper_1d >= 20 ? '#22C55E' : '#38BDF8',
              padding: '1px 4px',
              borderRadius: '3px',
              fontWeight: 950
            }} title={`Espacio a Bollinger Superior 1D: +${opp.room_to_bb_upper_1d.toFixed(1)}% (SMA20 1D: $${opp.sma20_1d || '?'}, BB Sup 1D: $${opp.bb_upper_1d || '?'})`}>
              🚀 BB 1D: +{opp.room_to_bb_upper_1d.toFixed(0)}%
            </span>
          )}
        </div>
        <span style={{ fontSize: '9px', color: '#666', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '95px' }}>
          {opp.company_name || opp.ticker}
        </span>
      </div>
      
      {/* 3. Precio / Var */}
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <span style={{ fontWeight: 800, fontSize:'13px', color: '#EEE' }}>${(opp.price || 0).toFixed(2)}</span>
        <span style={{ color:(opp.change_pct || 0) >= 0 ? '#22C55E' : '#EF4444', fontWeight:900, fontSize:'11px' }}>
          {opp.change_pct > 0 ? '+' : ''}{(opp.change_pct || 0).toFixed(2)}%
        </span>
      </div>

      {/* 4. Vol / RVOL */}
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <span style={{ fontWeight: 800, fontSize:'11px', color: '#DDD' }}>
          {opp.volume ? (opp.volume / 1_000_000).toFixed(2) + 'M' : '—'}
        </span>
        <span style={{ fontSize: '9px', color: '#888', fontWeight: 700 }}>
          RVOL: <b style={{ color: (opp.rvol || 1) >= 2.0 ? '#38BDF8' : '#AAA' }}>{(opp.rvol || 1.0).toFixed(1)}x</b>
        </span>
      </div>

      {/* 5. Fuerza Compradora (5m) */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: '4px',
          background: bf5m >= 70 ? 'rgba(34,197,94,0.15)' : (bf5m >= 50 ? 'rgba(56,189,248,0.15)' : 'rgba(245,158,11,0.15)'),
          color: bf5m >= 70 ? '#22C55E' : (bf5m >= 50 ? '#38BDF8' : '#F59E0B'),
          border: `1px solid ${bf5m >= 70 ? '#22C55E33' : '#38BDF833'}`,
          padding: '2px 8px', borderRadius: '6px', fontSize: '11px', fontWeight: 950
        }}>
          <span>⚡ {bf5m}/100</span>
        </div>
        <span style={{ fontSize: '9px', color: delta5m >= 0 ? '#22C55E' : '#EF4444', fontWeight: 800, marginTop: '2px' }}>
          5m: {delta5m >= 0 ? '+' : ''}{delta5m.toFixed(2)}%
        </span>
      </div>

      {/* 6. Semáforo Entrada */}
      <div style={{ display: 'flex', justifyContent: 'center' }} title={semTip}>
        <div style={{
          fontSize: '9px', fontWeight: 900, padding: '3px 8px', borderRadius: '6px',
          background: `${semColor}18`, color: semColor, border: `1px solid ${semColor}44`,
          textAlign: 'center', letterSpacing: '0.02em', cursor: 'help'
        }}>
          {semLabel}
        </div>
      </div>

      {/* 7. Noticias / Catalizador */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        {hasNews ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
            <span style={{
              background: `${badgeColor}18`, color: badgeColor,
              border: `1px solid ${badgeColor}44`, fontSize: '9px',
              fontWeight: 900, padding: '2px 6px', borderRadius: '4px'
            }}>
              {badgeLabel} {newsBonus > 0 ? `(+${newsBonus})` : ''}
            </span>
            <button
              onClick={() => onOpenNews(opp)}
              title="Leer titulares y artículos originales"
              style={{
                background: 'rgba(56,189,248,0.1)', border: '1px solid rgba(56,189,248,0.3)',
                color: '#38BDF8', fontSize: '9px', fontWeight: 900, padding: '2px 8px',
                borderRadius: '6px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '3px'
              }}
            >
              <span>📰 Leer</span>
            </button>
          </div>
        ) : (
          <span style={{ color: '#444', fontSize: '12px', fontWeight: 700 }}>—</span>
        )}
      </div>

      {/* 8. APEX Score */}
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <ApexBadge score4h={opp.apex_4h} score1d={opp.apex_1d} signal={opp.apex_signal} confidence={opp.apex_conf} edge={opp.apex_edge} />
      </div>

      {/* 9. Estado */}
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <StatusBadge 
          status={opp.semaphore === 'EXHAUSTION_GAP' ? 'exhaustion' : (opp.semaphore === 'DESCENDING' || opp.semaphore === 'BELOW_EMA9' || opp.is_ema3_1h_descending || opp.is_ema3_above_ema9 === false ? 'blocked' : opp.queue_status)} 
          isOB={opp.is_overbought_queue || opp.semaphore === 'DESCENDING' || opp.semaphore === 'BELOW_EMA9' || opp.semaphore === 'EXHAUSTION_GAP' || Boolean(opp.is_ema3_1h_descending) || opp.is_ema3_above_ema9 === false} 
        />
      </div>

      {/* 10. Acción */}
      <div style={{textAlign:'right', display: 'flex', justifyContent: 'flex-end', gap: '6px'}}>
        <button onClick={onOpenDetails} title="Analizar Empresa" style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)', color: '#22C55E', width: '30px', height: '30px', borderRadius: '50%', fontSize: '13px', cursor: 'pointer', display: 'inline-flex', justifyContent: 'center', alignItems: 'center', transition: 'all 0.2s' }}>🔍</button>
        {isPro && (
            <button onClick={onDelete} title="Eliminar de PRO" style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#EF4444', width: '30px', height: '30px', borderRadius: '50%', fontSize: '13px', cursor: 'pointer', display: 'inline-flex', justifyContent: 'center', alignItems: 'center', transition: 'all 0.2s' }}>—</button>
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


function formatLastScanTime(raw?: string): string {
  if (!raw || raw === '--:--' || raw === 'RECIBIENDO...') return raw || 'RECIBIENDO...';
  if (raw.includes('UTC')) {
    const match = raw.match(/(\d{1,2}):(\d{2})/);
    if (match) {
      const utcHours = parseInt(match[1], 10);
      const utcMins = parseInt(match[2], 10);
      const limaHours = (utcHours - 5 + 24) % 24;
      const nycHours = (utcHours - 4 + 24) % 24;
      const today = new Date().toLocaleDateString('es-PE', { day: '2-digit', month: '2-digit' });
      return `${String(limaHours).padStart(2, '0')}:${String(utcMins).padStart(2, '0')} Lima (${String(nycHours).padStart(2, '0')}:${String(utcMins).padStart(2, '0')} ET) · ${today}`;
    }
  }
  return raw;
}
export default function OpportunitiesIntelligence() {
  const { nextBell, nycTime } = useMarketBell()
  const [opportunities, setOpportunities] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [selectedStock, setSelectedStock] = useState<any | null>(null)
  const [activeTab, setActiveTab] = useState<'TOP3' | 'GAP_UP' | 'ALPHA' | 'HOT' | 'QUEUE' | 'VALUE'>('TOP3')
  const [newsStock, setNewsStock] = useState<any | null>(null)
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
    maxHotResults: 50,
    language: 'es',
    translateNews: true,
    activeStocksLimit: 3
  })
  const [showSettings, setShowSettings] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [searchTicker, setSearchTicker] = useState("");
  const [searchResult, setSearchResult] = useState<any>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isAdding, setIsAdding] = useState(false);

  useEffect(() => {
    try {
      const saved = localStorage.getItem('etrade_scanner_settings');
      if (saved) {
        setSettings(prev => ({ ...prev, ...JSON.parse(saved) }));
      }
    } catch (e) {
      // ignore
    }
  }, []);

  const updateSettings = (newSettings: any) => {
    setSettings(newSettings);
    try {
      localStorage.setItem('etrade_scanner_settings', JSON.stringify(newSettings));
    } catch (e) {
      // ignore
    }
  };

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

  // Añadir información de posición en la cola de compras a cada oportunidad
  const opportunitiesWithQueue = mergedOpportunities.map(opp => {
    const queueIdx = priorityQueue.findIndex((pq: any) => pq.ticker === opp.ticker);
    return {
      ...opp,
      queue_rank: queueIdx !== -1 ? queueIdx + 1 : null
    };
  });

  // Cola APEX: Filtra acciones con alto APEX Score del día (>= 60), descartando bloqueadas o bajistas (-1.5%)
  const queueList = opportunitiesWithQueue
    .filter(o => {
      const isBlocked = o.status === 'blocked' || o.queue_status === 'blocked' || o.is_deep_bear_excluded;
      if (isBlocked) return false;
      const apex = o.apex_4h || o.apex_1d || 0;
      const chg = o.change_pct !== undefined ? o.change_pct : 0;
      if (chg < -1.5) return false;
      return apex >= 60 || o.queue_rank !== null || o._from_priority_queue;
    })
    .sort((a, b) => {
      const apexA = a.apex_4h || a.apex_1d || 0;
      const apexB = b.apex_4h || b.apex_1d || 0;
      if (apexB !== apexA) return apexB - apexA;
      return (a.queue_rank || 999) - (b.queue_rank || 999);
    });

  // Open Gap Up Runners: Prioridad 1 Institucional (excluyendo bloqueadas)
  const gapUpList = opportunitiesWithQueue
    .filter(o => o.is_gap_runner && o.status !== 'blocked' && o.queue_status !== 'blocked' && !o.is_deep_bear_excluded)
    .sort((a, b) => {
      const scoreDiff = (parseFloat(b.rank_score) || b.buying_force_5m || 0) - (parseFloat(a.rank_score) || a.buying_force_5m || 0);
      if (scoreDiff !== 0) return scoreDiff;
      return (b.gap_pct || 0) - (a.gap_pct || 0);
    });

  const hotList = opportunitiesWithQueue
    .filter(o => o._from_priority_queue || (o.price <= settings.hotMaxPrice && o.volume >= settings.minVolume))
    .sort((a, b) => (parseFloat(b.rank_score) || b.buying_force_5m || 0) - (parseFloat(a.rank_score) || a.buying_force_5m || 0))
    .slice(0, 20);

  const alphaList = opportunitiesWithQueue
    .filter(o => {
      // Excluir terminantemente bloqueadas, en trampa, o en Deep Bear Winter
      const isBlocked = o.status === 'blocked' || o.queue_status === 'blocked' || o.is_overbought_queue || o.is_deep_bear_excluded || o.is_trap;
      if (isBlocked) return false;
      // Excluir si 1H EMA3 < EMA9 (a menos que tenga reversión explosiva con RVOL >= 3.0x y EMA3 ascendente)
      if (o.is_ema3_above_ema9 === false && (!o.rvol || o.rvol < 3.0)) return false;
      return o.is_gap_runner || o.source === 'live_top_gainers' || o.is_intraday_alpha || o.is_high_growth_opp || (o.change_pct && o.change_pct >= 5.0);
    })
    .sort((a, b) => {
      // Prioridad 1 Absoluta a OPEN GAP UP genuinos
      if (a.is_gap_runner && !b.is_gap_runner) return -1;
      if (!a.is_gap_runner && b.is_gap_runner) return 1;
      return (parseFloat(b.rank_score) || b.buying_force_5m || 0) - (parseFloat(a.rank_score) || a.buying_force_5m || 0);
    });

  const top3List = alphaList.slice(0, settings.activeStocksLimit || 3);
  const valueList = opportunitiesWithQueue.filter(o => o.is_pro_member);
  const displayList = activeTab === 'TOP3' ? top3List : (activeTab === 'GAP_UP' ? gapUpList : (activeTab === 'ALPHA' ? alphaList : (activeTab === 'HOT' ? hotList : (activeTab === 'QUEUE' ? queueList : valueList))));

  return (
    <div style={{ padding: '24px 32px', minHeight: '100vh', background: '#090A0F', color: '#FFF', fontFamily: 'Inter, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
        <div>
          <div style={{ fontSize: '10px', fontWeight: 900, color: '#22C55E', textTransform: 'uppercase', letterSpacing: '0.2em' }}>Intelligence Layer v4.5 • APEX Score v1.0</div>
          <h1 style={{ fontSize: '24px', fontWeight: 900, margin: '4px 0', letterSpacing: '-0.02em' }}>🎯 AI Stock Scanner</h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <p style={{ color: '#555', fontSize: '12px' }}>{total} monitoreados · NYC Live Tracking</p>
               <span 
                title={`Wall Street (NYSE/NASDAQ) • NYC: ${nycTime.timeStr} ET • ${nextBell.summaryStr}`}
                style={{ 
                  fontSize: '11px', 
                  background: nextBell.isOpen ? '#22C55E' : (nextBell.statusText === 'PRE-MERCADO' ? '#EAB308' : '#EF4444'), 
                  color: nextBell.isOpen ? '#000' : '#FFF', 
                  padding: '2px 10px', 
                  borderRadius: '6px', 
                  fontWeight: 950, 
                  textTransform: 'uppercase',
                  letterSpacing: '0.03em',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  boxShadow: nextBell.isOpen ? '0 0 10px rgba(34, 197, 94, 0.25)' : 'none'
                }}
               >
                <span>{nextBell.isOpen ? '🟢' : (nextBell.statusText === 'PRE-MERCADO' ? '🟡' : '🔴')}</span>
                <span>{nextBell.detailedBadge}</span>
               </span>
              <MarketBellButton />
              {opportunities.length > 0 && (
                <span style={{ fontSize: '10px', color: '#888', fontWeight: 700 }}>
                  ÚLTIMO PROCESO: <span style={{ color: '#22C55E' }}>{formatLastScanTime(opportunities[0].last_scan_time)}</span>
                </span>
              )}
          </div>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
            <button onClick={() => setShowSettings(!showSettings)} style={{ background: showSettings ? '#22C55E' : 'rgba(255,255,255,0.05)', color: showSettings ? '#000' : '#FFF', border: 'none', padding: '10px 16px', borderRadius: '12px', fontSize: '12px', fontWeight: 900, cursor: 'pointer' }}>⚙️ FILTROS</button>
            <div style={{ display: 'flex', background: 'rgba(255,255,255,0.03)', padding: '4px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)', alignItems: 'center' }}>
                <TabButton label={`🎯 Top ${settings.activeStocksLimit || 3} Foco de Compra`} active={activeTab === 'TOP3'} onClick={() => setActiveTab('TOP3')} count={top3List.length}/>
                <TabButton label="🚀 Open Gap Up (Prioridad 1)" active={activeTab === 'GAP_UP'} onClick={() => setActiveTab('GAP_UP')} count={gapUpList.length}/>
                <TabButton label="⚡ Alpha Runners (Orden BOT Completo)" active={activeTab === 'ALPHA'} onClick={() => setActiveTab('ALPHA')} count={alphaList.length}/>
                <TabButton label="🔥 Hot by Volume (Top 20)" active={activeTab === 'HOT'} onClick={() => setActiveTab('HOT')} count={hotList.length}/>
                <TabButton label="🎯 En Cola APEX" active={activeTab === 'QUEUE'} onClick={() => setActiveTab('QUEUE')} count={queueList.length}/>
                <TabButton label="💎 Inversión Pro" active={activeTab === 'VALUE'} onClick={() => setActiveTab('VALUE')} count={valueList.length}/>
                <button onClick={() => setShowAddModal(true)} style={{ background: '#22C55E', color: '#000', border: 'none', width: '28px', height: '28px', borderRadius: '8px', marginLeft: '8px', cursor: 'pointer', fontWeight: 900, fontSize: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>+</button>
            </div>
        </div>
      </div>

      {showSettings && (
        <div style={{ background: '#161922', padding: '20px', borderRadius: '16px', marginBottom: '20px', border: '1px solid #22C55E' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '15px', marginBottom: '15px' }}>
            <SettingInput label="Hot Price Max ($)" value={settings.hotMaxPrice} onChange={(v:any) => updateSettings({...settings, hotMaxPrice: Number(v)})} />
            <SettingInput label="Min RVOL" value={settings.minRvol} onChange={(v:any) => updateSettings({...settings, minRvol: Number(v)})} step={0.1} />
            <SettingInput label="Min Volume" value={settings.minVolume} onChange={(v:any) => updateSettings({...settings, minVolume: Number(v)})} step={100000} />
            <SettingInput label="Min Market Cap" value={settings.minMarketCap} onChange={(v:any) => updateSettings({...settings, minMarketCap: Number(v)})} step={100000000} />
          </div>

          <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '15px', display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '15px', alignItems: 'center' }}>
            <SettingInput
              label="Cant. Acciones Activas (Top Foco Compra)"
              value={settings.activeStocksLimit || 3}
              onChange={(v:any) => updateSettings({...settings, activeStocksLimit: Math.max(1, Number(v) || 3)})}
              step={1}
            />

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ fontSize: '9px', fontWeight: 900, color: '#666', textTransform: 'uppercase' }}>Idioma Noticias & Análisis</label>
              <select
                value={settings.language || 'es'}
                onChange={(e) => updateSettings({...settings, language: e.target.value})}
                style={{ background: '#000', border: '1px solid #333', borderRadius: '8px', padding: '8px', color: '#22C55E', fontWeight: 900, fontSize: '12px' }}
              >
                <option value="es">🇪🇸 Español (Predeterminado)</option>
                <option value="en">🇺🇸 English (Original)</option>
              </select>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ fontSize: '9px', fontWeight: 900, color: '#666', textTransform: 'uppercase' }}>Traducción Automática (IA)</label>
              <button
                type="button"
                onClick={() => updateSettings({...settings, translateNews: !settings.translateNews})}
                style={{
                  background: settings.translateNews ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                  border: `1px solid ${settings.translateNews ? '#22C55E' : '#EF4444'}`,
                  borderRadius: '8px',
                  padding: '8px 12px',
                  color: settings.translateNews ? '#22C55E' : '#EF4444',
                  fontWeight: 900,
                  fontSize: '12px',
                  cursor: 'pointer',
                  textAlign: 'center'
                }}
              >
                {settings.translateNews ? '✅ TRADUCCIÓN ACTIVA (ES)' : '❌ TRADUCCIÓN DESACTIVADA'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ADUANA OPEN GAP UP INSTITUTIONAL BANNER (STOCKS) */}
      {gapUpList.length > 0 && (
        <div style={{
          background: 'linear-gradient(90deg, rgba(34,197,94,0.18) 0%, rgba(56,189,248,0.15) 50%, rgba(245,158,11,0.18) 100%)',
          border: '1px solid rgba(34,197,94,0.4)',
          borderRadius: 14,
          padding: '14px 20px',
          marginBottom: 18,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 12,
          boxShadow: '0 0 20px rgba(34,197,94,0.12)'
        }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <b style={{ color: '#FFF', fontSize: 14, letterSpacing: '-0.3px' }}>
                🚀 PRIORIDAD ABSOLUTA ADUANA OPEN GAP RUNNERS ACTIVA
              </b>
              <span style={{ fontSize: 9, padding: '2px 8px', borderRadius: 4, background: '#22C55E', color: '#000', fontWeight: 900 }}>
                PRIORIDAD 1 INSTITUCIONAL
              </span>
            </div>
            <p style={{ color: '#CCC', fontSize: 12, margin: '4px 0 0' }}>
              Detectados <b>{gapUpList.length}</b> activos de STOCKS con OPEN GAP UP institucional. Reciben <b>Score Boost (+25 pts)</b>, prioridad 0 en la cola de compra del BOT y Escudo Defensivo ADUANA (SL 15m EMA9, Trailing Stop Midpoint 1H, TP parcial Upper 5 / Upper 6).
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button
              onClick={() => setActiveTab('GAP_UP')}
              style={{
                background: activeTab === 'GAP_UP' ? '#22C55E' : 'rgba(255,255,255,0.08)',
                color: activeTab === 'GAP_UP' ? '#000' : '#FFF',
                border: '1px solid rgba(34,197,94,0.5)',
                padding: '8px 14px',
                borderRadius: 8,
                fontSize: 11,
                fontWeight: 900,
                cursor: 'pointer',
              }}
            >
              VER {gapUpList.length} RUNNERS 🚀
            </button>
          </div>
        </div>
      )}

      {/* APEX Priority Queue Panel */}
      <PriorityQueuePanel 
        queue={activeTab === 'TOP3' ? (top3List.length > 0 ? top3List : priorityQueue.filter((p: any) => p.status !== 'blocked' && p.queue_status !== 'blocked')) : (activeTab === 'GAP_UP' ? gapUpList : (activeTab === 'QUEUE' ? queueList : priorityQueue.filter((p: any) => p.status !== 'blocked' && p.queue_status !== 'blocked')))} 
        capital={pqCapital} 
        summary={pqSummary} 
        activeTab={activeTab} 
        activeLimit={settings.activeStocksLimit || 3} 
      />

      <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)', overflow: 'hidden' }}>
        <style jsx>{`
          .scanner-row:hover {
            background: rgba(34, 197, 94, 0.05) !important;
            transform: translateX(4px);
          }
        `}</style>
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: '70px 105px 110px 100px 125px 150px 1fr 105px 90px 55px', 
          padding: '14px 16px', 
          borderBottom: '1px solid rgba(255,255,255,0.08)', 
          fontSize: '10px', 
          fontWeight: 900, 
          color: '#555', 
          textTransform: 'uppercase', 
          letterSpacing: '0.12em', 
          alignItems: 'center',
          background: 'rgba(0,0,0,0.2)'
        }}>
          <RankingHeaderTooltip />
          <span>Ticker</span>
          <span>Precio / Var</span>
          <span>Vol / RVOL</span>
          <span style={{textAlign:'center'}}>Fuerza 5m</span>
          <span style={{textAlign:'center'}}>Semáforo</span>
          <span>Noticias / Catalizador</span>
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
                onOpenNews={(stockToOpen: any) => setNewsStock(stockToOpen)}
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
      {newsStock && <NewsModal stock={newsStock} onClose={() => setNewsStock(null)} defaultTranslate={settings.translateNews} defaultLang={settings.language} />}
      <Link href="/stocks/universe" style={{ display: 'inline-block', marginTop: '20px', color: '#22C55E', textDecoration: 'none', fontWeight: 800, fontSize: '11px' }}>← VOLVER AL UNIVERSE BUILDER</Link>
    </div>
  )
}
