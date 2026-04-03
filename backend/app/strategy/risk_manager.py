import logging
from datetime import datetime, timedelta
from app.execution.binance_connector import get_client, get_account_balance
from app.workers.alerts_service import send_kill_switch_alert

def activar_kill_switch(supabase, reason: str):
    try:
        # 1. Actualizar risk_config
        supabase.table('risk_config').update({
            'kill_switch_triggered': True,
            'bot_active': False
        }).eq('id', 1).execute() # assuming ID 1 for config
        
        # 2. Insertar en alert_events
        supabase.table('alert_events').insert({
            'event_type': 'kill_switch',
            'severity': 'critical',
            'message': f'KILL SWITCH ACTIVADO: {reason}',
            'telegram_sent': False, # Will be handled by alert service
            'email_sent': False
        }).execute()
        
        # 3. Intentar cerrar todas las posiciones abiertas
        from app.execution.order_manager import close_all_positions
        client = get_client()
        close_all_positions(supabase, client)
        
        # 4. Enviar alerta
        send_kill_switch_alert(reason)
        
        logging.critical(f"KILL SWITCH TRIGGERED: {reason}")
    except Exception as e:
        logging.error(f"Error activating kill switch: {e}")

def check_daily_loss_at_cycle_start(risk_config: dict, supabase):
    try:
        today_start = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()

        daily_pnl = supabase.table('positions') \
            .select('realized_pnl') \
            .eq('status', 'closed') \
            .gte('closed_at', today_start) \
            .execute()

        total_daily_loss = sum(
            float(p['realized_pnl']) 
            for p in daily_pnl.data 
            if float(p['realized_pnl']) < 0
        )

        client = get_client()
        balance = get_account_balance(client, 'USDT')
        max_daily_loss_pct = float(risk_config.get('max_daily_loss_pct', 5.0))
        max_daily_loss_usdt = balance * (max_daily_loss_pct / 100)

        if abs(total_daily_loss) >= max_daily_loss_usdt:
            activar_kill_switch(supabase, f'Daily loss limit reached: ${abs(total_daily_loss):.2f}')
            return False
            
        return True
    except Exception as e:
        logging.error(f"Error checking daily loss: {e}")
        return True

def validate_signal(
    signal: dict,
    oco_params: dict,
    risk_config: dict,
    supabase_client
) -> dict:
    
    # CHECK 1 — Bot activo:
    if not risk_config.get('bot_active', True):
        return { 'approved': False, 'reason': 'BOT_INACTIVE' }

    # CHECK 2 — Kill switch no activado:
    if risk_config.get('kill_switch_triggered', False):
        return { 'approved': False, 'reason': 'KILL_SWITCH_ACTIVE' }

    # CHECK 3 — No exceder trades abiertos simultáneos:
    try:
        open_positions = supabase_client.table('positions') \
            .select('id', count='exact') \
            .eq('status', 'open') \
            .execute()
        
        max_open = int(risk_config.get('max_open_trades', 3))
        current_open = open_positions.count or 0

        if current_open >= max_open:
            return { 'approved': False, 'reason': f'MAX_OPEN_TRADES_REACHED ({current_open}/{max_open})' }
    except Exception as e:
        logging.error(f"Error checking open trades: {e}")
        current_open = 0 # Fallback

    # CHECK 4 — No operar el mismo símbolo dos veces:
    try:
        existing = supabase_client.table('positions') \
            .select('id') \
            .eq('symbol', signal['symbol']) \
            .eq('status', 'open') \
            .execute()
            
        if existing.data:
            return { 'approved': False, 'reason': f'SYMBOL_ALREADY_OPEN: {signal["symbol"]}' }
    except Exception as e:
        logging.error(f"Error checking existing symbol: {e}")

    # CHECK 5 — Pérdida diaria no superada (ya se checa al inicio del ciclo, pero re-validamos por si acaso):
    # (Ya está en check_daily_loss_at_cycle_start)
    
    # CHECK 6 — Verificar pérdida horaria (kill switch proactivo):
    try:
        one_hour_ago = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        hourly_pnl = supabase_client.table('positions') \
            .select('realized_pnl') \
            .eq('status', 'closed') \
            .gte('closed_at', one_hour_ago) \
            .execute()

        total_hourly_loss = sum(
            float(p['realized_pnl'])
            for p in hourly_pnl.data
            if float(p['realized_pnl']) < 0
        )

        client = get_client()
        balance = get_account_balance(client, 'USDT')
        kill_switch_pct = float(risk_config.get('kill_switch_loss_pct', 3.0))
        kill_switch_usdt = balance * (kill_switch_pct / 100)

        if abs(total_hourly_loss) >= kill_switch_usdt:
            activar_kill_switch(supabase_client, f'Hourly kill switch triggered: ${abs(total_hourly_loss):.2f}')
            return { 'approved': False, 'reason': 'KILL_SWITCH_HOURLY_TRIGGERED' }
    except Exception as e:
        logging.error(f"Error checking hourly loss: {e}")

    return {
        'approved': True,
        'reason': 'ALL_CHECKS_PASSED',
        'balance_usdt': balance if 'balance' in locals() else 0,
        'daily_loss_usdt': 0, # Placeholder
        'open_positions': current_open
    }
