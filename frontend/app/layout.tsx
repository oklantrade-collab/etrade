import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "eTrader — Plataforma de Trading Algorítmico Multimercado",
  description: "Volume Spike + Multi-Timeframe Confirmation trading system with automated OCO orders on Binance",
};

import { Toaster } from 'react-hot-toast';

import AppContainer from "@/components/AppContainer";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es">
      <body className="bg-[#05070a] text-slate-200">
        <Toaster position="bottom-right" toastOptions={{ style: { background: '#0f172a', color: '#fff', border: '1px solid #1e293b' } }} />
        <AppContainer>
           {children}
        </AppContainer>
      </body>
    </html>
  );
}
