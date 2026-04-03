'use client'
import React, { useState } from 'react'
import { supabase } from '@/lib/supabase'

export default function ConfigBackup() {
  const [exporting, setExporting] = useState(false)
  const [importing, setImporting] = useState(false)

  async function handleExport() {
    setExporting(true)
    try {
      // Fetch all relevant config tables
      const { data: config } = await supabase.from('trading_config').select('*')
      const { data: rules } = await supabase.from('trading_rules').select('*')
      
      const backupData = {
        version: '3.0',
        timestamp: new Date().toISOString(),
        config: config?.[0] || {},
        rules: rules || []
      }

      // Create blob and download
      const blob = new Blob([JSON.stringify(backupData, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `eTrade-backup-${new Date().toISOString().split('T')[0]}.json`
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setExporting(false)
    }
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return

    setImporting(true)
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      
      if (!confirm('This will overwrite current configuration and rules. Are you sure?')) return

      // Logic to restore would go here...
      // await supabase.from('trading_config').upsert(data.config)...
      
      alert('Backup restored successfully (simulated)')
    } catch (err) {
      alert('Error importing backup')
    } finally {
      setImporting(false)
      e.target.value = ''
    }
  }

  return (
    <div className="flex gap-4">
      <button 
        onClick={handleExport}
        disabled={exporting}
        className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-sm font-semibold transition-colors border border-slate-700"
      >
        <span>📥</span> {exporting ? 'Exporting...' : 'Export Config'}
      </button>
      
      <div className="relative">
        <input 
          type="file" 
          onChange={handleImport}
          className="absolute inset-0 opacity-0 cursor-pointer" 
          accept=".json"
        />
        <button 
          disabled={importing}
          className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-sm font-semibold transition-colors border border-slate-700"
        >
          <span>📤</span> {importing ? 'Importing...' : 'Import Config'}
        </button>
      </div>

      <button className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-sm font-semibold transition-colors border border-slate-700">
        <span>↺</span> Restore Defaults
      </button>
    </div>
  )
}
