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
        
        // Clear old PriceLines (active position markers)
        priceLinesRef.current.forEach(l => candleSeriesRef.current?.removePriceLine(l))
        priceLinesRef.current = []

        return
    }

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

    // --- SET INDICATOR DATA (FROM API) ---
    const basisSeries = (chartRef.current as any)?.basisSeries
    const upper6Series = (chartRef.current as any)?.upper6Series
    const lower6Series = (chartRef.current as any)?.lower6Series

    if (basisSeries && showBasis) {
        basisSeries.setData(candles.filter(c => parseFloat(c.basis) > 0).map(c => ({
            time: Math.floor(new Date(c.open_time || c.timestamp).getTime() / 1000) as any,
            value: parseFloat(c.basis)
        })).sort((a: any, b: any) => a.time - b.time))
    }
    if (upper6Series) {
        upper6Series.setData(candles.filter(c => parseFloat(c.upper_6) > 0).map(c => ({
            time: Math.floor(new Date(c.open_time || c.timestamp).getTime() / 1000) as any,
            value: parseFloat(c.upper_6)
        })).sort((a: any, b: any) => a.time - b.time))
    }
    if (lower6Series) {
        lower6Series.setData(candles.filter(c => parseFloat(c.lower_6) > 0).map(c => ({
            time: Math.floor(new Date(c.open_time || c.timestamp).getTime() / 1000) as any,
            value: parseFloat(c.lower_6)
        })).sort((a: any, b: any) => a.time - b.time))
    }

    // Add Markers
    const markers = trades
      .filter(t => t.type === 'entry' && showRealTrades)
      .map(t => {
        const isLong = t.direction === 'long'
        // Asegurar que el timestamp sea en segundos y sea un número válido
        let tradeTime = typeof t.timestamp === 'string' ? new Date(t.timestamp).getTime() / 1000 : t.timestamp
        if (tradeTime > 10000000000) tradeTime = tradeTime / 1000 // Convertir ms a s si es necesario
        
        // Encontrar la vela más cercana (o exacta) para alinear el marcador
        const candleTime = formattedCandles.find(c => c.time <= tradeTime && (c.time + (15 * 60)) > tradeTime)?.time || tradeTime

        return {
          time:     candleTime as any,
          position: isLong ? 'belowBar' : ('aboveBar' as any),
          color:    isLong ? '#00FF00' : '#FFA500', 
          shape:    'text' as any,
          text:     isLong ? 'BUY' : 'SELL',
          size:     1
        }
      })

    // --- ADD PINESCRIPT MARKERS (B/S) ---
    const pineMarkers = candles
      .filter(c => c.pinescript_signal === 'Buy' || c.pinescript_signal === 'Sell')
      .map(c => ({
        time:     Math.floor(new Date(c.open_time).getTime() / 1000) as any,
        position: c.pinescript_signal === 'Buy' ? 'belowBar' : ('aboveBar' as any),
        color:    c.pinescript_signal === 'Buy' ? '#00C896' : '#FF4757',
        shape:    'text' as any,
        text:     c.pinescript_signal === 'Buy' ? 'B' : 'S',
        size:     2, // Aumentado de 1 a 2
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
    priceLinesRef.current.forEach(l => candleSeriesRef.current?.removePriceLine(l))
    priceLinesRef.current = []

    if (activePosition && candleSeriesRef.current) {
      const entryPrice = activePosition.avg_entry || activePosition.entry_price || activePosition.avg_entry_price;
      const slPrice = activePosition.sl_price;
      const tp1Price = activePosition.tp_partial || activePosition.tp_partial_price || activePosition.tp_price;
      const tp2Price = activePosition.tp_full || activePosition.tp_full_price;

      const lines = [
        entryPrice ? { price: entryPrice, color: '#00C896', title: `Entry $${entryPrice.toLocaleString()}` } : null,
        slPrice ? { price: slPrice, color: '#FF4757', title: `SL $${slPrice.toLocaleString()}` } : null,
        tp1Price ? { price: tp1Price, color: '#FFD700', title: `TP1 $${tp1Price.toLocaleString()}` } : null,
        tp2Price ? { price: tp2Price, color: '#ffffff', title: `TP2 $${tp2Price.toLocaleString()}` } : null,
      ].filter(l => l !== null);

      lines.forEach((l: any) => {
        if (l.price > 0 && candleSeriesRef.current) {
          const pl = candleSeriesRef.current.createPriceLine({
            price: l.price,
            color: l.color,
            lineWidth: 1,
            lineStyle: (LineStyle as any).Dashed || 2,
            axisLabelVisible: true,
            title: l.title,
          })
          if (pl) priceLinesRef.current.push(pl)
        }
      })
    }

    if (!hasFitInitial && candles.length > 0) {
      chartRef.current?.timeScale().fitContent()
      setHasFitInitial(true)
    }
  }, [candles, trades, activePosition, showRealTrades]);

   }, [candles, trades, activePosition, showRealTrades]);

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
