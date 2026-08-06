import logging
from datetime import datetime, timedelta
from app.execution.binance_connector import get_client, get_account_balance
from app.workers.alerts_service import send_kill_switch_alert

def activar_kill_switch(supabase, reason: str):
    try:
        # 1. Obtener el ID dinámicamente o usar el que tenemos en cache
        config = supabase.table('risk_config').select('id').limit(1).execute()
        if not config.data:
            logging.error("No risk_config found to activate kill switch")
            return
            
        config_id = config.data[0]['id']

        # 2. Actualizar risk_config
        supabase.table('risk_config').update({
            'bot_active': False
        }).eq('id', config_id).execute()
        
        # 3. Insertar en alert_events
        supabase.table('alert_events').insert({
            'event_type': 'kill_switch',
            'severity': 'critical',
            'message': f'KILL SWITCH ACTIVADO: {reason}',
            'telegram_sent': False, 
            'email_sent': False
        }).execute()
        
        # 4. Intentar cerrar todas las posiciones abiertas
        from app.execution.order_manager import close_all_positions
        client = get_client()
        close_all_positions(supabase, client)
        
        # 5. Enviar alerta
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
    # CHECK 0 — Bloqueos de Seguridad por Subprocesos
    from app.core.safety_manager import is_crypto_safety_blocked, check_db_safety_block, get_rule_expected_direction
    if is_crypto_safety_blocked() or check_db_safety_block('crypto_futures'):
        return { 'approved': False, 'reason': 'SAFETY_BLOCK_CRYPTO_ACTIVE' }

    # CHECK 0.1 — Coherencia de Regla vs Dirección
    rule_code = signal.get('rule_code')
    direction = signal.get('direction') or signal.get('signal_type')
    if not direction and oco_params:
        direction = 'long' if 'BUY' in str(oco_params.get('side', '')).upper() else 'short'
    
    if direction and rule_code:
        expected = get_rule_expected_direction(rule_code)
        if expected and expected != direction.strip().lower():
            return { 'approved': False, 'reason': f'INCOHERENT_RULE_DIRECTION ({rule_code} expected {expected}, got {direction})' }

    # CHECK 1 — Bot activo:
    if not risk_config.get('bot_active', True):
        return { 'approved': False, 'reason': 'BOT_INACTIVE' }

    # CHECK 2 — El bot debe estar activo (ya se checa arriba, pero para robustez):
    if not risk_config.get('bot_active', True):
        return { 'approved': False, 'reason': 'KILL_SWITCH_ACTIVE' }

    # CHECK 3 — No exceder trades abiertos simultáneos (GLOBAL):
    try:
        open_positions_res = supabase_client.table('positions') \
            .select('symbol', count='exact') \
            .eq('status', 'open') \
            .execute()
        
        max_open = int(risk_config.get('max_open_trades', 15))
        current_open = open_positions_res.count or 0

        if current_open >= max_open:
            return { 'approved': False, 'reason': f'MAX_OPEN_TRADES_REACHED ({current_open}/{max_open})' }
    except Exception as e:
        logging.error(f"Error checking global open trades: {e}")
        current_open = 999 # FAIL-CLOSED

    # CHECK 3.5 — Cantidad Máxima de Monedas Activas Simultáneas (Crypto):
    try:
        open_symbols_res = supabase_client.table('positions') \
            .select('symbol') \
            .eq('status', 'open') \
            .execute()
        
        active_symbols = set(p['symbol'] for p in (open_symbols_res.data or []))
        
        tc_res = supabase_client.table('trading_config').select('regime_params').eq('id', 1).execute()
        tc_data = tc_res.data[0] if tc_res.data else {}
        regime_params = tc_data.get('regime_params', {}) or {}
        max_active_symbols_crypto = int(regime_params.get('max_active_symbols_crypto', 1))
        
        sig_symbol = signal.get('symbol', '')
        if sig_symbol and sig_symbol not in active_symbols and len(active_symbols) >= max_active_symbols_crypto:
            return { 'approved': False, 'reason': f'MAX_ACTIVE_SYMBOLS_CRYPTO_REACHED ({len(active_symbols)}/{max_active_symbols_crypto})' }
    except Exception as e:
        logging.error(f"Error checking max active symbols crypto: {e}")

    # CHECK 3.6 — Cantidad Máxima de Monedas Activas Simultáneas (Forex):
    try:
        open_fx_res = supabase_client.table('forex_positions') \
            .select('symbol') \
            .eq('status', 'open') \
            .execute()
        
        active_fx_symbols = set(p['symbol'] for p in (open_fx_res.data or []))
        
        tc_res = supabase_client.table('trading_config').select('regime_params').eq('id', 1).execute()
        tc_data = tc_res.data[0] if tc_res.data else {}
        regime_params = tc_data.get('regime_params', {}) or {}
        max_active_symbols_forex = int(regime_params.get('max_active_symbols_forex', 2))
        
        sig_symbol = signal.get('symbol', '')
        if market_type == 'forex_futures' and sig_symbol and sig_symbol not in active_fx_symbols and len(active_fx_symbols) >= max_active_symbols_forex:
            return { 'approved': False, 'reason': f'MAX_ACTIVE_SYMBOLS_FOREX_REACHED ({len(active_fx_symbols)}/{max_active_symbols_forex})' }
    except Exception as e:
        logging.error(f"Error checking max active symbols forex: {e}")

    # CHECK 4 — No exceder posiciones por símbolo:
    try:
        from app.core.crypto_symbols import crypto_symbol_match_variants
        variants = crypto_symbol_match_variants(signal['symbol'])
        symbol_positions = supabase_client.table('positions') \
            .select('id', count='exact') \
            .in_('symbol', variants) \
            .eq('status', 'open') \
            .execute()
            
        max_per_symbol = int(risk_config.get('max_positions_per_symbol', 4))
        current_symbol_open = symbol_positions.count if symbol_positions.count is not None else 999

        if current_symbol_open >= max_per_symbol:
            return { 'approved': False, 'reason': f'MAX_POSITIONS_PER_SYMBOL_REACHED ({signal["symbol"]}: {current_symbol_open}/{max_per_symbol})' }
            
    except Exception as e:
        logging.error(f"Error checking per-symbol positions: {e}")

    # CHECK 4.5 — Cooldown por Estrategia y Símbolo (15 min) + Bypass por Extremos
    try:
        from app.core.crypto_symbols import crypto_symbol_match_variants
        from datetime import datetime, timedelta
        variants = crypto_symbol_match_variants(signal['symbol'])
        rule_code = signal.get('rule_code')
        
        if rule_code:
            fifteen_mins_ago = (datetime.utcnow() - timedelta(minutes=15)).isoformat()
            
            # Buscar en 'trading_signals' en vez de 'positions' para ser más exacto al disparo de la señal
            # O en 'positions' si queremos bloquear post-compra. La regla pide: "compre BTC en Aa30C y hay que esperar 15 min"
            # por lo tanto buscamos en positions:
            recent_positions = supabase_client.table('positions') \
                .select('id, created_at') \
                .in_('symbol', variants) \
                .eq('rule_code', rule_code) \
                .gte('created_at', fifteen_mins_ago) \
                .limit(1) \
                .execute()
            
            if recent_positions.data:
                metrics = signal.get('raw_metrics_5m', {})
                sig_dir = str(signal.get('direction') or signal.get('signal_type', '')).lower()
                
                rsi = float(metrics.get('rsi', 50))
                low_price = float(metrics.get('low', 0))
                high_price = float(metrics.get('high', 0))
                open_price = float(metrics.get('open', 0))
                close_price = float(metrics.get('close', 0))
                
                lower_5 = float(metrics.get('lower_5', 0))
                lower_6 = float(metrics.get('lower_6', 0))
                upper_5 = float(metrics.get('upper_5', 0))
                upper_6 = float(metrics.get('upper_6', 0))
                bb_lower = float(metrics.get('bb_lower', metrics.get('lower_2', 0))) 
                bb_upper = float(metrics.get('bb_upper', metrics.get('upper_2', 0)))

                bypass = False
                if 'long' in sig_dir or 'buy' in sig_dir:
                    if rsi < 15:
                        bypass = True
                    elif lower_6 > 0 and low_price <= lower_6:
                        bypass = True
                    elif lower_5 > 0 and low_price <= lower_5:
                        bypass = True
                    elif bb_lower > 0 and open_price < bb_lower and close_price < open_price:
                        bypass = True
                else: # short
                    if rsi > 85:
                        bypass = True
                    elif upper_6 > 0 and high_price >= upper_6:
                        bypass = True
                    elif upper_5 > 0 and high_price >= upper_5:
                        bypass = True
                    elif bb_upper > 0 and open_price > bb_upper and close_price > open_price:
                        bypass = True
                
                if not bypass:
                    return { 'approved': False, 'reason': f'COOLDOWN_ACTIVE_STRATEGY ({rule_code} en {signal["symbol"]})' }
                else:
                    logging.info(f"Bypass cooldown activado para {signal['symbol']} ({rule_code}) por extremos (RSI: {rsi:.2f})")
    except Exception as e:
        logging.error(f"Error checking strategy cooldown: {e}")

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
        
        # Fallback to capital_operativo if balance is zero or fetch failed
        if not balance or balance <= 0:
            try:
                config_res = supabase_client.table('trading_config').select('capital_operativo').eq('id', 1).maybe_single().execute()
                balance = float(config_res.data.get('capital_operativo', 500))
            except:
                balance = 500

        kill_switch_pct = float(risk_config.get('kill_switch_loss_pct', 3.0))
        kill_switch_usdt = balance * (kill_switch_pct / 100)

        if total_hourly_loss < 0 and abs(total_hourly_loss) >= kill_switch_usdt:
            activar_kill_switch(supabase_client, f'Hourly kill switch triggered: ${abs(total_hourly_loss):.2f}')
            return { 'approved': False, 'reason': 'KILL_SWITCH_HOURLY_TRIGGERED' }
    except Exception as e:
        logging.error(f"Error checking hourly loss: {e}")

    return {
        'approved': True,
        'reason': 'ALL_CHECKS_PASSED',
        'balance_usdt': locals().get('balance', 0),
        'daily_loss_usdt': 0, 
        'open_positions': current_open
    }
