'use client'
import React from 'react'
import { usePathname } from 'next/navigation'
import Sidebar from './Sidebar'

export default function AppContainer({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  
  const isAuthPage = 
    pathname === '/login' || 
    pathname === '/register' || 
    pathname.startsWith('/auth')

  if (isAuthPage) {
    return <div className="min-h-screen bg-[#05070a]">{children}</div>
  }

  return (
    <>
      <Sidebar />
      <main className="main-content">
        {children}
      </main>
    </>
  )
}
