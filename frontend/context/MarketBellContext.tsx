'use client';

import React, { createContext, useContext, useEffect, useState, useRef, useCallback } from 'react';
import { marketBell } from '@/lib/audio/marketBell';
import { getNYCDateTime, getNextMarketBellInfo, NYCTimeInfo, MarketBellEvent, isMarketHoliday, isEarlyCloseDay } from '@/lib/marketSchedule';
import toast from 'react-hot-toast';

interface MarketBellContextType {
  enabled: boolean;
  setEnabled: (enabled: boolean) => void;
  toggleEnabled: () => void;
  volume: number;
  setVolume: (volume: number) => void;
  nycTime: NYCTimeInfo;
  nextBell: MarketBellEvent;
  isUnlocked: boolean;
  unlockAudio: () => void;
  testBell: (type: 'open' | 'close') => void;
  lastTriggered: string | null;
  showModal: boolean;
  setShowModal: (show: boolean) => void;
}

const MarketBellContext = createContext<MarketBellContextType | null>(null);

export function MarketBellProvider({ children }: { children: React.ReactNode }) {
  const [enabled, setEnabledState] = useState<boolean>(true);
  const [volume, setVolumeState] = useState<number>(0.85);
  const [nycTime, setNycTime] = useState<NYCTimeInfo>(() => getNYCDateTime());
  const [nextBell, setNextBell] = useState<MarketBellEvent>(() => getNextMarketBellInfo(getNYCDateTime()));
  const [isUnlocked, setIsUnlocked] = useState<boolean>(false);
  const [lastTriggered, setLastTriggered] = useState<string | null>(null);
  const [showModal, setShowModal] = useState<boolean>(false);

  const prevIsOpenRef = useRef<boolean | null>(null);

  // Initialize saved preferences
  useEffect(() => {
    try {
      const savedEnabled = localStorage.getItem('etrade_market_bell_enabled');
      if (savedEnabled !== null) {
        setEnabledState(savedEnabled === 'true');
      }
      const savedVol = localStorage.getItem('etrade_bell_volume');
      if (savedVol !== null) {
        const v = parseFloat(savedVol);
        setVolumeState(v);
        marketBell.setVolume(v);
      }
    } catch (e) {
      // ignore
    }
    setIsUnlocked(marketBell.getIsUnlocked());
  }, []);

  const setEnabled = useCallback((value: boolean) => {
    setEnabledState(value);
    try {
      localStorage.setItem('etrade_market_bell_enabled', value ? 'true' : 'false');
    } catch (e) {
      // ignore
    }
  }, []);

  const toggleEnabled = useCallback(() => {
    setEnabled(!enabled);
  }, [enabled, setEnabled]);

  const setVolume = useCallback((value: number) => {
    setVolumeState(value);
    marketBell.setVolume(value);
  }, []);

  const unlockAudio = useCallback(() => {
    const success = marketBell.unlockAudio();
    setIsUnlocked(success);
  }, []);

  // Play Bell and record trigger
  const triggerBell = useCallback(async (type: 'open' | 'close', reason: string = 'horario automático') => {
    if (!enabled) {
      console.log(`[MarketBell] ${type.toUpperCase()} bell scheduled, but sound is muted by user.`);
      return;
    }

    console.log(`[MarketBell] 🔔 Ringing ${type.toUpperCase()} bell (${reason})`);
    marketBell.unlockAudio();
    setIsUnlocked(true);
    await marketBell.play(type);

    const nowStr = new Date().toLocaleTimeString();
    setLastTriggered(`${type === 'open' ? 'Apertura' : 'Cierre'} a las ${nowStr}`);

    if (type === 'open') {
      toast.custom(
        (t) => (
          <div className={`${t.visible ? 'animate-enter' : 'animate-leave'} max-w-md w-full bg-[#111622] border-2 border-emerald-500/70 shadow-2xl rounded-2xl pointer-events-auto flex p-4 text-white ring-1 ring-black ring-opacity-5`}>
            <div className="flex items-center gap-3">
              <span className="text-3xl animate-bounce">🔔</span>
              <div>
                <p className="text-sm font-black text-emerald-400 uppercase tracking-wider">¡Apertura de Wall Street (NYSE/NASDAQ)!</p>
                <p className="text-xs text-slate-300 mt-0.5">La campana bursátil ha sonado. Sesión regular abierta (09:30 AM ET).</p>
              </div>
            </div>
          </div>
        ),
        { duration: 8000 }
      );
    } else {
      toast.custom(
        (t) => (
          <div className={`${t.visible ? 'animate-enter' : 'animate-leave'} max-w-md w-full bg-[#111622] border-2 border-rose-500/70 shadow-2xl rounded-2xl pointer-events-auto flex p-4 text-white ring-1 ring-black ring-opacity-5`}>
            <div className="flex items-center gap-3">
              <span className="text-3xl animate-pulse">🛎️</span>
              <div>
                <p className="text-sm font-black text-rose-400 uppercase tracking-wider">¡Cierre de la Bolsa (NYSE/NASDAQ)!</p>
                <p className="text-xs text-slate-300 mt-0.5">La campana de cierre ha sonado. Sesión regular finalizada (04:00 PM ET).</p>
              </div>
            </div>
          </div>
        ),
        { duration: 8000 }
      );
    }
  }, [enabled]);

  // Public test trigger
  const testBell = useCallback((type: 'open' | 'close') => {
    triggerBell(type, 'prueba manual');
  }, [triggerBell]);

  // Main 1-second timekeeping and auto-trigger clock
  useEffect(() => {
    const timer = setInterval(() => {
      const currentNYC = getNYCDateTime();
      setNycTime(currentNYC);
      setNextBell(getNextMarketBellInfo(currentNYC));
      setIsUnlocked(marketBell.getIsUnlocked());

      const { year, month, day, dayOfWeek, hours, minutes, seconds, dateStr } = currentNYC;
      const holiday = isMarketHoliday(year, month, day, dayOfWeek);
      if (holiday.isHoliday) {
        return; // No bell on holidays or weekends
      }

      const isEarlyClose = isEarlyCloseDay(year, month, day, dayOfWeek);
      const closeHour = isEarlyClose ? 13 : 16;

      // 1. Check Market Open: 09:30:00 ET (window 0-2 seconds)
      if (hours === 9 && minutes === 30 && seconds <= 2) {
        const key = `etrade_bell_${dateStr}_open`;
        if (typeof window !== 'undefined' && !localStorage.getItem(key)) {
          localStorage.setItem(key, 'true');
          triggerBell('open', '09:30:00 AM ET Exacto');
        }
      }

      // 2. Check Market Close: 16:00:00 ET (or 13:00 on early close)
      if (hours === closeHour && minutes === 0 && seconds <= 2) {
        const key = `etrade_bell_${dateStr}_close`;
        if (typeof window !== 'undefined' && !localStorage.getItem(key)) {
          localStorage.setItem(key, 'true');
          triggerBell('close', `${closeHour}:00:00 PM ET Exacto`);
        }
      }
    }, 1000);

    return () => clearInterval(timer);
  }, [triggerBell]);

  // Supplementary backend status poller (every 30 seconds)
  useEffect(() => {
    const checkBackendStatus = async () => {
      try {
        const res = await fetch(`/api/v1/stocks/market-status?t=${Date.now()}`);
        if (!res.ok) return;
        const data = await res.json();
        
        // If state changed from closed to open during market hours
        if (prevIsOpenRef.current === false && data.is_open === true) {
          const currentNYC = getNYCDateTime();
          const key = `etrade_bell_${currentNYC.dateStr}_open`;
          if (!localStorage.getItem(key)) {
            localStorage.setItem(key, 'true');
            triggerBell('open', 'Transición API a Mercado Abierto');
          }
        }
        
        // If state changed from open to closed
        if (prevIsOpenRef.current === true && data.is_open === false) {
          const currentNYC = getNYCDateTime();
          const key = `etrade_bell_${currentNYC.dateStr}_close`;
          if (!localStorage.getItem(key)) {
            localStorage.setItem(key, 'true');
            triggerBell('close', 'Transición API a Mercado Cerrado');
          }
        }

        prevIsOpenRef.current = data.is_open;
      } catch (e) {
        // quiet error
      }
    };

    checkBackendStatus();
    const interval = setInterval(checkBackendStatus, 30000);
    return () => clearInterval(interval);
  }, [triggerBell]);

  return (
    <MarketBellContext.Provider
      value={{
        enabled,
        setEnabled,
        toggleEnabled,
        volume,
        setVolume,
        nycTime,
        nextBell,
        isUnlocked,
        unlockAudio,
        testBell,
        lastTriggered,
        showModal,
        setShowModal,
      }}
    >
      {children}
    </MarketBellContext.Provider>
  );
}

export function useMarketBell() {
  const context = useContext(MarketBellContext);
  if (!context) {
    throw new Error('useMarketBell must be used within a MarketBellProvider');
  }
  return context;
}
