import { createClient } from '@supabase/supabase-js'

const DEFAULT_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoiYW5vbiIsImlzcyI6InBvc3RncmVzdCIsImlhdCI6MTc5NDAyNjc0NSwiZXhwIjoyMTA5Mzg2NzQ1fQ.ANOsR_yv7HhRFyrW_xd0XPK0fjdtt3SENwre6QWjkk4'

// En el navegador usar el propio origen (HTTPS en Vercel) para que las llamadas /rest/v1/*
// pasen por el proxy de Next.js sin errores de Mixed Content ni WebSocket inseguro (ws://).
const supabaseUrl =
  typeof window !== 'undefined'
    ? window.location.origin
    : (process.env.NEXT_PUBLIC_SUPABASE_URL || 'http://165.22.87.171')

const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || DEFAULT_ANON_KEY

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: false,
    autoRefreshToken: false,
  },
})

// PostgREST en DigitalOcean opera vía REST; desactivar creación de WebSockets Realtime
// para evitar SecurityError (ws:// en páginas https://) y reconexiones fallidas.
const noopChannel: any = {
  on: () => noopChannel,
  subscribe: (cb?: any) => {
    if (typeof cb === 'function') {
      try { cb('SUBSCRIBED') } catch {}
    }
    return noopChannel
  },
  unsubscribe: () => Promise.resolve('ok'),
}

supabase.channel = (() => noopChannel) as any
supabase.removeChannel = (() => Promise.resolve('ok')) as any

