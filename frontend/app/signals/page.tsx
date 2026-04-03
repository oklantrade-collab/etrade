'use client'
import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'

export default function SignalsPage() {
  const [activeTab, setActiveTab] = useState<'signals' | 'spikes'>('signals')
  const [signals, setSignals] = useState<any[]>([])
  const [spikes, setSpikes] = useState<any[]>([])
  const [filter, setFilter] = useState<string>('all')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadSignals()
    loadSpikes()

    // Realtime subscription for new signals
    const channel = supabase
      .channel('signals-feed')
      .on('postgres_changes', {
        event: 'INSERT',
        schema: 'public',
        table: 'trading_signals',
      }, (payload) => {
        setSignals(prev => [payload.new, ...prev].slice(0, 50))
      })
      .on('postgres_changes', {
        event: 'INSERT',
        schema: 'public',
        table: 'volume_spikes',
      }, (payload) => {
        setSpikes(prev => [payload.new, ...prev].slice(0, 50))
      })
      .subscribe()

    return () => { supabase.removeChannel(channel) }
  }, [])

  useEffect(() => {
    loadSignals()
  }, [filter])

  async function loadSignals() {
    setLoading(true)
    let q = supabase
      .from('trading_signals')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(50)

    if (filter !== 'all') {
      q = q.eq('signal_type', filter.toUpperCase())
    }
    const { data } = await q
    if (data) setSignals(data)
    setLoading(false)
  }

  async function loadSpikes() {
    const { data } = await supabase
      .from('volume_spikes')
      .select('*')
      .order('detected_at', { ascending: false })
      .limit(50)
    if (data) setSpikes(data)
  }

  const formatTimeAgo = (ts: string) => {
    if (!ts) return '—'
    const diff = (Date.now() - new Date(ts).getTime()) / 60000
    if (diff < 1) return 'just now'
    if (diff < 60) return `${Math.floor(diff)} min ago`
    if (diff < 1440) return `${Math.floor(diff / 60)}h ago`
    return `${Math.floor(diff / 1440)}d ago`
  }

  const renderVoteArrow = (vote: number) => {
    if (vote === 1) return <span className="vote-up">↑</span>
    if (vote === -1) return <span className="vote-down">↓</span>
    return <span className="vote-neutral">→</span>
  }

  const renderVoteWeight = (vote: number, weight: string) => {
    const cls = vote === 1 ? 'vote-up' : vote === -1 ? 'vote-down' : 'vote-neutral'
    return <span className={cls}>×{weight}</span>
  }

  const getSentimentEmoji = (score: number) => {
    if (score > 0.3) return '😊 Bullish'
    if (score < -0.3) return '😟 Bearish'
    return '😐 Neutral'
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'pending':
        return <span className="badge badge-yellow">PENDING EXECUTION</span>
      case 'hold':
        return <span className="badge badge-gray">HOLD - Score insuficiente</span>
      case 'executed':
        return <span className="badge badge-green">EXECUTED</span>
      case 'rejected':
        return <span className="badge badge-red">REJECTED</span>
      default:
        return <span className="badge badge-gray">{status}</span>
    }
  }

  const getSignalBorder = (type: string) => {
    if (type === 'BUY') return 'var(--accent-green)'
    if (type === 'SELL') return 'var(--accent-red)'
    return 'var(--border-color)'
  }

  const getSignalIcon = (type: string) => {
    if (type === 'BUY') return '🟢'
    if (type === 'SELL') return '🔴'
    return '⚪'
  }

  const getMTFBreakdown = (s: any) => [
    { tf: '15m', vote: s.vote_15m || 0, weight: '0.35' },
    { tf: '30m', vote: s.vote_30m || 0, weight: '0.20' },
    { tf: '45m', vote: s.vote_45m || 0, weight: '0.15' },
    { tf: '4h',  vote: s.vote_4h  || 0, weight: '0.15' },
    { tf: '1d',  vote: s.vote_1d  || 0, weight: '0.10' },
    { tf: '1w',  vote: s.vote_1w  || 0, weight: '0.05' },
  ]

  const getSpikeDirectionBadge = (dir: string) => {
    if (dir === 'BULLISH') return <span className="badge badge-green">🟢 BULLISH</span>
    if (dir === 'BEARISH') return <span className="badge badge-red">🔴 BEARISH</span>
    return <span className="badge badge-gray">⚪ INDETER</span>
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1>Signals Feed</h1>
          <p>Real-time MTF trading signals and volume spike detection</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="signal-tabs" style={{ display: 'flex', gap: 0, marginBottom: 24 }}>
        <button
          className={`tab-btn ${activeTab === 'signals' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('signals')}
        >
          📊 Trading Signals
        </button>
        <button
          className={`tab-btn ${activeTab === 'spikes' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('spikes')}
        >
          ⚡ Volume Spikes
        </button>
      </div>

      {/* ═══ TAB 1: Trading Signals ═══ */}
      {activeTab === 'signals' && (
        <>
          <div style={{ marginBottom: 16, display: 'flex', gap: 12, alignItems: 'center' }}>
            <select
              className="select"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option value="all">All Signals</option>
              <option value="buy">BUY Only</option>
              <option value="sell">SELL Only</option>
              <option value="hold">HOLD Only</option>
            </select>
            <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
              {signals.length} signals loaded
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {signals.map((s) => (
              <div
                key={s.id}
                className="card signal-card"
                style={{
                  borderLeft: `4px solid ${getSignalBorder(s.signal_type)}`,
                  padding: '20px 24px',
                  animation: 'fadeIn 0.3s ease',
                }}
              >
                {/* Row 1: Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontSize: '1.2rem' }}>{getSignalIcon(s.signal_type)}</span>
                    <span className={`badge ${s.signal_type === 'BUY' ? 'badge-green' : s.signal_type === 'SELL' ? 'badge-red' : 'badge-gray'}`}
                          style={{ fontSize: '0.85rem', padding: '5px 14px' }}>
                      {s.signal_type}
                    </span>
                    <h3 style={{ fontSize: '1.15rem', fontWeight: 800 }}>{s.symbol}</h3>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    {getStatusBadge(s.status)}
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                      {formatTimeAgo(s.created_at)}
                    </span>
                  </div>
                </div>

                {/* Row 2: Score + Prices + MTF */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1.5fr', gap: 24 }}>
                  {/* Score Block */}
                  <div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 8 }}>Score Final</div>
                    <div className={`${parseFloat(s.score_final) >= 0.65 ? 'score-positive' : parseFloat(s.score_final) <= -0.65 ? 'score-negative' : 'score-neutral'}`}
                         style={{ fontSize: '1.8rem', fontWeight: 800 }}>
                      {parseFloat(s.score_final || 0).toFixed(4)}
                    </div>
                    {s.sentiment_adjustment != null && parseFloat(s.sentiment_adjustment) !== 0 && (
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: 4 }}>
                        Sentiment: {parseFloat(s.sentiment_adjustment) > 0 ? '+' : ''}{parseFloat(s.sentiment_adjustment).toFixed(4)}
                      </div>
                    )}
                  </div>

                  {/* Trade Parameters */}
                  <div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 8 }}>Trade Parameters</div>
                    {parseFloat(s.entry_price || 0) > 0 ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: '0.85rem' }}>
                        <div>
                          <span style={{ color: 'var(--text-muted)' }}>Entry: </span>
                          <strong>${parseFloat(s.entry_price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 8 })}</strong>
                        </div>
                        {s.stop_loss && (
                          <div>
                            <span style={{ color: 'var(--text-muted)' }}>SL: </span>
                            <strong style={{ color: 'var(--accent-red)' }}>${parseFloat(s.stop_loss).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 8 })}</strong>
                          </div>
                        )}
                        {s.take_profit && (
                          <div>
                            <span style={{ color: 'var(--text-muted)' }}>TP: </span>
                            <strong style={{ color: 'var(--accent-green)' }}>${parseFloat(s.take_profit).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 8 })}</strong>
                          </div>
                        )}
                        {s.risk_reward_ratio && (
                          <div style={{ marginTop: 2 }}>
                            <span style={{ color: 'var(--text-muted)' }}>R/R: </span>
                            <strong>{parseFloat(s.risk_reward_ratio).toFixed(1)}x</strong>
                            {s.atr_4h_used && (
                              <span style={{ color: 'var(--text-muted)', marginLeft: 8, fontSize: '0.75rem' }}>
                                ATR 4h: ${parseFloat(s.atr_4h_used).toLocaleString()}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    ) : (
                      <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No Trade Params</div>
                    )}
                  </div>

                  {/* MTF Breakdown */}
                  <div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 8 }}>MTF Breakdown</div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '6px 16px', fontSize: '0.8rem' }}>
                      {getMTFBreakdown(s).map(tf => (
                        <div key={tf.tf} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span style={{ fontWeight: 700, width: 28, color: 'var(--text-secondary)' }}>{tf.tf}</span>
                          {renderVoteArrow(tf.vote)}
                          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>×{tf.weight}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ))}

            {signals.length === 0 && (
              <div className="card" style={{ textAlign: 'center', padding: 48 }}>
                <div style={{ fontSize: '2rem', marginBottom: 12 }}>📊</div>
                <p style={{ color: 'var(--text-muted)' }}>
                  No signals generated yet. Waiting for volume spikes to trigger the MTF analysis pipeline...
                </p>
              </div>
            )}
          </div>
        </>
      )}

      {/* ═══ TAB 2: Volume Spikes ═══ */}
      {activeTab === 'spikes' && (
        <div>
          <div className="table-container card" style={{ padding: 0 }}>
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Direction</th>
                  <th>Spike Ratio</th>
                  <th>Buy Vol %</th>
                  <th>Body %</th>
                  <th>Signal?</th>
                  <th>MTF Score</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {spikes.map((sp) => (
                  <tr key={sp.id}>
                    <td style={{ fontWeight: 700 }}>{sp.symbol}</td>
                    <td>{getSpikeDirectionBadge(sp.spike_direction)}</td>
                    <td style={{ fontWeight: 600 }}>×{parseFloat(sp.spike_ratio || 0).toFixed(1)}</td>
                    <td>{parseFloat(sp.taker_buy_pct || 0).toFixed(1)}%</td>
                    <td>{parseFloat(sp.body_pct || 0).toFixed(1)}%</td>
                    <td>
                      {sp.resulted_in_signal ? (
                        <span style={{ color: 'var(--accent-green)' }}>✅</span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)' }}>—</span>
                      )}
                    </td>
                    <td>
                      {sp.mtf_score != null ? (
                        <span className={parseFloat(sp.mtf_score) >= 0.65 ? 'vote-up' : parseFloat(sp.mtf_score) <= -0.65 ? 'vote-down' : 'vote-neutral'}>
                          {parseFloat(sp.mtf_score).toFixed(4)}
                        </span>
                      ) : '—'}
                    </td>
                    <td style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                      {formatTimeAgo(sp.detected_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {spikes.length === 0 && (
              <div style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)' }}>
                <div style={{ fontSize: '2rem', marginBottom: 12 }}>⚡</div>
                No volume spikes detected yet. Monitoring...
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
