import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

/**
 * eTrade v4 — Vercel Cron: Limpieza Diaria de BD
 * 
 * Ejecuta: Diariamente a las 03:00 UTC (22:00 Lima)
 * Config:  vercel.json → crons[].path = "/api/cron/cleanup"
 * 
 * ESTRATEGIA DUAL:
 *   1. Intenta ejecutar cleanup_database() via RPC (pg_cron nativo)
 *   2. Si falla, ejecuta limpieza directa tabla por tabla
 * 
 * PROVEEDORES: Binance, IC Markets, Interactive Brokers + 2 futuros
 * SÍMBOLOS:    ~4 por proveedor × 5 = 20 símbolos
 * OBJETIVO:    Mantener BD < 400MB (free tier = 500MB)
 */

export async function GET(request: Request) {

  // ── Seguridad: Verificar origen de Vercel Cron ──
  const authHeader = request.headers.get('authorization')
  if (authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
    return NextResponse.json(
      { error: 'Unauthorized' },
      { status: 401 }
    )
  }

  // ── Crear cliente con Service Role Key ──
  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  )

  const startTime = Date.now()

  try {
    // ── ESTRATEGIA 1: Ejecutar función SQL nativa ──
    const { data, error } = await supabase.rpc('cleanup_database')

    if (error) {
      console.warn('[CRON] RPC cleanup_database falló, ejecutando fallback:', error.message)
      
      // ── ESTRATEGIA 2: Fallback — limpieza directa ──
      const fallbackResult = await directCleanup(supabase)
      const duration = Date.now() - startTime

      return NextResponse.json({
        success:   true,
        strategy:  'fallback_direct',
        result:    fallbackResult,
        duration:  `${duration}ms`,
        timestamp: new Date().toISOString()
      })
    }

    const duration = Date.now() - startTime

    console.log('[CRON] Cleanup completado via RPC:', JSON.stringify(data))

    return NextResponse.json({
      success:   true,
      strategy:  'rpc_native',
      result:    data,
      duration:  `${duration}ms`,
      timestamp: new Date().toISOString()
    })

  } catch (error: any) {
    console.error('[CRON] Error crítico:', error.message)

    // Loguear error en system_logs
    try {
      await supabase.table('system_logs').insert({
        module:     'CRON_CLEANUP',
        level:      'ERROR',
        message:    `Vercel Cron falló: ${error.message}`,
        created_at: new Date().toISOString()
      })
    } catch { /* silencioso */ }

    return NextResponse.json({
      success: false,
      error:   error.message
    }, { status: 500 })
  }
}


/**
 * Limpieza directa tabla por tabla (Fallback).
 * Se usa si la función RPC cleanup_database() no existe.
 */
async function directCleanup(supabase: ReturnType<typeof createClient>) {
  const results: Record<string, number> = {}
  const now = new Date()

  // ── 1. System Logs (48 horas) ──
  try {
    const cutoff = new Date(now.getTime() - 48 * 60 * 60 * 1000)
    const { data } = await supabase
      .from('system_logs')
      .delete()
      .lt('created_at', cutoff.toISOString())
      .select('id')

    results.system_logs = data?.length || 0
  } catch (e) { results.system_logs = -1 }

  // ── 2. Pilot Diagnostics (24 horas) ──
  try {
    const cutoff = new Date(now.getTime() - 24 * 60 * 60 * 1000)
    const { data } = await supabase
      .from('pilot_diagnostics')
      .delete()
      .lt('timestamp', cutoff.toISOString())
      .select('id')

    results.pilot_diagnostics = data?.length || 0
  } catch (e) { results.pilot_diagnostics = -1 }

  // ── 3. Strategy Evaluations (7 días) ──
  try {
    const cutoff = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
    const { data } = await supabase
      .from('strategy_evaluations')
      .delete()
      .lt('created_at', cutoff.toISOString())
      .select('id')

    results.strategy_evaluations = data?.length || 0
  } catch (e) { results.strategy_evaluations = -1 }

  // ── 4. Volume Spikes (14 días) ──
  try {
    const cutoff = new Date(now.getTime() - 14 * 24 * 60 * 60 * 1000)
    const { data } = await supabase
      .from('volume_spikes')
      .delete()
      .lt('detected_at', cutoff.toISOString())
      .select('id')

    results.volume_spikes = data?.length || 0
  } catch (e) { results.volume_spikes = -1 }

  // ── 5. Signals Log (14 días) ──
  try {
    const cutoff = new Date(now.getTime() - 14 * 24 * 60 * 60 * 1000)
    const { data } = await supabase
      .from('signals_log')
      .delete()
      .lt('detected_at', cutoff.toISOString())
      .select('id')

    results.signals_log = data?.length || 0
  } catch (e) { results.signals_log = -1 }

  // ── 6. Cooldowns inactivos ──
  try {
    const { data } = await supabase
      .from('cooldowns')
      .delete()
      .eq('active', false)
      .select('id')

    results.cooldowns = data?.length || 0
  } catch (e) { results.cooldowns = -1 }

  // ── 7. Pending Orders completadas (7 días) ──
  try {
    const cutoff = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
    const { data } = await supabase
      .from('pending_orders')
      .delete()
      .in('status', ['cancelled', 'expired', 'triggered'])
      .lt('created_at', cutoff.toISOString())
      .select('id')

    results.pending_orders = data?.length || 0
  } catch (e) { results.pending_orders = -1 }

  // ── Total ──
  const total = Object.values(results)
    .filter(v => v > 0)
    .reduce((a, b) => a + b, 0)

  results.total_deleted = total

  // ── Loguear resultado ──
  try {
    await supabase.from('system_logs').insert({
      module:     'CRON_CLEANUP',
      level:      'INFO',
      message:    `Fallback cleanup: ${total} filas eliminadas`,
      created_at: new Date().toISOString()
    })
  } catch { /* silencioso */ }

  return results
}
