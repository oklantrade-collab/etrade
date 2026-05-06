'use client'
import { useEffect, useRef, useState } from 'react'
import { createChart, CandlestickSeries, LineSeries, LineStyle, IChartApi, ISeriesApi, createSeriesMarkers } from 'lightweight-charts'
// Note: lightweight-charts v5 uses createSeriesMarkers instead of series.setMarkers()

export interface TradeEvent {
  type: 'entry' | 'tp_partial' | 'tp_full' | 'sl' | 'blocked'
  direction: 'long' | 'short'
  timestamp: number
  price: number
  rule_code: string
  blocked_reasonText?: string | null
}

interface TradeMarkerChartProps {
  symbol: string
  timeframe: string
  candles: any[]
  trades: TradeEvent[]
  height?: number
  showEMAs?: boolean
  showBasis?: boolean
  activePosition?: {
    avg_entry: number
    sl_price: number
    tp_partial: number
    tp_full: number
  } | null
  basis?: number | null
  upper_6?: number | null
  lower_6?: number | null
  precision?: number
  minMove?: number
}

export default function TradeMarkerChart({
  symbol,
  timeframe,
  candles,
  trades,
  height = 400,
  showEMAs = true,
  showBasis = true,
  activePosition = null,
  basis = null,
  upper_6 = null,
  lower_6 = null,
  precision = 2,
  minMove = 0.01
}: TradeMarkerChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const priceLinesRef = useRef<any[]>([])
  const indicatorLinesRef = useRef<any[]>([])
  const [showRealTrades, setShowRealTrades] = useState(false)
  const [hasFitInitial, setHasFitInitial] = useState(false)

  useEffect(() => {
    if (!chartContainerRef.current) return

    // Create chart
    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: height,
      layout: {
        background: { color: 'transparent' },
        textColor: '#94a3b8',
        fontSize: 11,
      },
      localization: {
        locale: 'es-PE',
        timeFormatter: (time: number) => {
          const date = new Date(time * 1000)
          return date.toLocaleString('es-PE', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false,
            timeZone: 'America/Lima'
          })
        }
      },
      grid: {
        vertLines: { color: 'rgba(30, 41, 59, 0.5)' },
        horzLines: { color: 'rgba(30, 41, 59, 0.5)' },
      },
      crosshair: {
        mode: 0,
        vertLine: { labelBackgroundColor: '#1e293b' },
        horzLine: { labelBackgroundColor: '#1e293b' },
      },
      timeScale: {
        borderColor: 'rgba(255, 255, 255, 0.05)',
        timeVisible: true,
      },
      rightPriceScale: {
        borderColor: 'rgba(255, 255, 255, 0.05)',
        autoScale: true,
      },
    })

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#00C896',
      downColor: '#FF4757',
      borderUpColor: '#00C896',
      borderDownColor: '#FF4757',
      wickUpColor: '#00C896',
      wickDownColor: '#FF4757',
      priceFormat: {
        type: 'price',
        precision: precision,
        minMove: minMove,
      },
    })
    const sarSeries = chart.addSeries(LineSeries, {
      lineVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    })

    const basisSeries = chart.addSeries(LineSeries, {
      color: '#9B59B6',
      lineWidth: 1,
      lineStyle: LineStyle.Solid,
      lastValueVisible: true, // Axis label
      priceLineVisible: false,
      title: 'BASIS',
    })

    const upper6Series = chart.addSeries(LineSeries, {
      color: '#00C896',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      lastValueVisible: true, // Axis label
      priceLineVisible: false,
      title: 'U6',
    })

    const lower6Series = chart.addSeries(LineSeries, {
      color: '#FF4757',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      lastValueVisible: true, // Axis label
      priceLineVisible: false,
      title: 'L6',
    })
    
    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    ;(chartRef.current as any).sarSeries = sarSeries
    ;(chartRef.current as any).basisSeries = basisSeries
    ;(chartRef.current as any).upper6Series = upper6Series
    ;(chartRef.current as any).lower6Series = lower6Series

    // Reset initial fit when symbol or timeframe changes
    setHasFitInitial(false)

    // Cleanup
    return () => {
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
    }
  }, [height, symbol, timeframe])

  useEffect(() => {
    if (!candleSeriesRef.current) return

    if (!candles || candles.length === 0) {
        candleSeriesRef.current.setData([])
        if ((chartRef.current as any).sarSeries) (chartRef.current as any).sarSeries.setData([])
        if ((chartRef.current as any).basisSeries) (chartRef.current as any).basisSeries.setData([])
        if ((chartRef.current as any).upper6Series) (chartRef.current as any).upper6Series.setData([])
        if ((chartRef.current as any).lower6Series) (chartRef.current as any).lower6Series.setData([])
        
        // Clear old PriceLines
        priceLinesRef.current.forEach(l => candleSeriesRef.current?.removePriceLine(l))
        priceLinesRef.current = []
        return
    }

    // Format and set candle data
    const formattedCandles = candles
      .map(c => {
        const t = Math.floor(new Date(c.open_time || c.timestamp).getTime() / 1000)
        return {
          time: t as any,
          open:  parseFloat(c.open || 0),
          high:  parseFloat(c.high || 0),
          low:   parseFloat(c.low || 0),
          close: parseFloat(c.close || 0)
        }
      })
      .filter(c => !isNaN(c.time) && !isNaN(c.close))
      .sort((a, b) => a.time - b.time)

    // Remove duplicates
    const uniqueCandles = Array.from(new Map(formattedCandles.map(c => [c.time, c])).values())
    if (candleSeriesRef.current && uniqueCandles.length > 0) {
      candleSeriesRef.current.setData(uniqueCandles)
    }

    // --- INDICATORS ---
    const sarSeries = (chartRef.current as any)?.sarSeries
    if (sarSeries) {
      const sarData = candles
        .map(c => {
          const t = Math.floor(new Date(c.open_time || c.timestamp).getTime() / 1000)
          return {
            time: t as any,
            value: parseFloat(c.sar || 0),
            trend: parseInt(c.sar_trend || 0)
          }
        })
        .filter(p => !isNaN(p.time) && p.value > 0)
        .sort((a, b) => a.time - b.time)
      
      const uniqueSar = Array.from(new Map(sarData.map(c => [c.time, c])).values())
      sarSeries.setData(uniqueSar.map(p => ({ time: p.time, value: p.value })))
      
      const sarMarkers = uniqueSar.map(p => ({
        time:     p.time,
        position: p.trend > 0 ? 'belowBar' : ('aboveBar' as any),
        color:    p.trend > 0 ? '#26a69a' : '#ef5350',
        shape:    'circle' as any,
        size:     1
      }))
      
      try {
          if (!(chartRef.current as any).sarMarkersPlugin) {
            (chartRef.current as any).sarMarkersPlugin = createSeriesMarkers(sarSeries, sarMarkers)
          } else {
            (chartRef.current as any).sarMarkersPlugin.setMarkers(sarMarkers)
          }
      } catch (e) { console.error("SAR Markers error", e) }
    }

    const basisSeries = (chartRef.current as any)?.basisSeries
    const upper6Series = (chartRef.current as any)?.upper6Series
    const lower6Series = (chartRef.current as any)?.lower6Series

    if (basisSeries && showBasis) {
        const d = candles
          .map(c => ({
            time: Math.floor(new Date(c.open_time || c.timestamp).getTime() / 1000) as any,
            value: parseFloat(c.basis || 0)
          }))
          .filter(p => !isNaN(p.time) && p.value > 0)
          .sort((a, b) => a.time - b.time)
        basisSeries.setData(d)
    }
    if (upper6Series) {
        const d = candles
          .map(c => ({
            time: Math.floor(new Date(c.open_time || c.timestamp).getTime() / 1000) as any,
            value: parseFloat(c.upper_6 || 0)
          }))
          .filter(p => !isNaN(p.time) && p.value > 0)
          .sort((a, b) => a.time - b.time)
        upper6Series.setData(d)
    }
    if (lower6Series) {
        const d = candles
          .map(c => ({
            time: Math.floor(new Date(c.open_time || c.timestamp).getTime() / 1000) as any,
            value: parseFloat(c.lower_6 || 0)
          }))
          .filter(p => !isNaN(p.time) && p.value > 0)
          .sort((a, b) => a.time - b.time)
        lower6Series.setData(d)
    }

    // --- TRADE MARKERS ---
    const markers = trades
      .filter(t => t.type === 'entry' && showRealTrades)
      .map(t => {
        const isLong = t.direction === 'long'
        let tradeTime = typeof t.timestamp === 'string' ? new Date(t.timestamp).getTime() / 1000 : t.timestamp
        if (tradeTime > 10000000000) tradeTime = tradeTime / 1000
        
        const candleTime = uniqueCandles.find(c => (c.time as any) <= tradeTime && ((c.time as any) + (15 * 60)) > tradeTime)?.time || tradeTime

        return {
          time:     candleTime as any,
          position: isLong ? 'belowBar' : ('aboveBar' as any),
          color:    isLong ? '#00FF00' : '#FFA500', 
          shape:    'text' as any,
          text:     isLong ? 'BUY' : 'SELL',
          size:     1
        }
      })

    const pineMarkers = candles
      .filter(c => c.pinescript_signal === 'Buy' || c.pinescript_signal === 'Sell')
      .map(c => ({
        time:     Math.floor(new Date(c.open_time).getTime() / 1000) as any,
        position: c.pinescript_signal === 'Buy' ? 'belowBar' : ('aboveBar' as any),
        color:    c.pinescript_signal === 'Buy' ? '#00C896' : '#FF4757',
        shape:    'text' as any,
        text:     c.pinescript_signal === 'Buy' ? 'B' : 'S',
        size:     2,
      }))

    const allMarkers = [...markers, ...pineMarkers].sort((a, b) => a.time - b.time)

    if (candleSeriesRef.current && allMarkers.length > 0) {
      try {
          if (!(chartRef.current as any).tradeMarkersPlugin) {
            (chartRef.current as any).tradeMarkersPlugin = createSeriesMarkers(candleSeriesRef.current, allMarkers)
          } else {
            (chartRef.current as any).tradeMarkersPlugin.setMarkers(allMarkers)
          }
      } catch (e) { console.error("Trade Markers error", e) }
    }

    // --- PRICE LINES ---
    priceLinesRef.current.forEach(l => candleSeriesRef.current?.removePriceLine(l))
    priceLinesRef.current = []

    if (activePosition && candleSeriesRef.current) {
      const entryPrice = activePosition.avg_entry || activePosition.entry_price || 0;
      const slPrice = activePosition.sl_price || 0;
      const tp1Price = activePosition.tp_partial || activePosition.tp_partial_price || activePosition.tp_block1_price || 0;
      const tp2Price = activePosition.tp_full || activePosition.tp_full_price || activePosition.tp_block2_price || 0;
      const tp3Price = activePosition.tp_3 || activePosition.tp_3_price || activePosition.tp_block3_price || 0;

      const lines = [
        entryPrice > 0 ? { price: entryPrice, color: '#00C896', title: `Entry $${entryPrice.toLocaleString()}` } : null,
        slPrice > 0 ? { price: slPrice, color: '#FF4757', title: `SL $${slPrice.toLocaleString()}` } : null,
        tp1Price > 0 ? { price: tp1Price, color: '#FFD700', title: `TP1 $${tp1Price.toLocaleString()}` } : null,
        tp2Price > 0 ? { price: tp2Price, color: '#ffffff', title: `TP2 $${tp2Price.toLocaleString()}` } : null,
        tp3Price > 0 ? { price: tp3Price, color: '#38BDF8', title: `TP3 $${tp3Price.toLocaleString()}` } : null,
      ].filter(l => l !== null);

      lines.forEach((l: any) => {
          const pl = candleSeriesRef.current?.createPriceLine({
            price: l.price,
            color: l.color,
            lineWidth: 1,
            lineStyle: (LineStyle as any).Dashed || 2,
            axisLabelVisible: true,
            title: l.title,
          })
          if (pl) priceLinesRef.current.push(pl)
      })
    }

    if (!hasFitInitial && uniqueCandles.length > 0) {
      setTimeout(() => {
        chartRef.current?.timeScale().fitContent()
        setHasFitInitial(true)
      }, 100)
    }
  }, [candles, trades, activePosition, showRealTrades, symbol, timeframe]);

  // Chart creation logic including localization:
  // (Assuming chart object creation here)
  /*
      localization: {
        locale: 'es-PE',
        timeFormatter: (time: number) => {
          const date = new Date(time * 1000)
          return date.toLocaleString('es-PE', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false,
            timeZone: 'America/Lima'
          })
        }
      },
  */

  return (
    <div className="relative w-full h-full">
      <div style={{
        position:   'absolute',
        bottom:     '40px',
        left:       '12px',
        background: 'rgba(15, 23, 42, 0.9)',
        padding:    '8px 16px',
        borderRadius: '8px',
        fontSize:   '12px',
        color:      '#cbd5e1',
        zIndex:     10,
        pointerEvents: 'none',
        display: 'flex',
        gap: '20px',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
        backdropFilter: 'blur(8px)'
      }}>
        <div className="flex gap-6 items-center">
          <label className="flex items-center gap-2 cursor-pointer hover:text-white transition-colors pointer-events-auto">
            <input 
              type="checkbox" 
              checked={showRealTrades} 
              onChange={e => setShowRealTrades(e.target.checked)}
              className="w-4 h-4 rounded border-white/20 bg-black/40 accent-[#00FF00]"
            />
            <span style={{ fontSize: '12px', fontWeight: 900, letterSpacing: '0.5px', color: '#fff' }}>MIS TRADES (SIPV)</span>
          </label>
        </div>
        <div className="flex gap-4 border-l border-white/10 pl-4">
          <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-[#00FF00]" /> BUY</span>
          <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-[#FFA500]" /> SELL</span>
        </div>
        <div className="flex gap-4 border-l border-white/10 pl-4">
          <span className="flex items-center gap-1.5 text-[#00C896] font-bold">B (PINE)</span>
          <span className="flex items-center gap-1.5 text-[#FF4757] font-bold">S (PINE)</span>
          <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-[#ef5350]" /> SAR</span>
          <span className="flex items-center gap-1.5 font-bold text-[#00C896]">U6</span>
          <span className="flex items-center gap-1.5 font-bold text-[#FF4757]">L6</span>
        </div>
      </div>
      <div ref={chartContainerRef} className="w-full h-full" />
    </div>
  )
}
