'use client'
import { useEffect, useState, useRef, useCallback } from 'react'
import { supabase } from '@/lib/supabase'
import TradeMarkerChart, { TradeEvent } from '@/components/TradeMarkerChart'

const TIMEFRAMES = ['15m', '30m', '1h', '4h', '1d', '1w']

// Stablecoins to exclude
const EXCLUDED_SYMBOLS = [
  'FDUSD/USDT', 'USDC/USDT', 'BUSD/USDT', 'TUSD/USDT',
  'USDP/USDT', 'DAI/USDT', 'USDD/USDT', 'EURC/USDT', 'PAXG/USDT',
]

interface Candle {
  open_time: string
  open: string | number
  high: string | number
  low: string | number
  close: string | number
  volume: string | number
}

interface Indicator {
  timestamp: string
  ema_3: number | null
  ema_9: number | null
  ema_20: number | null
  ema_50: number | null
  ema_200: number | null
  rsi_14: number | null
  macd_line: number | null
  macd_signal: number | null
  macd_histogram: number | null
  bb_upper: number | null
  bb_middle: number | null
  bb_lower: number | null
  atr_14: number | null
  adx_14: number | null
  di_plus: number | null
  di_minus: number | null
  vwap: number | null
  stoch_k: number | null
  stoch_d: number | null
  williams_r: number | null
  volume_sma_20: number | null
  [key: string]: any
}

export default function MarketPage() {
  const [symbols, setSymbols] = useState<any[]>([])
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)
  const [selectedTf, setSelectedTf] = useState('15m')
  const [indicators, setIndicators] = useState<Indicator | null>(null)
  const [loading, setLoading] = useState(false)
  const [candles, setCandles] = useState<any[]>([])
  const [trades, setTrades] = useState<TradeEvent[]>([])

  useEffect(() => {
    loadSymbols()
  }, [])

  useEffect(() => {
    if (selectedSymbol) {
      loadIndicators(selectedSymbol, selectedTf)
      loadChart(selectedSymbol, selectedTf)
    }
  }, [selectedSymbol, selectedTf])


  async function loadSymbols() {
    const { data } = await supabase
      .from('market_candles')
      .select('symbol, timeframe, volume, quote_volume, close, open_time')
      .eq('timeframe', '15m')
      .order('open_time', { ascending: false })
      .limit(500)

    if (!data) return

    // Group by symbol, take latest candle, exclude stablecoins
    const map = new Map<string, any>()
    data.forEach((c: any) => {
      if (!map.has(c.symbol) && !EXCLUDED_SYMBOLS.includes(c.symbol)) {
        map.set(c.symbol, c)
      }
    })

    const list = Array.from(map.values()).sort((a, b) =>
      parseFloat(b.quote_volume || '0') - parseFloat(a.quote_volume || '0')
    )
    setSymbols(list)
    if (list.length > 0 && !selectedSymbol) setSelectedSymbol(list[0].symbol)
  }

  async function loadIndicators(symbol: string, tf: string) {
    const { data } = await supabase
      .from('technical_indicators')
      .select('*')
      .eq('symbol', symbol)
      .eq('timeframe', tf)
      .order('timestamp', { ascending: false })
      .limit(1)

    if (data && data.length > 0) setIndicators(data[0])
    else setIndicators(null)
  }

  async function loadChart(symbol: string, tf: string) {
    setLoading(true)
    try {
      const [cRes, tRes] = await Promise.all([
        supabase
          .from('market_candles')
          .select('*')
          .eq('symbol', symbol)
          .eq('timeframe', tf)
          .order('open_time', { ascending: false })
          .limit(200),
        fetch(`/api/v1/market/trade-events/${symbol}?days=7`)
      ])
      
      if (cRes.data) {
        setCandles(cRes.data.reverse())
      }
      if (tRes.ok) {
        setTrades(await tRes.json())
      }
    } catch (err) {
      console.error('Chart error:', err)
    } finally {
      setLoading(false)
    }
  }

  const fmt = (v: any, dp = 2) => v != null ? parseFloat(v).toFixed(dp) : '—'
  const fmtPrice = (v: any) => v != null ? parseFloat(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 8 }) : '—'

  // EMA color: green if price > EMA, red if price < EMA
  const emaColor = (emaVal: number | null) => {
    if (emaVal == null || !indicators) return 'inherit'
    const close = parseFloat(String(indicators.close || indicators.ema_3 || 0))
    if (close === 0 || emaVal === 0) return 'inherit'
    return close > emaVal ? 'var(--accent-green)' : 'var(--accent-red)'
  }

  // RSI color
  const rsiColor = (val: number | null) => {
    if (val == null) return 'var(--text-muted)'
    if (val > 70) return 'var(--accent-red)'
    if (val < 30) return 'var(--accent-green)'
    return 'var(--text-muted)'
  }

  const rsiLabel = (val: number | null) => {
    if (val == null) return ''
    if (val > 70) return 'Overbought'
    if (val < 30) return 'Oversold'
    return 'Neutral'
  }

  return (
    <div>
      <div className="page-header">
        <h1>Market Overview</h1>
        <p>Active symbols with technical indicators, volume analysis and price charts</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 24 }}>
        {/* Symbol List */}
        <div className="card" style={{ maxHeight: 800, overflowY: 'auto', padding: 16 }}>
          <div className="card-title" style={{ marginBottom: 12, padding: '0 4px' }}>
            Active Symbols ({symbols.length})
          </div>
          {symbols.map(s => (
            <div
              key={s.symbol}
              onClick={() => setSelectedSymbol(s.symbol)}
              style={{
                padding: '10px 12px',
                borderRadius: 10,
                cursor: 'pointer',
                background: selectedSymbol === s.symbol
                  ? 'var(--accent-blue-glow)' : 'transparent',
                borderLeft: selectedSymbol === s.symbol
                  ? '3px solid var(--accent-blue)' : '3px solid transparent',
                marginBottom: 4,
                transition: 'all 0.2s ease',
              }}
            >
              <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>{s.symbol}</div>
              <div style={{
                fontSize: '0.75rem', color: 'var(--text-muted)',
                display: 'flex', justifyContent: 'space-between', marginTop: 2,
              }}>
                <span>${fmtPrice(s.close)}</span>
                <span>Vol: {parseFloat(s.volume).toLocaleString('en-US', { maximumFractionDigits: 0 })}</span>
              </div>
            </div>
          ))}
          {symbols.length === 0 && (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', padding: 8 }}>
              No market data yet. Run the worker to fetch data.
            </p>
          )}
        </div>

        {/* Right Panel */}
        <div>
          {selectedSymbol && (
            <>
              {/* Timeframe Selector */}
              <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                {TIMEFRAMES.map(tf => (
                  <button
                    key={tf}
                    onClick={() => setSelectedTf(tf)}
                    className={selectedTf === tf ? 'btn btn-primary' : 'btn btn-ghost'}
                    style={{
                      padding: '6px 16px',
                      fontSize: '0.8rem',
                      borderRadius: 8,
                      minWidth: 50,
                    }}
                  >
                    {tf}
                  </button>
                ))}
              </div>

              {/* Technical Indicators Panel */}
              <div className="card" style={{ marginBottom: 20 }}>
                <div className="card-header">
                  <span className="card-title">{selectedSymbol} — Technical Indicators ({selectedTf})</span>
                </div>
                {indicators ? (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 20 }}>
                    {/* EMAs */}
                    <div>
                      <h4 style={{
                        fontSize: '0.75rem', color: 'var(--accent-blue)',
                        marginBottom: 10, fontWeight: 700, textTransform: 'uppercase',
                        letterSpacing: '0.5px',
                      }}>Moving Averages</h4>
                      <div style={{ fontSize: '0.8rem', lineHeight: 2.2 }}>
                        {(['ema_3', 'ema_9', 'ema_20', 'ema_50', 'ema_200'] as const).map(ema => (
                          <div key={ema} style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: 'var(--text-muted)' }}>
                              {ema.replace('ema_', 'EMA ')}
                            </span>
                            <strong style={{ color: emaColor(indicators[ema] as number) }}>
                              {fmtPrice(indicators[ema])}
                            </strong>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Momentum / Oscillators */}
                    <div>
                      <h4 style={{
                        fontSize: '0.75rem', color: 'var(--accent-purple)',
                        marginBottom: 10, fontWeight: 700, textTransform: 'uppercase',
                        letterSpacing: '0.5px',
                      }}>Momentum</h4>
                      <div style={{ fontSize: '0.8rem', lineHeight: 1.6 }}>
                        {/* RSI with progress bar */}
                        <div style={{ marginBottom: 8 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                            <span style={{ color: 'var(--text-muted)' }}>RSI 14</span>
                            <strong style={{ color: rsiColor(indicators.rsi_14) }}>
                              {fmt(indicators.rsi_14)} <span style={{ fontSize: '0.65rem', fontWeight: 400 }}>
                                {rsiLabel(indicators.rsi_14)}
                              </span>
                            </strong>
                          </div>
                          <div style={{
                            height: 6, borderRadius: 3, background: 'rgba(42, 48, 64, 0.5)',
                            overflow: 'hidden',
                          }}>
                            <div style={{
                              height: '100%', borderRadius: 3,
                              width: `${Math.min(100, Math.max(0, indicators.rsi_14 || 0))}%`,
                              background: rsiColor(indicators.rsi_14),
                              transition: 'width 0.5s ease',
                            }} />
                          </div>
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'space-between', lineHeight: 2.2 }}>
                          <span style={{ color: 'var(--text-muted)' }}>MACD</span>
                          <strong>{fmtPrice(indicators.macd_line)}</strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', lineHeight: 2.2 }}>
                          <span style={{ color: 'var(--text-muted)' }}>Signal</span>
                          <strong>{fmtPrice(indicators.macd_signal)}</strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', lineHeight: 2.2 }}>
                          <span style={{ color: 'var(--text-muted)' }}>Histogram</span>
                          <strong style={{
                            color: indicators.macd_histogram && parseFloat(String(indicators.macd_histogram)) > 0
                              ? 'var(--accent-green)' : 'var(--accent-red)',
                          }}>
                            {fmtPrice(indicators.macd_histogram)}
                          </strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', lineHeight: 2.2 }}>
                          <span style={{ color: 'var(--text-muted)' }}>Stoch %K / %D</span>
                          <strong>{fmt(indicators.stoch_k)} / {fmt(indicators.stoch_d)}</strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', lineHeight: 2.2 }}>
                          <span style={{ color: 'var(--text-muted)' }}>Williams %R</span>
                          <strong>{fmt(indicators.williams_r)}</strong>
                        </div>
                      </div>
                    </div>

                    {/* Volatility */}
                    <div>
                      <h4 style={{
                        fontSize: '0.75rem', color: 'var(--accent-yellow)',
                        marginBottom: 10, fontWeight: 700, textTransform: 'uppercase',
                        letterSpacing: '0.5px',
                      }}>Volatility</h4>
                      <div style={{ fontSize: '0.8rem', lineHeight: 2.2 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--text-muted)' }}>ATR 14</span>
                          <strong>{fmtPrice(indicators.atr_14)}</strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--text-muted)' }}>BB Upper</span>
                          <strong>{fmtPrice(indicators.bb_upper)}</strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--text-muted)' }}>BB Middle</span>
                          <strong>{fmtPrice(indicators.bb_middle)}</strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--text-muted)' }}>BB Lower</span>
                          <strong>{fmtPrice(indicators.bb_lower)}</strong>
                        </div>
                      </div>
                    </div>

                    {/* Trend & Volume */}
                    <div>
                      <h4 style={{
                        fontSize: '0.75rem', color: 'var(--accent-green)',
                        marginBottom: 10, fontWeight: 700, textTransform: 'uppercase',
                        letterSpacing: '0.5px',
                      }}>Trend & Volume</h4>
                      <div style={{ fontSize: '0.8rem', lineHeight: 2.2 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--text-muted)' }}>ADX</span>
                          <strong style={{
                            color: indicators.adx_14 && parseFloat(String(indicators.adx_14)) > 20
                              ? 'var(--accent-green)' : 'var(--text-muted)',
                          }}>
                            {fmt(indicators.adx_14)}
                            <span style={{ fontSize: '0.65rem', fontWeight: 400, marginLeft: 4 }}>
                              {indicators.adx_14 && parseFloat(String(indicators.adx_14)) > 25 ? 'Strong' : 'Weak'}
                            </span>
                          </strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--text-muted)' }}>+DI</span>
                          <strong style={{ color: 'var(--accent-green)' }}>{fmt(indicators.di_plus)}</strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--text-muted)' }}>-DI</span>
                          <strong style={{ color: 'var(--accent-red)' }}>{fmt(indicators.di_minus)}</strong>
                        </div>
                        {indicators.vwap && (
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: 'var(--text-muted)' }}>VWAP</span>
                            <strong>{fmtPrice(indicators.vwap)}</strong>
                          </div>
                        )}
                        <div style={{
                          display: 'flex', justifyContent: 'space-between',
                          borderTop: '1px solid var(--border-color)',
                          paddingTop: 8, marginTop: 4,
                        }}>
                          <span style={{ color: 'var(--text-muted)' }}>Vol SMA20</span>
                          <strong style={{ color: 'var(--accent-blue)' }}>
                            {indicators.volume_sma_20
                              ? parseFloat(String(indicators.volume_sma_20)).toLocaleString('en-US', { maximumFractionDigits: 0 })
                              : '—'}
                          </strong>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <p style={{ color: 'var(--text-muted)' }}>
                    No indicator data available for {selectedTf}. Run the worker to calculate.
                  </p>
                )}
              </div>

              {/* Price Chart */}
              <div className="card">
                <div className="card-header" style={{ marginBottom: 12 }}>
                  <span className="card-title">
                    {selectedSymbol} — Price Chart ({selectedTf})
                  </span>
                  <div style={{ display: 'flex', gap: 12, alignItems: 'center', fontSize: '0.7rem' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <span style={{ width: 12, height: 2, background: '#ffffff', display: 'inline-block' }} /> EMA 3
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <span style={{ width: 12, height: 2, background: '#00BCD4', display: 'inline-block' }} /> EMA 9
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <span style={{ width: 12, height: 2, background: '#FFC107', display: 'inline-block' }} /> EMA 20
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <span style={{ width: 12, height: 2, background: '#FF9800', display: 'inline-block' }} /> EMA 50
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <span style={{ width: 12, height: 2, background: '#F44336', display: 'inline-block' }} /> EMA 200
                    </span>
                  </div>
                </div>
                <div
                  style={{
                    width: '100%',
                    height: 420,
                    borderRadius: 12,
                    overflow: 'hidden',
                    background: '#0F172A',
                    border: '1px solid var(--border-color)',
                    position: 'relative',
                  }}
                >
                  {loading ? (
                    <div style={{
                      position: 'absolute', inset: 0,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: 'rgba(15, 23, 42, 0.8)', zIndex: 10,
                    }}>
                      <span style={{ color: 'var(--accent-blue)', fontSize: '0.9rem' }}>
                        Loading chart...
                      </span>
                    </div>
                  ) : (
                    <TradeMarkerChart 
                      symbol={selectedSymbol}
                      timeframe={selectedTf}
                      candles={candles}
                      trades={trades}
                      height={420}
                    />
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
