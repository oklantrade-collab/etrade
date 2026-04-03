'use client'
import React, { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { verifyEmail } from '@/lib/api-client'
import Link from 'next/link'

export default function VerifyPage() {
  const searchParams = useSearchParams()
  const token = searchParams.get('token')
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('Verificando tu cuenta...')
  const router = useRouter()

  useEffect(() => {
    if (!token) {
      setStatus('error')
      setMessage('Token de verificación no encontrado.')
      return
    }

    const doVerify = async () => {
      try {
        const res = await verifyEmail(token)
        setStatus('success')
        setMessage(res.message || 'Tu cuenta ha sido verificada con éxito.')
      } catch (err: any) {
        setStatus('error')
        setMessage(err.message || 'Error al verificar la cuenta.')
      }
    }

    doVerify()
  }, [token])

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#05070a] selection:bg-emerald-500/30">
      <div className="w-full max-w-md p-6 text-center animate-in fade-in zoom-in-95 duration-500">
        <div className="bg-[#0c0f16]/80 backdrop-blur-xl border border-white/5 rounded-3xl p-10 shadow-2xl">
          {status === 'loading' && (
            <div className="space-y-6 py-10">
              <div className="w-16 h-16 border-4 border-emerald-500/20 border-t-emerald-500 rounded-full animate-spin mx-auto md:w-20 md:h-20" />
              <h2 className="text-xl font-bold text-white tracking-tight">{message}</h2>
            </div>
          )}

          {status === 'success' && (
            <div className="space-y-6 py-6">
              <div className="w-20 h-20 bg-emerald-500/20 text-emerald-500 rounded-full flex items-center justify-center mx-auto text-4xl shadow-lg shadow-emerald-500/10">✓</div>
              <h2 className="text-2xl font-bold text-white">¡Excelente!</h2>
              <p className="text-slate-400 text-sm leading-relaxed">{message}</p>
              <Link href="/login" className="inline-block mt-4 px-8 py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-xl transition-all shadow-lg shadow-emerald-500/20">
                Iniciar Sesión Ahora
              </Link>
            </div>
          )}

          {status === 'error' && (
            <div className="space-y-6 py-6">
              <div className="w-20 h-20 bg-red-500/20 text-red-500 rounded-full flex items-center justify-center mx-auto text-4xl shadow-lg shadow-red-500/10">!</div>
              <h2 className="text-2xl font-bold text-white">Lo sentimos</h2>
              <p className="text-red-400/80 text-sm leading-relaxed">{message}</p>
              <div className="pt-4 flex flex-col space-y-3">
                <Link href="/login" className="text-slate-400 hover:text-white text-xs font-medium transition-colors">
                  Volver al inicio
                </Link>
                <button onClick={() => window.location.reload()} className="text-emerald-500 hover:text-emerald-400 text-xs font-bold transition-all underline decoration-emerald-500/30">
                  Intentar de nuevo
                </button>
              </div>
            </div>
          )}
        </div>

        <p className="mt-10 text-[0.6rem] text-slate-700 tracking-[0.4em] uppercase font-bold">eTrade Platform Security</p>
      </div>
    </div>
  )
}
