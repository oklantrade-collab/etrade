import os
import wave
import numpy as np

def generate_bell_sound(filepath, duration=5.0, strike_count=20, strike_interval=0.14, base_freq=820.0, is_close=False):
    sr = 44100
    total_samples = int(duration * sr)
    buffer = np.zeros(total_samples, dtype=np.float32)
    
    # Partials of Edwards 14-inch NYSE cast brass bell
    partials = [
        (0.50, 0.40, 3.0),   # Hum tone
        (1.00, 0.70, 2.6),   # Strike tone / prime
        (1.19, 0.50, 2.0),   # Minor third (tierce)
        (1.51, 0.40, 1.8),   # Fifth (quint)
        (2.00, 0.45, 1.5),   # Octave (nominal)
        (2.74, 0.30, 1.0),   # High mode 1
        (3.85, 0.22, 0.7),   # High mode 2
        (5.15, 0.15, 0.4),   # Metallic transient mode
    ]
    
    # Calculate strike times
    np.random.seed(42)
    if is_close:
        # Closing bell pattern: 3 distinct warning chimes, then continuous ringing, then final grand toll
        strike_times = [0.0, 0.45, 0.9]
        for i in range(14):
            strike_times.append(1.4 + i * 0.14 + (np.random.rand() - 0.5) * 0.005)
    elif strike_count == 1:
        strike_times = [0.0]
    else:
        # Opening bell: energetic rapid ringing (NYSE opening clapper)
        strike_times = []
        for i in range(strike_count):
            strike_times.append(i * strike_interval + (np.random.rand() - 0.5) * 0.004)
            
    for s_idx, st in enumerate(strike_times):
        start_idx = int(st * sr)
        if start_idx < 0 or start_idx >= total_samples:
            continue
        is_last = (s_idx == len(strike_times) - 1)
        strength = 1.3 if is_last else 0.95
        decay_mult = 2.0 if is_last else 0.45
        
        # Transient hammer hit (metal on brass click)
        trans_len = min(int(0.02 * sr), total_samples - start_idx)
        if trans_len > 0:
            t_trans = np.linspace(0, trans_len / sr, trans_len, endpoint=False, dtype=np.float32)
            trans_env = np.exp(-t_trans / 0.003, dtype=np.float32) * (strength * 0.4)
            trans_noise = (np.random.uniform(-1.0, 1.0, trans_len).astype(np.float32)) * trans_env
            buffer[start_idx : start_idx + trans_len] += trans_noise
            
        # Add modal partials
        rem_len = total_samples - start_idx
        t = np.linspace(0, rem_len / sr, rem_len, endpoint=False)
        
        # Acoustic shimmer / beating
        shimmer = 1.0 + 0.08 * np.sin(2.0 * np.pi * 4.0 * t)
        
        strike_signal = np.zeros(rem_len, dtype=np.float32)
        for ratio, amp, base_decay in partials:
            freq = base_freq * ratio
            decay = base_decay * decay_mult
            env = np.exp(-t / decay) * (amp * strength)
            strike_signal += (env * shimmer * np.sin(2.0 * np.pi * freq * t)).astype(np.float32)
            
        buffer[start_idx:] += strike_signal

    # Normalize to avoid clipping
    peak = np.max(np.abs(buffer))
    if peak > 0:
        buffer = buffer * (0.88 / peak)
        
    # Convert to 16-bit PCM
    pcm_data = (buffer * 32767).astype(np.int16).tobytes()
    
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with wave.open(filepath, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(pcm_data)
        
    print(f"Generated: {filepath} ({len(pcm_data)} bytes)")

if __name__ == '__main__':
    # 1. Opening Bell (Campana de Apertura)
    generate_bell_sound('frontend/public/sounds/market-bell-open.wav', duration=5.2, strike_count=22, strike_interval=0.135, base_freq=830.0, is_close=False)
    # 2. Closing Bell (Campana de Cierre)
    generate_bell_sound('frontend/public/sounds/market-bell-close.wav', duration=5.2, strike_count=18, strike_interval=0.14, base_freq=760.0, is_close=True)
    # 3. Single Bell Chime
    generate_bell_sound('frontend/public/sounds/market-bell-chime.wav', duration=3.5, strike_count=1, strike_interval=0.0, base_freq=800.0, is_close=False)
