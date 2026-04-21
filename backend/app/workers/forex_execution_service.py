"""
Forex Execution Service v1.2 - Multiple Positions Support
Supports up to 4 concurrent positions per symbol.
"""

import os
import time
import traceback
from datetime import datetime, timezone

from ctrader_open_api import Protobuf
from ctrader_open_api.messages.OpenApiMessages_pb2 import *
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import *

from app.strategy.proactive_exit import evaluate_proactive_exit

# ── Configuración ────────────────────────────────
FOREX_CONFIG = {
    'capital_usd':        float(os.getenv('FOREX_CAPITAL', 1000)),
    'risk_per_trade_pct': float(os.getenv('FOREX_RISK_PCT', 1.0)),
    'max_open_positions_per_symbol': 4,
    'mode':               os.getenv('FOREX_MODE', 'paper'),
}

PIP_CONFIG = {
    'EURUSD': {'pip': 0.0001, 'pip_val_std': 10.0},
    'GBPUSD': {'pip': 0.0001, 'pip_val_std': 10.0},
    'USDJPY': {'pip': 0.01,   'pip_val_std': 10.0},
    'XAUUSD': {'pip': 0.01,   'pip_val_std': 1.0 },
}

class ForexExecutionService:
    def __init__(self, worker, supabase_client, state_ref, symbols_ref):
        self.worker   = worker
        self.sb       = supabase_client
        self.state    = state_ref
        self.symbols  = symbols_ref
        self.log      = worker.log
        self.mode     = FOREX_CONFIG['mode']
        self._open_positions_list = []
        self._load_open_positions()

    def _load_open_positions(self):
        try:
            res = self.sb.table('forex_positions').select('*').eq('status', 'open').execute()
            self._open_positions_list = res.data or []
            self.log(f'Posiciones abiertas cargadas: {len(self._open_positions_list)}')
        except Exception as e:
            self.log(f'Error cargando posiciones: {e}', 'ERROR')

    def run_evaluation_cycle(self):
        try:
            # 1. Recargar posiciones frescas desde DB para evitar discrepancias
            self._load_open_positions()
            open_count = len(self._open_positions_list)

            # 2. Cargar config de riesgo dinamica
            from app.core.supabase_client import get_risk_config
            risk_config = get_risk_config()
            limit_per_symbol = int(risk_config.get('max_positions_per_symbol', 4))
            limit_global = int(risk_config.get('max_total_positions', 16))

            if open_count >= limit_global:
                self.log(f'Limite global de posiciones alcanzado ({open_count}/{limit_global})')
                return

            pos_count = {}
            for p in self._open_positions_list:
                s = p['symbol']
                pos_count[s] = pos_count.get(s, 0) + 1

            symbols = list(self.state['symbol_ids'].keys()) or self.symbols
            snaps_res = self.sb.table('market_snapshot').select('*').in_('symbol', symbols).execute()
            snaps_data = snaps_res.data or []
            
            summary = ", ".join([f"{s}: {pos_count.get(s,0)}" for s in symbols])
            self.log(f'Evaluando {len(snaps_data)} simbolos. Total: {open_count} | {summary} (Limite/Simbolo: {limit_per_symbol})')

            for snap in snaps_data:
                symbol = snap['symbol']
                count = pos_count.get(symbol, 0)
                if count >= limit_per_symbol:
                    if count > limit_per_symbol:
                        self.log(f"[EXCESO] Detectado en {symbol}: {count} > {limit_per_symbol}", "WARNING")
                    continue 
                
                self._evaluate_symbol(snap)

        except Exception as e:
            self.log(f'Error en ciclo evaluacion: {e}', 'ERROR')

    def _evaluate_symbol(self, snap: dict):
        try:
            context = self._build_context(snap)
            for direction in ['long', 'short']:
                signal = self._check_rules(context, direction)
                if signal and signal['triggered']:
                    self.log(f'[SIGNAL] {direction.upper()} {snap["symbol"]}: {signal["rule_code"]}')
                    self._execute_signal(snap['symbol'], direction, signal, snap)
                    break
        except Exception as e:
            self.log(f'{snap["symbol"]} evaluacion error: {e}', 'ERROR')

    def _build_context(self, snap: dict) -> dict:
        price = float(snap.get('price') or 0)
        adx = float(snap.get('adx') or 25)
        if adx < 20: velocity = 'debil'
        elif adx < 35: velocity = 'moderado'
        elif adx < 50: velocity = 'agresivo'
        else: velocity = 'explosivo'

        mtf_raw = snap.get('mtf_score')
        mtf_score = float(mtf_raw) if mtf_raw is not None else 0.0

        return {
            'symbol': snap.get('symbol'),
            'price': price,
            'basis': float(snap.get('basis') or price),
            'dist_basis_pct': float(snap.get('dist_basis_pct') or 0),
            'adx': adx,
            'adx_velocity': velocity,
            'mtf_score': mtf_score,
            'sar_trend_4h': int(snap.get('sar_trend_4h') or 0),
            'sar_trend_15m': int(snap.get('sar_trend_15m') or 0),
            'sar_phase': str(snap.get('sar_phase') or 'neutral'),
            'fibonacci_zone': int(snap.get('fibonacci_zone') or 0),
            'pinescript_signal': str(snap.get('pinescript_signal') or ''),
            'allow_long_4h': bool(snap.get('allow_long_4h') if snap.get('allow_long_4h') is not None else True),
            'allow_short_4h': bool(snap.get('allow_short_4h') if snap.get('allow_short_4h') is not None else True),
            'upper_1': float(snap.get('upper_1') or 0),
            'lower_1': float(snap.get('lower_1') or 0),
            'upper_6': float(snap.get('upper_6') or 0),
            'lower_6': float(snap.get('lower_6') or 0),
        }

    def _check_rules(self, context: dict, direction: str) -> dict:
        results = []
        sar_4h = context['sar_trend_4h']
        sar_15m = context['sar_trend_15m']
        mtf = context['mtf_score']
        pine = context['pinescript_signal']
        struct_ok = context['allow_long_4h'] if direction == 'long' else context['allow_short_4h']
        fib_zone = context['fibonacci_zone']

        if direction == 'long':
            sar_4h_ok, sar_15m_ok = sar_4h > 0, sar_15m > 0
            mtf_ok, pine_ok = mtf >= 0.25, pine == 'Buy'
        else:
            sar_4h_ok, sar_15m_ok = sar_4h < 0, sar_15m < 0
            mtf_ok, pine_ok = mtf <= -0.25, pine == 'Sell'

        # Aa22/Bb22: Full confirmation
        results.append({'rule_code': 'Aa22' if direction == 'long' else 'Bb22', 'triggered': (sar_4h_ok and mtf_ok and pine_ok and struct_ok), 'score': 0.8})

        # Aa31/Bb31: SAR alignment
        results.append({'rule_code': 'Aa31a' if direction == 'long' else 'Bb31a', 'triggered': (sar_4h_ok and sar_15m_ok and struct_ok), 'score': 0.7})

        # Dd Reversal
        fib_reversal = (direction == 'long' and fib_zone <= -2) or (direction == 'short' and fib_zone >= 2)
        results.append({'rule_code': 'Dd21_15m' if direction == 'long' else 'Dd11_15m', 'triggered': (fib_reversal and sar_15m_ok and struct_ok), 'score': 0.9})

        triggered = [r for r in results if r.get('triggered')]
        return max(triggered, key=lambda x: x['score']) if triggered else None

    def _execute_signal(self, symbol, direction, signal, snap):
        # 1. Reglas Multi-layer (Misma estrategia)
        same_strat = [p for p in self._open_positions_list if p['symbol'] == symbol and p['rule_code'] == signal['rule_code']]
        if same_strat:
            # Regla 1: 1 compra por vela (usamos 15 min como estándar solicitado)
            last_pos = sorted(same_strat, key=lambda x: x['opened_at'], reverse=True)[0]
            opened_at_str = str(last_pos['opened_at'])
            if 'Z' in opened_at_str: opened_at_str = opened_at_str.replace('Z', '+00:00')
            opened_at = datetime.fromisoformat(opened_at_str)
            now = datetime.now(timezone.utc)
            
            if (now - opened_at).total_seconds() < 900: # 15 minutos
                 self.log(f'⏸️ Omitiendo {symbol} {signal["rule_code"]}: Ya se abrió en los últimos 15 min.')
                 return
            
            # Regla 2: Mejora de precio
            price = float(snap.get('price', 0))
            last_entry = float(last_pos['entry_price'])
            if direction == 'long' and price >= last_entry:
                 self.log(f'⏸️ Omitiendo {symbol} {direction.upper()}: Precio {price} >= {last_entry} (No mejora costo)')
                 return
            if direction == 'short' and price <= last_entry:
                 self.log(f'⏸️ Omitiendo {symbol} {direction.upper()}: Precio {price} <= {last_entry} (No mejora costo)')
                 return
            
            self.log(f'💎 Agregando CAPA {len(same_strat)+1} para {symbol} ({signal["rule_code"]})')

        # Gualdián final: Límite TOTAL por símbolo (Para todas las estrategias)
        total_symbol = len([p for p in self._open_positions_list if p['symbol'] == symbol])
        from app.core.supabase_client import get_risk_config
        max_per_symbol = int(get_risk_config().get('max_positions_per_symbol', 4))
        if total_symbol >= max_per_symbol:
            self.log(f'🚫 LÍMITE TOTAL ALCANZADO para {symbol}: {total_symbol}/{max_per_symbol} posiciones.', 'WARNING')
            return

        # 2. Reversión forzada: No permitimos BUY y SELL a la vez (Hedge OFF)
        opposite = 'short' if direction == 'long' else 'long'
        opp_positions = [p for p in self._open_positions_list if p['symbol'] == symbol and p['side'] == opposite]
        if opp_positions:
            self.log(f'[HEDGE] Cerrando {len(opp_positions)} posiciones de {opposite.upper()} por reversión a {direction.upper()}')
            for p in opp_positions:
                price_data = self.state['prices'].get(symbol, {})
                price = float(price_data.get('mid', snap.get('price', 0)))
                pip_size = PIP_CONFIG.get(symbol, {}).get('pip', 0.0001)
                pips = (price - p['entry_price'])/pip_size if p['side']=='long' else (p['entry_price'] - price)/pip_size
                self._close_position(p, price, f'reversal_{direction}', pips)

        # 2. Ejecutar nueva señal
        price = float(snap.get('price', 0))
        sl, tp, sl_pips = self._calculate_sl_tp(symbol, direction, price, snap, signal['rule_code'])
        lots = self._calculate_lot_size(symbol, sl_pips)

        # 3. Validación estricta de riesgo (Máximo $10 o 1% del capital)
        riesgo_limite = FOREX_CONFIG['capital_usd'] * FOREX_CONFIG['risk_per_trade_pct'] / 100
        pip_val = PIP_CONFIG.get(symbol, {}).get('pip_val_std', 10.0)
        riesgo_real = lots * sl_pips * pip_val

        if riesgo_real > (riesgo_limite * 1.2): # Permitimos un pequeño margen por redondeo a 0.01
            self.log(
                f'🚫 ABORTANDO {symbol}: Riesgo proyectado ${riesgo_real:.2f} '
                f'excede el límite de ${riesgo_limite:.2f} '
                f'(SL Pips: {sl_pips:.1f}, Lots: {lots})',
                'WARNING'
            )
            return

        self.log(f'[ORDEN] {direction.upper()} {symbol} ({signal["rule_code"]}): lots={lots} risk=${riesgo_real:.2f}')
        if self.mode == 'live': self._execute_live_order(symbol, direction, lots, price, sl, tp, signal['rule_code'])
        else: self._execute_paper_order(symbol, direction, lots, price, sl, tp, signal['rule_code'])

    def _calculate_lot_size(self, symbol, sl_pips):
        riesgo = FOREX_CONFIG['capital_usd'] * FOREX_CONFIG['risk_per_trade_pct'] / 100
        pip_val = PIP_CONFIG.get(symbol, {}).get('pip_val_std', 10.0)
        lots = round(riesgo / (sl_pips * pip_val), 2) if sl_pips > 0 else 0.01
        return min(max(lots, 0.01), 1.0)

    def _calculate_sl_tp(self, symbol, direction, entry, snap, rule_code):
        pip_size = PIP_CONFIG.get(symbol, {}).get('pip', 0.0001)
        u1, l1 = float(snap.get('upper_1') or 0), float(snap.get('lower_1') or 0)
        atr = (u1 - l1) / 3.236 if (u1 > 0 and l1 > 0) else (20 * pip_size)
        
        if direction == 'long':
            sl = float(snap.get('lower_6') or (entry-50*pip_size)) - atr
            tp = entry + (3 * atr)
        else:
            sl = float(snap.get('upper_6') or (entry+50*pip_size)) + atr
            tp = entry - (3 * atr)
        return round(sl, 6), round(tp, 6), abs(entry-sl)/pip_size

    def _execute_live_order(self, symbol, direction, lots, entry, sl, tp, rule_code):
        try:
            from app.workers.forex_worker_standalone import ACCOUNT_ID
            sid = self.state['symbol_ids'].get(symbol)
            if not sid: return
            req = ProtoOANewOrderReq()
            req.ctidTraderAccountId = ACCOUNT_ID
            req.symbolId, req.orderType, req.tradeSide = sid, 1, (1 if direction=='long' else 2)
            req.volume = int(lots * 100000)
            if sl > 0: req.stopLoss = round(sl, 6)
            if tp > 0: req.takeProfit = round(tp, 6)
            self.worker.client.send(req)
            self._save_position(symbol, direction, lots, entry, sl, tp, rule_code, mode='live')
        except Exception as e: self.log(f'Error live: {e}')

    def _execute_paper_order(self, symbol, direction, lots, entry, sl, tp, rule_code):
        self._save_position(symbol, direction, lots, entry, sl, tp, rule_code, mode='paper')
        self._send_telegram(f'📊 [PAPER] {direction.upper()} {symbol} (Rule: {rule_code})')

    def _save_position(self, symbol, direction, lots, entry, sl, tp, rule_code, mode='paper'):
        try:
            pos = {'symbol': symbol, 'side': direction, 'lots': float(lots), 'entry_price': float(entry), 'sl_price': float(sl), 'tp_price': float(tp), 'status': 'open', 'mode': mode, 'rule_code': rule_code, 'opened_at': datetime.now(timezone.utc).isoformat()}
            res = self.sb.table('forex_positions').insert(pos).execute()
            if res.data: self._open_positions_list.append(res.data[0])
        except Exception as e: self.log(f'Error guardando: {e}')

    def run_position_management(self):
        if not self._open_positions_list: return
        snaps = {}
        try:
            symbols = list(set(p['symbol'] for p in self._open_positions_list))
            res = self.sb.table('market_snapshot').select('*').in_('symbol', symbols).execute()
            for s in (res.data or []): snaps[s['symbol']] = s
        except Exception as e: self.log(f"Error gestion snaps: {e}")

        for pos in list(self._open_positions_list):
            try: 
                snap = snaps.get(pos['symbol'])
                
                # ── Primero: Verificar cierre proactivo ──
                if snap and self._check_proactive_exit_forex(pos, snap):
                    continue # Posición cerrada

                self._manage_position(pos, snap)
            except Exception as e: self.log(f'Error gestión: {e}')

    def _check_proactive_exit_forex(self, pos: dict, snap: dict) -> bool:
        """
        Evalúa Aa51/Bb51 para posiciones Forex.
        Retorna True si se cerró la posición.
        """
        symbol = pos['symbol']
        price_data = self.state['prices'].get(symbol)
        if not price_data:
            return False
        price = float(price_data.get('mid', 0))
        if price <= 0:
            return False

        # Obtener velas 4H del STATE del worker
        key_4h = f'{symbol}_4h'
        bars_4h = self.worker._STATE['candles'].get(key_4h, [])

        if len(bars_4h) < 3:
            return False

        # Convertir a DataFrame
        import pandas as pd
        df_4h = pd.DataFrame(bars_4h)
        df_4h['open_time'] = pd.to_datetime(df_4h['ts'])
        df_4h = df_4h.set_index('open_time')
        for col in ['open','high','low','close']:
            df_4h[col] = pd.to_numeric(df_4h[col])

        # Adaptar position al formato estandar (en Forex usamos 'lots' -> 'size')
        position_std = {
            'symbol':           symbol,
            'side':             pos['side'],
            'avg_entry_price':  pos['entry_price'],
            'size':             pos['lots'],
            'id':               pos['id']
        }

        result = evaluate_proactive_exit(
            position      = position_std,
            current_price = price,
            snap          = snap,
            df_4h         = df_4h,
            market_type   = 'forex_futures',
        )

        if not result['should_close']:
            return False

        pnl = result['pnl']
        self.log(
            f'🛡️ CIERRE PROACTIVO FOREX {symbol}: '
            f'{result["rule_code"]} '
            f'+{pnl["pnl_pct"]:.3f}% '
            f'({pnl["pnl_pips"]:.1f} pips) - {result["reason"]}'
        )

        # Cerrar posición
        self._close_position(pos, price, result['rule_code'], pnl['pnl_pips'])
        self._send_telegram(
            f"🛡️ CIERRE PROACTIVO FOREX [{symbol}]\n"
            f"Regla: {result['rule_code']}\n"
            f"Pips: +{pnl['pnl_pips']:.1f}\n"
            f"Razón: {result['reason']}"
        )

        return True

    def _manage_position(self, pos, snap=None):
        symbol = pos['symbol']
        price_data = self.state['prices'].get(symbol)
        if not price_data: return
        price = float(price_data.get('mid', 0))
        side, entry, sl, tp = pos['side'], float(pos['entry_price']), float(pos.get('sl_price') or 0), float(pos.get('tp_price') or 0)
        pip_size = PIP_CONFIG.get(symbol, {}).get('pip', 0.0001)
        pips_pnl = (price - entry) / pip_size if side == 'long' else (entry - price) / pip_size
        
        if snap:
            u6, l6 = float(snap.get('upper_6') or 0), float(snap.get('lower_6') or 0)
            if (side == 'long' and u6 > 0 and price >= u6) or (side == 'short' and l6 > 0 and price <= l6):
                self._close_position(pos, price, 'tp_band', pips_pnl)
                return

        if (sl > 0 and ((side=='long' and price<=sl) or (side=='short' and price>=sl))) or \
           (tp > 0 and ((side=='long' and price>=tp) or (side=='short' and price<=tp))):
            reason = 'sl' if (sl > 0 and ((side=='long' and price<=sl) or (side=='short' and price>=sl))) else 'tp'
            self._close_position(pos, price, reason, pips_pnl)

    def _close_position(self, pos, close_price, reason, pips_pnl):
        try:
            symbol = pos['symbol']
            
            # Cancelar todos los SL del exchange
            from app.strategy.dynamic_sl_manager import cancel_all_sl_orders
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(cancel_all_sl_orders(symbol, pos, self.sb, reason))
                else:
                    asyncio.run(cancel_all_sl_orders(symbol, pos, self.sb, reason))
            except Exception as sl_e:
                self.log(f'Error cancelando SL: {sl_e}', 'ERROR')

            pnl_usd = pips_pnl * PIP_CONFIG.get(symbol, {}).get('pip_val_std', 10.0) * float(pos['lots'])
            self.sb.table('forex_positions').update({'status': 'closed', 'current_price': close_price, 'close_reason': reason, 'pnl_usd': round(pnl_usd, 2), 'pnl_pips': round(pips_pnl, 1), 'closed_at': datetime.now(timezone.utc).isoformat()}).eq('id', pos['id']).execute()
            self._open_positions_list = [p for p in self._open_positions_list if p['id'] != pos['id']]
            self.log(f'Cerrada {symbol}: {reason} | PnL: {pips_pnl:.1f} pips')
        except Exception as e: self.log(f'Error cierre: {e}')

    def _send_telegram(self, message):
        try:
            import requests
            token, chat_id = os.getenv('TELEGRAM_BOT_TOKEN'), os.getenv('TELEGRAM_CHAT_ID')
            if token and chat_id: requests.post(f'https://api.telegram.org/bot{token}/sendMessage', json={'chat_id': chat_id, 'text': message}, timeout=5)
        except: pass
