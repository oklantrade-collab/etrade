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
  lower_6 = null
}: TradeMarkerChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const priceLinesRef = useRef<any[]>([])
  const [showRealTrades, setShowRealTrades] = useState(false)

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
            hour12: false
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
      lastValueVisible: true,
      priceLineVisible: false,
      title: 'BASIS',
    })

    const upper6Series = chart.addSeries(LineSeries, {
      color: '#00C896',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      lastValueVisible: true,
      priceLineVisible: false,
      title: 'U6',
    })

    const lower6Series = chart.addSeries(LineSeries, {
      color: '#FF4757',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      lastValueVisible: true,
      priceLineVisible: false,
      title: 'L6',
    })
    
    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    ;(chartRef.current as any).sarSeries = sarSeries
    ;(chartRef.current as any).basisSeries = basisSeries
    ;(chartRef.current as any).upper6Series = upper6Series
    ;(chartRef.current as any).lower6Series = lower6Series

    // Cleanup
    return () => {
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
    }
  }, [height])

  useEffect(() => {
    if (!candleSeriesRef.current || !candles.length) return

    // Format and set candle data
    const formattedCandles = candles.map(c => ({
      time: Math.floor(new Date(c.open_time || c.timestamp).getTime() / 1000) as any,
      open: parseFloat(c.open),
      high: parseFloat(c.high),
      low: parseFloat(c.low),
      close: parseFloat(c.close)
    })).sort((a, b) => a.time - b.time)

    // Remove duplicates
    const uniqueCandles = Array.from(new Map(formattedCandles.map(c => [c.time, c])).values())
    if (candleSeriesRef.current) {
      candleSeriesRef.current.setData(uniqueCandles)
    }

    // Set SAR data via markers for dots (TradingView style)
    const sarSeries = (chartRef.current as any)?.sarSeries
    if (sarSeries) {
      const sarData = candles
        .filter(c => c.sar > 0)
        .map(c => ({
          time: Math.floor(new Date(c.open_time || c.timestamp).getTime() / 1000) as any,
          value: parseFloat(c.sar),
          trend: parseInt(c.sar_trend)
        })).sort((a, b) => a.time - b.time)
      
      const uniqueSar = Array.from(new Map(sarData.map(c => [c.time, c])).values())
      sarSeries.setData(uniqueSar)
      
      const sarMarkers = uniqueSar.map(p => ({
        time:     p.time,
        position: p.trend > 0 ? 'belowBar' : ('aboveBar' as any),
        color:    p.trend > 0 ? '#26a69a' : '#ef5350',
        shape:    'circle' as any,
        size:     1
      }))
      if (!(chartRef.current as any).sarMarkersPlugin) {
        (chartRef.current as any).sarMarkersPlugin = createSeriesMarkers(sarSeries, sarMarkers)
      } else {
        (chartRef.current as any).sarMarkersPlugin.setMarkers(sarMarkers)
      }
    }

    // --- POPULATE FIBONACCI BANDS PER CANDLE ---
    const basisSeries = (chartRef.current as any)?.basisSeries
    if (basisSeries && showBasis) {
      const basisData = candles
        .filter(c => c.basis != null && c.basis > 0)
        .map(c => ({
          time: Math.floor(new Date(c.open_time || c.timestamp).getTime() / 1000) as any,
          value: parseFloat(c.basis)
        })).sort((a, b) => a.time - b.time)
      basisSeries.setData(basisData)
    }

    const upper6Series = (chartRef.current as any)?.upper6Series
    if (upper6Series) {
      const u6Data = candles
        .filter(c => c.upper_6 != null && c.upper_6 > 0)
        .map(c => ({
          time: Math.floor(new Date(c.open_time || c.timestamp).getTime() / 1000) as any,
          value: parseFloat(c.upper_6)
        })).sort((a, b) => a.time - b.time)
      upper6Series.setData(u6Data)
    }

    const lower6Series = (chartRef.current as any)?.lower6Series
    if (lower6Series) {
      const l6Data = candles
        .filter(c => c.lower_6 != null && c.lower_6 > 0)
        .map(c => ({
          time: Math.floor(new Date(c.open_time || c.timestamp).getTime() / 1000) as any,
          value: parseFloat(c.lower_6)
        })).sort((a, b) => a.time - b.time)
      lower6Series.setData(l6Data)
    }

    // Add Markers
    const markers = trades
      .filter(t => t.type === 'entry' && showRealTrades) // Apply filter based on toggle
      .map(t => {
        const isLong = t.direction === 'long'
        return {
          time: t.timestamp as any,
          position: isLong ? 'belowBar' : ('aboveBar' as any),
          color: isLong ? '#00FF00' : '#FFA500', // Lime for Buy, Orange for Sell
          shape: 'text' as any,
          text: isLong ? 'BUY' : 'SELL',
          size: 1
        }
      })

    // --- ADD PINESCRIPT MARKERS (B/S) ---
    const pineMarkers = candles
      .filter(c => c.pinescript_signal === 'Buy' || c.pinescript_signal === 'Sell')
      .map(c => ({
        time: Math.floor(new Date(c.open_time).getTime() / 1000) as any,
        position: c.pinescript_signal === 'Buy' ? 'belowBar' : ('aboveBar' as any),
        color: c.pinescript_signal === 'Buy' ? '#00C896' : '#FF4757',
        shape: 'text' as any,
        text: c.pinescript_signal === 'Buy' ? 'B' : 'S',
        size: 1
      }))

    const allMarkers = [...markers, ...pineMarkers].sort((a, b) => a.time - b.time)

    if (candleSeriesRef.current) {
      if (!(chartRef.current as any).tradeMarkersPlugin) {
        (chartRef.current as any).tradeMarkersPlugin = createSeriesMarkers(candleSeriesRef.current, allMarkers)
      } else {
        (chartRef.current as any).tradeMarkersPlugin.setMarkers(allMarkers)
      }
    }

    // Add Price Lines for active position
    // Clear old lines
    priceLinesRef.current.forEach(l => candleSeriesRef.current?.removePriceLine(l))
    priceLinesRef.current = []

    if (activePosition) {
      const lines = [
        { price: activePosition.avg_entry, color: '#00C896', title: `Entry $${activePosition.avg_entry.toLocaleString()}` },
        { price: activePosition.sl_price, color: '#FF4757', title: `SL $${activePosition.sl_price.toLocaleString()}` },
        { price: activePosition.tp_partial, color: '#FFD700', title: `TP1 $${activePosition.tp_partial.toLocaleString()}` },
        { price: activePosition.tp_full, color: '#ffffff', title: `TP2 $${activePosition.tp_full.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 3 })}` },
      ]

      lines.forEach(l => {
        if (l.price > 0) {
          const pl = candleSeriesRef.current?.createPriceLine({
            price: l.price,
            color: l.color,
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: l.title,
          })
          if (pl) priceLinesRef.current.push(pl)
        }
      })
    }

    chartRef.current?.timeScale().fitContent()
  }, [candles, trades, activePosition, basis, showBasis, upper_6, lower_6, showRealTrades])

  return (
    <div className="relative w-full h-full">
      <div style={{
        position:   'absolute',
        top:        '8px',
        left:       '8px',
        background: 'rgba(0,0,0,0.6)',
        padding:    '4px 8px',
        borderRadius: '4px',
        fontSize:   '10px',
        color:      '#888',
        zIndex:     10,
        pointerEvents: 'none',
        display: 'flex',
        gap: '12px'
      }}>
        <div className="flex gap-4 items-center">
          <label className="flex items-center gap-1.5 cursor-pointer hover:text-white transition-colors pointer-events-auto">
            <input 
              type="checkbox" 
              checked={showRealTrades} 
              onChange={e => setShowRealTrades(e.target.checked)}
              className="w-3.5 h-3.5 rounded border-white/20 bg-black/40 accent-[#00FF00]"
            />
            <span style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '0.5px' }}>MOSTRAR BUY/SELL</span>
          </label>
        </div>
        <div className="flex gap-3 border-l border-white/10 pl-3">
          <span className="flex items-center gap-1"><span style={{color:'#00FF00'}}>BUY</span> Buy</span>
          <span className="flex items-center gap-1"><span style={{color:'#FFA500'}}>SELL</span> Sell</span>
        </div>
        <div className="flex gap-3 border-l border-white/10 pl-3">
          <span className="flex items-center gap-1"><span style={{color:'#00C896'}}>B</span> Buy</span>
          <span className="flex items-center gap-1"><span style={{color:'#FF4757'}}>S</span> Sell</span>
          <span className="flex items-center gap-1"><span style={{color:'#ef5350'}}>●</span> SAR</span>
          <span className="flex items-center gap-1"><span style={{color:'#00C896'}}>--</span> U6</span>
          <span className="flex items-center gap-1"><span style={{color:'#FF4757'}}>--</span> L6</span>
        </div>
      </div>
      <div ref={chartContainerRef} className="w-full h-full" />
    </div>
  )
}
