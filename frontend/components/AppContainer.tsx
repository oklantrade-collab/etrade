'use client'
import React from 'react'
import { usePathname } from 'next/navigation'
import Sidebar from './Sidebar'

export default function AppContainer({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [isSidebarOpen, setIsSidebarOpen] = React.useState(false)

  React.useEffect(() => {
    setIsSidebarOpen(false)
  }, [pathname])
  
  const isAuthPage = 
    pathname === '/login' || 
    pathname === '/register' || 
    pathname.startsWith('/auth')

  if (isAuthPage) {
    return <div className="min-h-screen bg-[#05070a]">{children}</div>
  }

  return (
    <>
      <div className="mobile-top-nav md:hidden">
        <h1 className="text-xl font-black italic tracking-tighter bg-linear-to-r from-indigo-400 to-purple-500 bg-clip-text text-transparent">eTrader</h1>
        <button 
          onClick={() => setIsSidebarOpen(true)}
          className="p-2 text-slate-300 hover:text-white"
        >
          <span className="text-2xl">☰</span>
        </button>
      </div>

      {isSidebarOpen && (
        <div 
          className="sidebar-overlay" 
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      <Sidebar 
        isOpen={isSidebarOpen} 
        onClose={() => setIsSidebarOpen(false)} 
      />
      <main className="main-content">
        {children}
      </main>
    </>
  )
}
