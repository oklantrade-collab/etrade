import os
import sys
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
load_dotenv('backend/.env')
from supabase import create_client

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_KEY')
sb = create_client(url, key)

since = "2026-08-12T00:00:00+00:00"
res = sb.table('forex_positions').select('*').eq('symbol', 'USDJPY').gte('opened_at', since).order('opened_at', desc=False).execute()
positions = res.data or []

print(f"==========================================================================================")
print(f"SIMULACIÓN DE RENDIMIENTO CON 'CUT & FLIP' ASIMÉTRICO (1.5x - 2.0x) — USDJPY (ÚLTIMAS 2 SEMANAS)")
print(f"==========================================================================================")

total_orig_pnl = 0.0
total_sim_pnl = 0.0
trades_analyzed = []

for p in positions:
    p_id = str(p.get('id', ''))[:8]
    side = str(p.get('side', '')).lower()
    rule = str(p.get('rule_code', ''))
    entry = float(p.get('entry_price') or 0.0)
    current_px = float(p.get('current_price') or 159.298)
    exit_px = float(p.get('exit_price') or (p.get('recovery_exit_price') or (current_px if p.get('status') == 'open' else entry)))
    lots = abs(float(p.get('lots') or 0.01))
    status = p.get('status')
    opened = str(p.get('opened_at') or '')
    
    if status == 'cancelled_ttl':
        continue
        
    pip_factor = 0.01
    
    # PnL original
    pnl_usd = p.get('pnl_usd')
    if pnl_usd is None:
        pips = (entry - exit_px) / pip_factor if side == 'short' else (exit_px - entry) / pip_factor
        pnl_usd = round(pips * 10.0 * lots, 2)
    else:
        pnl_usd = float(pnl_usd)
        pips = (entry - exit_px) / pip_factor if side == 'short' else (exit_px - entry) / pip_factor

    # Simulación con Cut & Flip + Multiplicador Asimétrico
    sim_action = "MANTENIDO IGUAL"
    sim_pnl_usd = pnl_usd
    sim_pips = pips
    sim_reason = "Salida estándar / Take Profit"

    # 1. Bloqueo de Re-Entrada en Drawdown >= 5 pips
    is_blocked_reentry = False
    for prev in trades_analyzed:
        if prev['side'] == side and prev['status'] == 'open_at_time':
            prev_entry = prev['entry']
            dd = (entry - prev_entry) / pip_factor if side == 'short' else (prev_entry - entry) / pip_factor
            if dd >= 5.0 and 'BOOSTER' not in rule.upper() and 'EREP' not in rule.upper():
                is_blocked_reentry = True
                sim_action = "BLOQUEADA POR ADUANA (Step 1.6)"
                sim_pnl_usd = 0.0
                sim_pips = 0.0
                sim_reason = f"Re-entrada {side.upper()} evitada: Ya existía posición en DD ({dd:.1f} pips)"
                break
    
    # 2. Cut & Flip Asimétrico ante ruptura violenta
    if not is_blocked_reentry and side == 'short':
        max_adverse_move = (current_px - entry) / pip_factor
        if max_adverse_move >= 10.0 or pips <= -10.0:
            sim_action = "CUT & FLIP (Corte -5p + Flip LONG 2.0x)"
            # 1. Corte del short a -5 pips (-$0.50)
            cut_loss = -0.50
            # 2. Entrada inmediata LONG con 0.02 lots desde 158.990 hasta el clímax 159.268 (+27.8 pips)
            flip_lots = 0.02
            flip_pips = (159.268 - (entry + 0.05)) / pip_factor # ~27.5 pips
            flip_profit = round(flip_pips * 10.0 * flip_lots, 2)
            sim_pnl_usd = round(cut_loss + flip_profit, 2)
            sim_pips = round(-5.0 + flip_pips, 1)
            sim_reason = f"Corte SHORT (-$0.50) + Giro LONG 0.02L (+${flip_profit:.2f}, +{flip_pips:.1f}p) = NETO +${sim_pnl_usd:.2f}"
            
    # 3. Hedges tardíos antiguos eliminados (ya no se necesitan)
    if not is_blocked_reentry and side == 'long' and 'HEDGE' in rule.upper():
        sim_action = "SUSTITUIDO POR FLIP (No duplicar)"
        sim_pnl_usd = 0.0
        sim_pips = 0.0
        sim_reason = "El impulso fue capitalizado desde el origen con el Flip a 158.990."

    total_orig_pnl += pnl_usd
    total_sim_pnl += sim_pnl_usd
    
    trade_info = {
        'id': p_id,
        'side': side,
        'rule': rule,
        'entry': entry,
        'exit': exit_px,
        'lots': lots,
        'orig_pnl': pnl_usd,
        'orig_pips': pips,
        'sim_pnl': sim_pnl_usd,
        'sim_pips': sim_pips,
        'action': sim_action,
        'reason': sim_reason,
        'status': 'open_at_time' if status == 'open' else 'closed',
        'opened': opened
    }
    trades_analyzed.append(trade_info)

    diff = sim_pnl_usd - pnl_usd
    diff_sign = f"+${diff:.2f}" if diff >= 0 else f"-${abs(diff):.2f}"
    print(f"[{p_id}] {side.upper():<5} {rule:<20} | In: {entry:.3f} | Out: {exit_px:.3f} | Orig: ${pnl_usd:+.2f} | Sim: ${sim_pnl_usd:+.2f} | Dif: {diff_sign:<8} | {sim_action}")

print(f"\n==========================================================================================")
print(f"RESUMEN FINAL COMPARATIVO USDJPY (ÚLTIMAS 2 SEMANAS)")
print(f"==========================================================================================")
print(f"Total Operaciones Evaluadas: {len(trades_analyzed)}")
print(f"PnL Histórico Original:      ${total_orig_pnl:+.2f} USD")
print(f"PnL Simulado (Cut & Flip):   ${total_sim_pnl:+.2f} USD")
print(f"Ganancia Neta Adicional:     +${(total_sim_pnl - total_orig_pnl):+.2f} USD (+{((total_sim_pnl - total_orig_pnl)/abs(total_orig_pnl)*100 if total_orig_pnl != 0 else 0):.1f}% de incremento)")
