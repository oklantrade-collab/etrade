import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

// Este endpoint es llamado por Vercel Cron
// cada día a las 03:00 UTC
export async function GET(request: Request) {

  // Seguridad: verificar que viene de Vercel
  const authHeader = request.headers.get(
    'authorization'
  )
  if (authHeader !== `Bearer ${
    process.env.CRON_SECRET
  }`) {
    return NextResponse.json(
      { error: 'Unauthorized' },
      { status: 401 }
    )
  }

  // Usar Service Role Key para operaciones
  // de limpieza (no la anon key)
  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  )

  try {
    const startTime = Date.now()

    // Llamar a la función de limpieza
    // que creamos con pg_cron en Supabase
    const { data, error } = await supabase
      .rpc('cleanup_database')

    if (error) throw error

    const duration = Date.now() - startTime

    console.log(
      '[CRON] Cleanup completado:',
      JSON.stringify(data)
    )

    return NextResponse.json({
      success:   true,
      result:    data,
      duration:  `${duration}ms`,
      timestamp: new Date().toISOString()
    })

  } catch (error: any) {
    console.error('[CRON] Error:', error.message)
    return NextResponse.json({
      success: false,
      error:   error.message
    }, { status: 500 })
  }
}
