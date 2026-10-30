/**
 * marketBell.ts - High-fidelity Wall Street / Thinkorswim Market Bell Audio Engine
 * Supports HTML5 Audio with Thinkorswim (Charles Schwab) authentic sound assets
 * and a Web Audio API synthesizer fallback.
 */

export type BellSoundProfile = 'tos-session' | 'tos-bell' | 'tos-chimes' | 'tos-ring' | 'tos-ding';

export interface SoundOption {
  id: BellSoundProfile;
  name: string;
  description: string;
  file: string;
}

export const AVAILABLE_SOUNDS: SoundOption[] = [
  {
    id: 'tos-session',
    name: 'Thinkorswim (Schwab) Campana Bursátil Oficial',
    description: 'Sonido oficial de inicio y cierre de sesión de Thinkorswim (BeginTrading/EndTrading)',
    file: '/sounds/market-bell-open.wav',
  },
  {
    id: 'tos-bell',
    name: 'Thinkorswim Campana Clásica (Bell)',
    description: 'Campana de bronce clásica de Thinkorswim de alta fidelidad',
    file: '/sounds/tos-bell.wav',
  },
  {
    id: 'tos-chimes',
    name: 'Thinkorswim Chimes',
    description: 'Campanadas armónicas suaves de Thinkorswim',
    file: '/sounds/tos-chimes.wav',
  },
  {
    id: 'tos-ring',
    name: 'Thinkorswim Ring',
    description: 'Timbre resonante de Thinkorswim',
    file: '/sounds/tos-ring.wav',
  },
  {
    id: 'tos-ding',
    name: 'Thinkorswim Ding',
    description: 'Aviso sonoro simple de Thinkorswim',
    file: '/sounds/tos-ding.wav',
  },
];

class MarketBellAudioEngine {
  private audioCtx: AudioContext | null = null;
  private isUnlocked: boolean = false;
  private volume: number = 0.85;
  private soundProfile: BellSoundProfile = 'tos-session';
  private preloadedAudios: Map<string, HTMLAudioElement> = new Map();

  constructor() {
    if (typeof window !== 'undefined') {
      try {
        const savedVol = localStorage.getItem('etrade_bell_volume');
        if (savedVol !== null) {
          this.volume = Math.max(0, Math.min(1, parseFloat(savedVol)));
        }
        const savedProfile = localStorage.getItem('etrade_bell_sound_profile') as BellSoundProfile;
        if (savedProfile && AVAILABLE_SOUNDS.some(s => s.id === savedProfile)) {
          this.soundProfile = savedProfile;
        }
      } catch (e) {
        // ignore
      }
      this.setupUnlockListeners();
      this.preloadSounds();
    }
  }

  /**
   * Preload audio files so they are instant and decoded ahead of time
   */
  public preloadSounds() {
    if (typeof window === 'undefined') return;
    const files = [
      '/sounds/market-bell-open.wav',
      '/sounds/market-bell-close.wav',
      '/sounds/tos-bell.wav',
      '/sounds/tos-chimes.wav',
      '/sounds/tos-ring.wav',
      '/sounds/tos-ding.wav',
    ];

    files.forEach((path) => {
      try {
        if (!this.preloadedAudios.has(path)) {
          const audio = new Audio();
          audio.src = path;
          audio.preload = 'auto';
          this.preloadedAudios.set(path, audio);
        }
      } catch (e) {
        // ignore
      }
    });
  }

  /**
   * Set up interaction listeners to unlock AudioContext and HTML5 Audio
   * according to modern browser autoplay policies (Chrome, Edge, Safari, Firefox).
   */
  private setupUnlockListeners() {
    const unlock = () => {
      this.unlockAudio();
    };

    const events = ['pointerdown', 'mousedown', 'keydown', 'touchstart', 'click', 'scroll'];
    events.forEach((evt) => {
      window.addEventListener(evt, unlock, { capture: true, passive: true });
    });

    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
          this.unlockAudio();
        }
      });
    }
  }

  /**
   * Unlocks both the Web Audio API AudioContext and primes HTML5 audio
   */
  public unlockAudio(): boolean {
    try {
      if (!this.audioCtx) {
        const AudioCtxClass = window.AudioContext || (window as any).webkitAudioContext;
        if (AudioCtxClass) {
          this.audioCtx = new AudioCtxClass();
        }
      }

      if (this.audioCtx && this.audioCtx.state === 'suspended') {
        this.audioCtx.resume();
      }

      // Prime an audio element with 1-sample silent sound to unlock HTML5 Audio autoplay
      if (!this.isUnlocked) {
        const silentAudio = new Audio(
          'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA'
        );
        silentAudio.volume = 0;
        silentAudio.play().then(() => {
          this.isUnlocked = true;
        }).catch(() => {
          // Will be unlocked on next user action
        });
      }

      this.isUnlocked = true;
      return true;
    } catch (e) {
      console.warn('[MarketBell] Could not initialize or unlock audio:', e);
      return false;
    }
  }

  public setVolume(vol: number) {
    this.volume = Math.max(0, Math.min(1, vol));
    try {
      localStorage.setItem('etrade_bell_volume', this.volume.toString());
    } catch (e) {
      // ignore
    }
  }

  public getVolume(): number {
    return this.volume;
  }

  public setSoundProfile(profile: BellSoundProfile) {
    this.soundProfile = profile;
    try {
      localStorage.setItem('etrade_bell_sound_profile', profile);
    } catch (e) {
      // ignore
    }
  }

  public getSoundProfile(): BellSoundProfile {
    return this.soundProfile;
  }

  public getIsUnlocked(): boolean {
    return this.isUnlocked;
  }

  /**
   * Play the market bell sound
   * @param type 'open' (session open) or 'close' (session close)
   * @param overrideProfile Optional specific sound profile to preview
   */
  public async play(type: 'open' | 'close' = 'open', overrideProfile?: BellSoundProfile): Promise<boolean> {
    if (this.volume <= 0) return false;

    const profile = overrideProfile || this.soundProfile;
    let soundPath: string;

    if (profile === 'tos-session') {
      soundPath = type === 'close' 
        ? '/sounds/market-bell-close.wav' 
        : '/sounds/market-bell-open.wav';
    } else {
      const match = AVAILABLE_SOUNDS.find(s => s.id === profile);
      soundPath = match ? match.file : '/sounds/market-bell-open.wav';
    }

    // 1. Try playing preloaded or new HTML5 Audio
    try {
      const audio = new Audio(soundPath);
      audio.volume = this.volume;
      const playPromise = audio.play();
      if (playPromise !== undefined) {
        await playPromise;
        return true;
      }
    } catch (err) {
      console.warn('[MarketBell] Audio element playback blocked or failed, falling back to Web Audio API synthesizer:', err);
    }

    // 2. Synthesizer fallback using Web Audio API tuned to Thinkorswim's frequencies
    return this.synthesizeBell(type);
  }

  /**
   * Synthesize an authentic acoustic Thinkorswim brass bell chime (~1178 Hz & 663 Hz) using Web Audio API
   */
  public synthesizeBell(type: 'open' | 'close' = 'open'): boolean {
    try {
      this.unlockAudio();
      if (!this.audioCtx) return false;

      const ctx = this.audioCtx;
      const now = ctx.currentTime;
      
      // Thinkorswim Bell dominant spectral frequencies: 1178 Hz fundamental, 663 Hz harmonic, 2356 Hz overtone
      const baseFreq = type === 'close' ? 1103 : 1178;
      const subFreq = type === 'close' ? 620 : 663;

      const masterGain = ctx.createGain();
      masterGain.gain.setValueAtTime(this.volume * 0.9, now);
      masterGain.connect(ctx.destination);

      // Strike count: 3 pleasant chimes for session bell, or 1 chime for simple alert
      const strikes = type === 'open' ? [0, 0.35, 0.72] : [0, 0.40, 0.85, 1.30];

      strikes.forEach((delay, idx) => {
        const strikeTime = now + delay;
        const decayTime = idx === strikes.length - 1 ? 2.2 : 0.8;

        // 1. Strike transient attack (impact ping)
        const clickOsc = ctx.createOscillator();
        const clickGain = ctx.createGain();
        clickOsc.type = 'triangle';
        clickOsc.frequency.setValueAtTime(baseFreq * 2.8, strikeTime);
        clickOsc.frequency.exponentialRampToValueAtTime(150, strikeTime + 0.025);

        clickGain.gain.setValueAtTime(0.25, strikeTime);
        clickGain.gain.exponentialRampToValueAtTime(0.001, strikeTime + 0.025);

        clickOsc.connect(clickGain);
        clickGain.connect(masterGain);
        clickOsc.start(strikeTime);
        clickOsc.stop(strikeTime + 0.03);

        // 2. Fundamental Thinkorswim Bell tone (1178 Hz)
        const osc1 = ctx.createOscillator();
        const gain1 = ctx.createGain();
        osc1.type = 'sine';
        osc1.frequency.setValueAtTime(baseFreq, strikeTime);
        gain1.gain.setValueAtTime(0.45, strikeTime);
        gain1.gain.exponentialRampToValueAtTime(0.0001, strikeTime + decayTime);
        osc1.connect(gain1);
        gain1.connect(masterGain);
        osc1.start(strikeTime);
        osc1.stop(strikeTime + decayTime + 0.05);

        // 3. Sub-harmonic body tone (663 Hz)
        const osc2 = ctx.createOscillator();
        const gain2 = ctx.createGain();
        osc2.type = 'sine';
        osc2.frequency.setValueAtTime(subFreq, strikeTime);
        gain2.gain.setValueAtTime(0.35, strikeTime);
        gain2.gain.exponentialRampToValueAtTime(0.0001, strikeTime + decayTime);
        osc2.connect(gain2);
        gain2.connect(masterGain);
        osc2.start(strikeTime);
        osc2.stop(strikeTime + decayTime + 0.05);

        // 4. Upper harmonic shimmer (2356 Hz)
        const osc3 = ctx.createOscillator();
        const gain3 = ctx.createGain();
        osc3.type = 'sine';
        osc3.frequency.setValueAtTime(baseFreq * 2.0, strikeTime);
        gain3.gain.setValueAtTime(0.18, strikeTime);
        gain3.gain.exponentialRampToValueAtTime(0.0001, strikeTime + (decayTime * 0.6));
        osc3.connect(gain3);
        gain3.connect(masterGain);
        osc3.start(strikeTime);
        osc3.stop(strikeTime + (decayTime * 0.6) + 0.05);
      });

      return true;
    } catch (e) {
      console.error('[MarketBell] Synthesis failed:', e);
      return false;
    }
  }

  /**
   * Play Thinkorswim confirmation sound when an order is executed by broker (Stock or Option)
   * @param type 'buy' (Ding) or 'sell'/'close' (Chimes)
   */
  public async playOrderSound(type: 'buy' | 'sell' | 'close' = 'buy'): Promise<boolean> {
    if (this.volume <= 0) return false;
    this.unlockAudio();

    const isBuy = type === 'buy';
    const soundPath = isBuy ? '/sounds/tos-ding.wav' : '/sounds/tos-chimes.wav';

    // 1. Try HTML5 Audio asset
    try {
      const audio = new Audio(soundPath);
      audio.volume = this.volume;
      const playPromise = audio.play();
      if (playPromise !== undefined) {
        await playPromise;
        return true;
      }
    } catch (err) {
      console.warn(`[MarketBell] Order sound playback blocked (${type}), using synthesizer fallback:`, err);
    }

    // 2. Synthesizer fallback tuned to Thinkorswim's Ding / Chimes
    return this.synthesizeOrderFill(isBuy);
  }

  /**
   * Synthesize Thinkorswim Ding (Buy) or Chimes (Close/Sell)
   */
  public synthesizeOrderFill(isBuy: boolean): boolean {
    try {
      this.unlockAudio();
      if (!this.audioCtx && typeof window !== 'undefined') {
        const AudioCtxClass = window.AudioContext || (window as any).webkitAudioContext;
        if (AudioCtxClass) {
          this.audioCtx = new AudioCtxClass();
        }
      }
      if (!this.audioCtx) return false;

      const ctx = this.audioCtx;
      if (ctx.state === 'suspended') {
        ctx.resume();
      }
      const now = ctx.currentTime;

      const masterGain = ctx.createGain();
      masterGain.gain.setValueAtTime(this.volume * 0.9, now);
      masterGain.connect(ctx.destination);

      if (isBuy) {
        // Thinkorswim BUY Ding: 1318.5 Hz (E6) with rapid decay
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(1318.5, now);
        gain.gain.setValueAtTime(0.5, now);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.85);

        osc.connect(gain);
        gain.connect(masterGain);
        osc.start(now);
        osc.stop(now + 0.9);
      } else {
        // Thinkorswim SELL Chimes: Descending melodic chord (880Hz -> 659Hz)
        [880, 659.25].forEach((freq, idx) => {
          const t = now + idx * 0.18;
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.type = 'sine';
          osc.frequency.setValueAtTime(freq, t);
          gain.gain.setValueAtTime(0.4, t);
          gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.9);

          osc.connect(gain);
          gain.connect(masterGain);
          osc.start(t);
          osc.stop(t + 0.95);
        });
      }
      return true;
    } catch (e) {
      console.error('[MarketBell] Order synthesis failed:', e);
      return false;
    }
  }
}

export const marketBell = new MarketBellAudioEngine();
