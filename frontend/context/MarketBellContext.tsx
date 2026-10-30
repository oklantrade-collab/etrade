'use client';

import React, { createContext, useContext, useEffect, useState, useRef, useCallback } from 'react';
import { marketBell, BellSoundProfile, SoundOption, AVAILABLE_SOUNDS } from '@/lib/audio/marketBell';
import { getNYCDateTime, getNextMarketBellInfo, NYCTimeInfo, MarketBellEvent, isMarketHoliday, isEarlyCloseDay } from '@/lib/marketSchedule';
import { supabase } from '@/lib/supabase';
import toast from 'react-hot-toast';

export interface OrderFillDetails {
  symbol?: string;
  shares?: number;
  price?: number;
  isOption?: boolean;
}

interface MarketBellContextType {
  enabled: boolean;
  setEnabled: (enabled: boolean) => void;
  toggleEnabled: () => void;
  volume: number;
  setVolume: (volume: number) => void;
  soundProfile: BellSoundProfile;
  setSoundProfile: (profile: BellSoundProfile) => void;
  availableSounds: SoundOption[];
  nycTime: NYCTimeInfo;
  nextBell: MarketBellEvent;
  isUnlocked: boolean;
  unlockAudio: () => void;
  testBell: (type: 'open' | 'close', specificProfile?: BellSoundProfile) => void;
  playOrderSound: (type: 'buy' | 'sell' | 'close', details?: OrderFillDetails) => Promise<void>;
  lastTriggered: string | null;
  showModal: boolean;
  setShowModal: (show: boolean) => void;
}

const MarketBellContext = createContext<MarketBellContextType | null>(null);

export function MarketBellProvider({ children }: { children: React.ReactNode }) {
  const [enabled, setEnabledState] = useState<boolean>(true);
  const [volume, setVolumeState] = useState<number>(0.85);
  const [soundProfile, setSoundProfileState] = useState<BellSoundProfile>('tos-session');
  const [nycTime, setNycTime] = useState<NYCTimeInfo>(() => getNYCDateTime());
  const [nextBell, setNextBell] = useState<MarketBellEvent>(() => getNextMarketBellInfo(getNYCDateTime()));
  const [isUnlocked, setIsUnlocked] = useState<boolean>(false);
  const [lastTriggered, setLastTriggered] = useState<string | null>(null);
  const [showModal, setShowModal] = useState<boolean>(false);

  const prevIsOpenRef = useRef<boolean | null>(null);
  const knownFilledOrdersRef = useRef<Set<string>>(new Set());
  const knownStocksPositionsRef = useRef<Map<string, string>>(new Map());
  const knownOptionTradesRef = useRef<Map<string, string>>(new Map());
  const isFirstCheckRef = useRef<boolean>(true);

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
      const savedProf = localStorage.getItem('etrade_bell_sound_profile') as BellSoundProfile;
      if (savedProf && AVAILABLE_SOUNDS.some(s => s.id === savedProf)) {
        setSoundProfileState(savedProf);
        marketBell.setSoundProfile(savedProf);
      }
    } catch (e) {
      // ignore
    }
    setIsUnlocked(marketBell.getIsUnlocked());
  }, []);

  // Global window listeners: Auto-unlock audio on ANY user click, touch, or keypress anywhere on screen
  useEffect(() => {
    const handleUserInteraction = () => {
      const ok = marketBell.unlockAudio();
      if (ok) {
        setIsUnlocked(true);
      }
    };

    window.addEventListener('click', handleUserInteraction, { capture: true, passive: true });
    window.addEventListener('touchstart', handleUserInteraction, { capture: true, passive: true });
    window.addEventListener('keydown', handleUserInteraction, { capture: true, passive: true });
    window.addEventListener('mousedown', handleUserInteraction, { capture: true, passive: true });

    return () => {
      window.removeEventListener('click', handleUserInteraction);
      window.removeEventListener('touchstart', handleUserInteraction);
      window.removeEventListener('keydown', handleUserInteraction);
      window.removeEventListener('mousedown', handleUserInteraction);
    };
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

  const setSoundProfile = useCallback((profile: BellSoundProfile) => {
    setSoundProfileState(profile);
    marketBell.setSoundProfile(profile);
  }, []);

  const unlockAudio = useCallback(() => {
    const success = marketBell.unlockAudio();
    setIsUnlocked(success);
  }, []);

  // Play Bell and record trigger
  const triggerBell = useCallback(async (
    type: 'open' | 'close', 
    reason: string = 'horario automático',
    overrideProfile?: BellSoundProfile
  ) => {
    if (!enabled && !overrideProfile) {
      console.log(`[MarketBell] ${type.toUpperCase()} bell scheduled, but sound is muted by user.`);
      return;
    }

    console.log(`[MarketBell] 🔔 Ringing Thinkorswim ${type.toUpperCase()} bell (${reason})`);
    marketBell.unlockAudio();
    setIsUnlocked(true);
    await marketBell.play(type, overrideProfile);

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
                <p className="text-xs text-slate-300 mt-0.5">Campana Thinkorswim reproducida. Sesión regular abierta (09:30 AM ET / 08:30 AM Lima).</p>
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
                <p className="text-xs text-slate-300 mt-0.5">Campana Thinkorswim reproducida. Sesión regular finalizada (04:00 PM ET / 03:00 PM Lima).</p>
              </div>
            </div>
          </div>
        ),
        { duration: 8000 }
      );
    }
  }, [enabled]);

  // Play Thinkorswim Order Confirmation Sounds (Ding for Buy, Chimes for Sell/Close)
  const playOrderSound = useCallback(async (
    type: 'buy' | 'sell' | 'close', 
    details?: OrderFillDetails
  ) => {
    if (!enabled) return;
    marketBell.unlockAudio();
    setIsUnlocked(true);
    await marketBell.playOrderSound(type);

    const isBuy = type === 'buy';
    const sym = details?.symbol || 'ACTIVO';
    const shares = details?.shares ? `${details.shares}x ` : '';
    const priceStr = details?.price ? ` @ $${details.price.toFixed(2)}` : '';
    const assetKind = details?.isOption ? 'OPCIÓN' : 'STOCK';

    toast.custom(
      (t) => (
        <div className={`${t.visible ? 'animate-enter' : 'animate-leave'} max-w-md w-full bg-[#111622] border-2 ${isBuy ? 'border-cyan-500/80' : 'border-amber-500/80'} shadow-2xl rounded-2xl pointer-events-auto flex p-3.5 text-white ring-1 ring-black ring-opacity-5`}>
          <div className="flex items-center gap-3">
            <span className="text-2xl">{isBuy ? '🛒' : '💰'}</span>
            <div>
              <p className={`text-xs font-black uppercase tracking-wider ${isBuy ? 'text-cyan-400' : 'text-amber-400'}`}>
                {isBuy ? `¡COMPRA ${assetKind} CONFIRMADA!` : `¡VENTA / CIERRE ${assetKind} CONFIRMADA!`}
              </p>
              <p className="text-xs text-slate-200 mt-0.5">
                {shares}{sym}{priceStr} • Ejecutado en broker Interactive Brokers (TWS).
              </p>
            </div>
          </div>
        </div>
      ),
      { duration: 6000 }
    );
  }, [enabled]);

  // Public test trigger
  const testBell = useCallback((type: 'open' | 'close', specificProfile?: BellSoundProfile) => {
    triggerBell(type, 'prueba manual Thinkorswim', specificProfile);
  }, [triggerBell]);

  // Main 1-second timekeeping and resilient auto-trigger clock
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

      // Seconds elapsed today in New York
      const totalSec = hours * 3600 + minutes * 60 + seconds;
      const openSec = 9 * 3600 + 30 * 60; // 34200 (09:30:00 ET / 08:30 Lima)
      const closeSec = closeHour * 3600;   // 57600 (16:00:00 ET / 15:00 Lima) or 46800 (13:00 ET)

      // 1. Check Market Open: 09:30:00 ET (resilient 300s window so it rings even if tab is opened at 09:31)
      if (totalSec >= openSec && totalSec < openSec + 300) {
        const key = `etrade_bell_${dateStr}_open`;
        if (typeof window !== 'undefined' && !localStorage.getItem(key)) {
          localStorage.setItem(key, 'true');
          triggerBell('open', '09:30 AM ET Apertura Oficial (08:30 Lima)');
        }
      }

      // 2. Check Market Close: 16:00:00 ET (resilient 300s window)
      if (totalSec >= closeSec && totalSec < closeSec + 300) {
        const key = `etrade_bell_${dateStr}_close`;
        if (typeof window !== 'undefined' && !localStorage.getItem(key)) {
          localStorage.setItem(key, 'true');
          triggerBell('close', `${closeHour}:00 PM ET Cierre Oficial (15:00 Lima)`);
        }
      }
    }, 1000);

    return () => clearInterval(timer);
  }, [triggerBell]);

  // Supplementary backend status poller (every 15 seconds)
  useEffect(() => {
    let isInitialCheck = true;
    const checkBackendStatus = async () => {
      try {
        const res = await fetch(`/api/v1/stocks/market-status?t=${Date.now()}`);
        if (!res.ok) return;
        const data = await res.json();
        
        // Skip first boot to avoid false bell triggers
        if (isInitialCheck) {
          isInitialCheck = false;
          prevIsOpenRef.current = data.is_open;
          return;
        }

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
    const interval = setInterval(checkBackendStatus, 15000);
    return () => clearInterval(interval);
  }, [triggerBell]);

  // Real-time Audio Listener for STOCKS & OPTIONS Order Fills (Thinkorswim Ding/Chimes)
  useEffect(() => {
    // Handler for a filled stock order
    const handleStockOrderFill = async (order: any) => {
      if (!order || order.status !== 'filled') return;
      const idStr = String(order.id);
      if (knownFilledOrdersRef.current.has(idStr)) return;
      knownFilledOrdersRef.current.add(idStr);

      const isBuy = String(order.direction || '').toLowerCase() === 'buy';
      const isOption = Boolean(order.target_band?.startsWith('OPT:') || order.rule_code?.includes('OPTION'));

      await playOrderSound(isBuy ? 'buy' : 'close', {
        symbol: order.ticker,
        shares: order.shares,
        price: order.filled_price || order.limit_price || order.market_price,
        isOption
      });
    };

    // Handler for an option trade fill (open or closed)
    const handleOptionTradeChange = async (trade: any) => {
      if (!trade || !trade.id) return;
      const idStr = String(trade.id);
      const prevStatus = knownOptionTradesRef.current.get(idStr);
      const currentStatus = String(trade.status || '').toLowerCase();

      // Brand new trade opened
      if (!prevStatus && currentStatus === 'open') {
        knownOptionTradesRef.current.set(idStr, currentStatus);
        await playOrderSound('buy', {
          symbol: trade.symbol || trade.ticker || 'OPCIÓN',
          shares: trade.contracts || 1,
          price: trade.entry_price || trade.current_price,
          isOption: true
        });
        return;
      }

      // Existing trade closed / sold
      if (prevStatus === 'open' && currentStatus === 'closed') {
        knownOptionTradesRef.current.set(idStr, 'closed');
        await playOrderSound('close', {
          symbol: trade.symbol || trade.ticker || 'OPCIÓN',
          shares: trade.contracts || 1,
          price: trade.exit_price || trade.entry_price,
          isOption: true
        });
        return;
      }

      knownOptionTradesRef.current.set(idStr, currentStatus);
    };

    // 1. Initial State Seeding (so past trades don't chime on page refresh)
    const seedInitialState = async () => {
      try {
        // Seed Stock Orders
        const { data: stOrders } = await supabase
          .from('stocks_orders')
          .select('id, status')
          .order('created_at', { ascending: false })
          .limit(50);
        (stOrders || []).forEach((o: any) => {
          if (o.status === 'filled') knownFilledOrdersRef.current.add(String(o.id));
        });

        // Seed Option Trades
        const { data: optTrades } = await supabase
          .from('opt_paper_trades')
          .select('id, status')
          .order('entry_time', { ascending: false })
          .limit(50);
        (optTrades || []).forEach((t: any) => {
          knownOptionTradesRef.current.set(String(t.id), String(t.status || '').toLowerCase());
        });

        isFirstCheckRef.current = false;
      } catch (err) {
        console.warn('[MarketBell] Error seeding initial trade states:', err);
        isFirstCheckRef.current = false;
      }
    };

    seedInitialState();

    // 2. Instant Supabase Realtime Subscriptions (zero-delay WebSocket)
    const stockChannel = supabase
      .channel('market-bell-stocks-realtime')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'stocks_orders' }, (payload: any) => {
        if (isFirstCheckRef.current) return;
        const newRecord = payload.new;
        if (newRecord && newRecord.status === 'filled') {
          handleStockOrderFill(newRecord);
        }
      })
      .subscribe();

    const optionsChannel = supabase
      .channel('market-bell-options-realtime')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'opt_paper_trades' }, (payload: any) => {
        if (isFirstCheckRef.current) return;
        const newRecord = payload.new;
        if (newRecord) {
          handleOptionTradeChange(newRecord);
        }
      })
      .subscribe();

    // 3. Fallback Periodic Poller (every 3 seconds in case WebSocket is unavailable)
    const pollInterval = setInterval(async () => {
      if (isFirstCheckRef.current) return;

      try {
        // Poll Stocks Orders
        const { data: recentOrders } = await supabase
          .from('stocks_orders')
          .select('*')
          .eq('status', 'filled')
          .order('created_at', { ascending: false })
          .limit(10);
        (recentOrders || []).forEach((o: any) => handleStockOrderFill(o));

        // Poll Option Trades
        const { data: recentOptions } = await supabase
          .from('opt_paper_trades')
          .select('*')
          .order('entry_time', { ascending: false })
          .limit(10);
        (recentOptions || []).forEach((t: any) => handleOptionTradeChange(t));
      } catch (e) {
        // quiet fallback
      }
    }, 3000);

    return () => {
      supabase.removeChannel(stockChannel);
      supabase.removeChannel(optionsChannel);
      clearInterval(pollInterval);
    };
  }, [playOrderSound]);

  return (
    <MarketBellContext.Provider
      value={{
        enabled,
        setEnabled,
        toggleEnabled,
        volume,
        setVolume,
        soundProfile,
        setSoundProfile,
        availableSounds: AVAILABLE_SOUNDS,
        nycTime,
        nextBell,
        isUnlocked,
        unlockAudio,
        testBell,
        playOrderSound,
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
