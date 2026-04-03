from app.core.supabase_client import get_supabase
from app.workers.alerts_service import send_telegram_message
from datetime import datetime, timezone, timedelta
from app.core.logger import log_info, log_error

# In-memory storage for alert throttling: {key: last_alert_time}
# Key formats: 'ev_{rule_code}', 'sl3_{rule_code}'
BOT_STATE_PERF = {}

async def check_performance_alerts():
    """
    Entregable 2 - Fase 1: Alertas automáticas de performance
    Ejecutado al final de cada ciclo de 15m.
    """
    try:
        supabase = get_supabase()
        
        # 1. Obtener todos los trades de paper trading para análisis
        result = supabase.table('paper_trades') \
            .select('*') \
            .eq('mode', 'paper') \
            .execute()
        
        trades = result.data or []
        if not trades:
            return
            
        # Agrupar por rule_code
        rule_groups = {}
        for t in trades:
            rc = t.get('rule_code')
            if not rc: continue
            if rc not in rule_groups:
                rule_groups[rc] = []
            rule_groups[rc].append(t)
            
        now = datetime.now(timezone.utc)
        
        for rule_code, group_trades in rule_groups.items():
            # Ordenar por fecha de cierre: más reciente primero
            # Usamos closed_at o created_at como fallback
            curr_trades = sorted(
                group_trades, 
                key=lambda x: x.get('closed_at') or x.get('created_at') or '', 
                reverse=True
            )
            
            total_trades = len(curr_trades)
            
            # --- ALERTA 1: EV Negativo ---
            if total_trades >= 10:
                wins = [t for t in curr_trades if float(t.get('total_pnl_usd') or 0) > 0]
                losses = [t for t in curr_trades if float(t.get('total_pnl_usd') or 0) <= 0]
                
                win_rate = len(wins) / total_trades
                avg_win_pct = sum(float(t.get('total_pnl_pct') or 0) for t in wins) / len(wins) if wins else 0
                avg_loss_pct = abs(sum(float(t.get('total_pnl_pct') or 0) for t in losses) / len(losses)) if losses else 0
                
                ev = (win_rate * avg_win_pct) - ((1 - win_rate) * avg_loss_pct)
                
                if ev < 0:
                    alert_key = f"ev_{rule_code}"
                    last_alert = BOT_STATE_PERF.get(alert_key)
                    if not last_alert or (now - last_alert >= timedelta(hours=4)):
                        mensaje = f"""⚠️ *ALERTA PERFORMANCE*
Regla `{rule_code}`: EV={ev:.4f} (negativo)
Win rate: {win_rate:.1%} | Trades: {total_trades}
Considerar desactivar en Rule Engine."""
                        await send_telegram_message(mensaje)
                        BOT_STATE_PERF[alert_key] = now
                        log_info("performance_monitor", f"Alerta EV negativo enviada para rule {rule_code}")

            # --- ALERTA 2: SL Consecutivos ---
            if len(curr_trades) >= 3:
                ultimos_3 = curr_trades[:3]
                todos_perdedores = all(float(t.get('total_pnl_usd') or 0) <= 0 for t in ultimos_3)
                
                if todos_perdedores:
                    alert_key = f"sl3_{rule_code}"
                    last_alert = BOT_STATE_PERF.get(alert_key)
                    if not last_alert or (now - last_alert >= timedelta(hours=4)):
                        mensaje = f"""🔴 *3 SL CONSECUTIVOS — Regla {rule_code}*
Revisar condiciones de mercado actuales."""
                        await send_telegram_message(mensaje)
                        BOT_STATE_PERF[alert_key] = now
                        log_info("performance_monitor", f"Alerta 3 SL consecutivos enviada para rule {rule_code}")

    except Exception as e:
        log_error("performance_monitor", f"Error in check_performance_alerts: {e}")
