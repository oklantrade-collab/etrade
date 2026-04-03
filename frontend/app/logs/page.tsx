'use client'
import { useEffect, useState, useRef } from 'react'
import { supabase } from '@/lib/supabase'

const MODULES = [
  { value: 'all', label: 'All Modules' },
  { value: 'pipeline', label: 'Pipeline' },
  { value: 'data_fetch', label: 'Data Fetcher' },
  { value: 'technical_indicators', label: 'Indicators' },
  { value: 'spike_detection', label: 'Spike Detection' },
  { value: 'mtf_scoring', label: 'MTF Scorer' },
  { value: 'mtf_scorer', label: 'MTF Scorer (alt)' },
  { value: 'sentiment', label: 'Sentiment' },
  { value: 'signal_generator', label: 'Signal Generator' },
  { value: 'candle_patterns', label: 'Candle Patterns' },
  { value: 'patterns', label: 'Patterns' },
  { value: 'risk', label: 'Risk' },
  { value: 'execution', label: 'Execution' },
  { value: 'alerts', label: 'Alerts' },
]

const LEVELS = [
  { value: 'all', label: 'All Levels' },
  { value: 'DEBUG', label: 'DEBUG' },
  { value: 'INFO', label: 'INFO' },
  { value: 'WARNING', label: 'WARNING' },
  { value: 'ERROR', label: 'ERROR' },
  { value: 'CRITICAL', label: 'CRITICAL' },
]

export default function LogsPage() {
  const [logs, setLogs] = useState<any[]>([])
  const [moduleFilter, setModuleFilter] = useState<string>('all')
  const [levelFilter, setLevelFilter] = useState<string>('all')
  const [cycleIdFilter, setCycleIdFilter] = useState<string>('')
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [nextCycleTimer, setNextCycleTimer] = useState<string>('')
  const terminalRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    loadLogs()
  }, [moduleFilter, levelFilter, cycleIdFilter])

  // Auto-refresh every 15 seconds
  useEffect(() => {
    if (!autoRefresh) return
    const interval = setInterval(() => {
      loadLogs()
    }, 15000)
    return () => clearInterval(interval)
  }, [autoRefresh, moduleFilter, levelFilter, cycleIdFilter])

  // Next cycle timer
  useEffect(() => {
    const updateTimer = () => {
      const now = new Date()
      const minutes = now.getMinutes()
      const nextCycleMinute = Math.ceil((minutes + 1) / 15) * 15
      const timeUntilNext = nextCycleMinute - minutes
      if (timeUntilNext <= 0) {
        setNextCycleTimer('starting now...')
      } else {
        setNextCycleTimer(`~${timeUntilNext} min`)
      }
    }
    updateTimer()
    const interval = setInterval(updateTimer, 30000)
    return () => clearInterval(interval)
  }, [])

  async function loadLogs() {
    let q = supabase
      .from('system_logs')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(200)

    if (moduleFilter !== 'all') q = q.eq('module', moduleFilter)
    if (levelFilter !== 'all') q = q.eq('level', levelFilter)
    if (cycleIdFilter.trim()) q = q.eq('cycle_id', cycleIdFilter.trim())

    const { data } = await q
    if (data) setLogs(data)
  }

  const getLevelColor = (level: string) => {
    switch (level) {
      case 'DEBUG':    return '#6B7280'
      case 'INFO':     return '#22C55E'
      case 'WARNING':  return '#EAB308'
      case 'ERROR':    return '#EF4444'
      case 'CRITICAL': return '#DC2626'
      default: return 'var(--text-muted)'
    }
  }

  const getLevelClass = (level: string) => {
    switch (level) {
      case 'INFO':     return 'log-info'
      case 'WARNING':  return 'log-warning'
      case 'ERROR':    return 'log-error'
      case 'CRITICAL': return 'log-critical'
      case 'DEBUG':    return 'log-debug'
      default: return ''
    }
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1>System Logs</h1>
          <p>Worker pipeline logs and system events</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div className="pulse-live" />
          <span style={{ fontSize: '0.8rem', color: 'var(--accent-green)' }}>
            {autoRefresh ? 'Auto-refresh ON' : 'Auto-refresh OFF'}
          </span>
        </div>
      </div>

      {/* Filters */}
      <div style={{
        display: 'flex',
        gap: 12,
        marginBottom: 20,
        flexWrap: 'wrap',
        alignItems: 'center',
      }}>
        <select
          className="select"
          value={moduleFilter}
          onChange={(e) => setModuleFilter(e.target.value)}
        >
          {MODULES.map(m => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </select>

        <select
          className="select"
          value={levelFilter}
          onChange={(e) => setLevelFilter(e.target.value)}
        >
          {LEVELS.map(l => (
            <option key={l.value} value={l.value}>{l.label}</option>
          ))}
        </select>

        <input
          className="input"
          style={{ width: 300 }}
          placeholder="Filter by Cycle ID..."
          value={cycleIdFilter}
          onChange={(e) => setCycleIdFilter(e.target.value)}
        />

        <label style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          fontSize: '0.85rem',
          color: 'var(--text-secondary)',
          cursor: 'pointer',
        }}>
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
            style={{ accentColor: 'var(--accent-green)' }}
          />
          🔄 Auto-refresh
        </label>

        <button className="btn btn-ghost" onClick={loadLogs}>
          Refresh
        </button>
      </div>

      {/* Terminal */}
      <div
        ref={terminalRef}
        className="log-terminal"
        style={{
          background: '#0A0F1E',
          maxHeight: 'calc(100vh - 300px)',
          minHeight: 400,
        }}
      >
        {/* Terminal header bar */}
        <div style={{
          display: 'flex',
          gap: 6,
          marginBottom: 12,
          paddingBottom: 10,
          borderBottom: '1px solid rgba(42, 48, 64, 0.5)',
        }}>
          <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#EF4444' }} />
          <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#F59E0B' }} />
          <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#22C55E' }} />
          <span style={{ marginLeft: 12, color: 'var(--text-muted)', fontSize: '0.75rem' }}>
            eTrader System Logs — {logs.length} entries
          </span>
        </div>

        {logs.length > 0 ? (
          logs.map((L) => {
            const time = new Date(L.created_at).toLocaleString('es-PE', { 
              timeZone: 'America/Lima',
              hour12: false,
              year: 'numeric',
              month: '2-digit',
              day: '2-digit',
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit'
            }).replace(',', '')
            return (
              <div key={L.id} className={`log-line ${L.level === 'CRITICAL' ? 'log-critical-pulse' : ''}`}>
                <span style={{ color: '#6B7280' }}>[{time}]</span>{' '}
                <span style={{
                  color: getLevelColor(L.level),
                  fontWeight: L.level === 'ERROR' || L.level === 'CRITICAL' ? 700 : 400,
                  display: 'inline-block',
                  width: 65,
                }}>
                  [{L.level}]
                </span>{' '}
                <span style={{ color: '#818CF8' }}>[{L.module}]</span>{' '}
                <span style={{ color: '#E2E8F0' }}>{L.message}</span>
              </div>
            )
          })
        ) : (
          <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', padding: 20 }}>
            No logs found for selected filters...
          </div>
        )}
      </div>

      {/* Footer */}
      <div style={{
        marginTop: 12,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        fontSize: '0.8rem',
        color: 'var(--text-muted)',
      }}>
        <span>Showing the last {logs.length} logs</span>
        <span>Next cycle in {nextCycleTimer}</span>
      </div>
    </div>
  )
}
