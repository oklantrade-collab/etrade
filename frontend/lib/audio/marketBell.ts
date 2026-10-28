/**
 * marketBell.ts - High-fidelity Wall Street / NYSE Market Bell Audio Engine
 * Supports HTML5 Audio with pre-rendered WAV assets and a Web Audio API synthesizer fallback.
 */

class MarketBellAudioEngine {
  private audioCtx: AudioContext | null = null;
  private isUnlocked: boolean = false;
  private volume: number = 0.85;

  constructor() {
    if (typeof window !== 'undefined') {
      try {
        const savedVol = localStorage.getItem('etrade_bell_volume');
        if (savedVol !== null) {
          this.volume = Math.max(0, Math.min(1, parseFloat(savedVol)));
        }
      } catch (e) {
        // ignore
      }
      this.setupUnlockListeners();
    }
  }

  /**
   * Set up interaction listeners to unlock AudioContext according to modern browser autoplay policies
   */
  private setupUnlockListeners() {
    const unlock = () => {
      this.unlockAudio();
      window.removeEventListener('pointerdown', unlock);
      window.removeEventListener('keydown', unlock);
      window.removeEventListener('touchstart', unlock);
    };

    window.addEventListener('pointerdown', unlock, { once: true, passive: true });
    window.addEventListener('keydown', unlock, { once: true, passive: true });
    window.addEventListener('touchstart', unlock, { once: true, passive: true });
  }

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
      this.isUnlocked = true;
      return true;
    } catch (e) {
      console.warn('[MarketBell] Could not initialize AudioContext:', e);
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

  public getIsUnlocked(): boolean {
    return this.isUnlocked;
  }

  /**
   * Play the Wall Street / NYSE bell sound
   * @param type 'open' (vigorous rapid NYSE opening bell) or 'close' (closing bell cadence)
   */
  public async play(type: 'open' | 'close' = 'open'): Promise<boolean> {
    if (this.volume <= 0) return false;

    // 1. Try playing audio file from /sounds/
    const soundPath = type === 'close' 
      ? '/sounds/market-bell-close.wav' 
      : '/sounds/market-bell-open.wav';

    try {
      const audio = new Audio(soundPath);
      audio.volume = this.volume;
      const playPromise = audio.play();
      if (playPromise !== undefined) {
        await playPromise;
        return true;
      }
    } catch (err) {
      console.warn('[MarketBell] Audio element playback was blocked or failed, falling back to Web Audio API synthesizer:', err);
    }

    // 2. Synthesizer fallback using Web Audio API
    return this.synthesizeBell(type);
  }

  /**
   * Synthesize an authentic acoustic cast brass bell (NYSE-style) using Web Audio API
   */
  public synthesizeBell(type: 'open' | 'close' = 'open'): boolean {
    try {
      this.unlockAudio();
      if (!this.audioCtx) return false;

      const ctx = this.audioCtx;
      const now = ctx.currentTime;
      const baseFreq = type === 'close' ? 760 : 830;
      const strikeInterval = type === 'close' ? 0.16 : 0.135;
      const strikeCount = type === 'close' ? 18 : 22;

      // Partials of Edwards 14-inch brass bell
      const partials = [
        { ratio: 0.50, gain: 0.40, decay: 2.8 },
        { ratio: 1.00, gain: 0.70, decay: 2.4 },
        { ratio: 1.19, gain: 0.50, decay: 1.8 },
        { ratio: 1.51, gain: 0.35, decay: 1.6 },
        { ratio: 2.00, gain: 0.40, decay: 1.3 },
        { ratio: 2.74, gain: 0.25, decay: 0.9 },
        { ratio: 3.85, gain: 0.18, decay: 0.6 },
      ];

      const masterGain = ctx.createGain();
      masterGain.gain.setValueAtTime(this.volume * 0.9, now);
      masterGain.connect(ctx.destination);

      for (let s = 0; s < strikeCount; s++) {
        const isLast = s === strikeCount - 1;
        const strikeTime = now + (s * strikeInterval);
        const strength = isLast ? 1.3 : 0.95;
        const decayMult = isLast ? 2.0 : 0.45;

        // Strike impact click
        const clickOsc = ctx.createOscillator();
        const clickGain = ctx.createGain();
        clickOsc.type = 'triangle';
        clickOsc.frequency.setValueAtTime(baseFreq * 3.5, strikeTime);
        clickOsc.frequency.exponentialRampToValueAtTime(100, strikeTime + 0.02);

        clickGain.gain.setValueAtTime(0.3 * strength, strikeTime);
        clickGain.gain.exponentialRampToValueAtTime(0.001, strikeTime + 0.02);

        clickOsc.connect(clickGain);
        clickGain.connect(masterGain);
        clickOsc.start(strikeTime);
        clickOsc.stop(strikeTime + 0.025);

        // Acoustic partials
        partials.forEach(p => {
          const osc = ctx.createOscillator();
          const gainNode = ctx.createGain();

          osc.type = 'sine';
          // Slight natural detune for warmth
          osc.frequency.setValueAtTime(baseFreq * p.ratio * (1 + (Math.random() - 0.5) * 0.004), strikeTime);

          const decay = p.decay * decayMult;
          gainNode.gain.setValueAtTime(p.gain * strength * 0.3, strikeTime);
          gainNode.gain.exponentialRampToValueAtTime(0.0001, strikeTime + decay);

          osc.connect(gainNode);
          gainNode.connect(masterGain);

          osc.start(strikeTime);
          osc.stop(strikeTime + decay + 0.05);
        });
      }

      return true;
    } catch (e) {
      console.error('[MarketBell] Synthesis failed:', e);
      return false;
    }
  }
}

export const marketBell = new MarketBellAudioEngine();
