"""
Broker Synchronizer — Sincronización Bidireccional en Vivo con Exchanges (Binance Futures & cTrader)
eTrade v5.0 / v6.0

Responsabilidades:
1. Consultar en tiempo real las posiciones abiertas en el broker/exchange.
2. Sincronizar automáticamente hacia Supabase ('positions' y 'forex_positions'):
   - Si una posición existe en el broker pero no en Supabase (ej. trades manuales o externos), la crea con status='open'.
   - Actualiza en vivo el precio actual (markPrice), PnL no realizado (unRealizedProfit) y tamaño.
   - Si una posición fue cerrada directamente en el broker (TP/SL de exchange, cierre manual), la marca en Supabase como status='closed'.
3. Mantiene sincronizada la memoria en vivo (BOT_STATE) y notifica vía Telegram.
4. Zombie Order Cleaner (Reaper): Cancela órdenes abiertas huérfanas en Binance de símbolos sin posición activa o con más de 15 minutos de antigüedad sin fill.
"""

import asyncio
from datetime import datetime, timezone
import os
from typing import Dict, List, Any, Optional

from app.core.config import settings
from app.core.logger import log_info, log_warning, log_error
from app.core.supabase_client import get_supabase
from app.execution.data_provider import BinanceCryptoProvider
from app.core.memory_store import BOT_STATE

MODULE = "BROKER_SYNC"


class BrokerSynchronizer:
    """
    Sincronizador en vivo de posiciones entre Brokers (Binance / cTrader) y eTrade.
    """

    def __init__(self):
        self._is_running_crypto = False
        self._is_running_forex = False

    async def sync_binance_futures(self) -> Dict[str, Any]:
        """
        Sincroniza posiciones de Binance Futures con la tabla 'positions' de Supabase
        y limpia órdenes zombi en el orderbook de Binance.
        """
        if self._is_running_crypto:
            return {"status": "already_running"}
        
        self._is_running_crypto = True
        result = {
            "synced_active": 0,
            "created": [],
            "updated": [],
            "closed": [],
            "zombie_orders_cleaned": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            api_key = os.getenv("BINANCE_API_KEY") or settings.binance_api_key
            api_secret = os.getenv("BINANCE_SECRET") or os.getenv("BINANCE_API_SECRET") or settings.binance_secret

            if not api_key or not api_secret:
                log_warning(MODULE, "No hay credenciales configuradas para Binance Futures.")
                return {"status": "error", "message": "No credentials"}

            provider = BinanceCryptoProvider(
                api_key=api_key,
                api_secret=api_secret,
                market="futures",
                testnet=settings.binance_testnet,
            )
            client = await provider._get_async_client()

            # 1. Obtener todas las posiciones de Binance Futures (con recvWindow ampliado de 60s)
            positions_raw = await client.futures_position_information(recvWindow=60000)
            active_binance_map: Dict[str, Dict[str, Any]] = {}

            for p in positions_raw:
                amt = float(p.get("positionAmt", 0))
                if amt != 0:
                    sym = p.get("symbol", "").upper()
                    active_binance_map[sym] = {
                        "symbol": sym,
                        "side": "LONG" if amt > 0 else "SHORT",
                        "size": abs(amt),
                        "entry_price": float(p.get("entryPrice", 0)),
                        "mark_price": float(p.get("markPrice", 0)),
                        "unrealized_pnl": float(p.get("unRealizedProfit", 0)),
                        "leverage": int(p.get("leverage", 20)),
                        "liquidation_price": float(p.get("liquidationPrice", 0)),
                    }

            result["synced_active"] = len(active_binance_map)

            # 2. Consultar posiciones abiertas en Supabase
            sb = get_supabase()
            res_db = sb.table("positions").select("*").eq("status", "open").execute()
            db_positions = res_db.data or []
            db_symbols_map = {}

            for p in db_positions:
                sym_norm = str(p.get("symbol", "")).replace("/", "").upper()
                db_symbols_map[sym_norm] = p

            # 3. Procesar posiciones activas de Binance
            for sym, b_pos in active_binance_map.items():
                entry_p = b_pos["entry_price"] or b_pos["mark_price"]
                sl_p = entry_p * 0.95 if b_pos["side"] == "LONG" else entry_p * 1.05
                tp_p = entry_p * 1.05 if b_pos["side"] == "LONG" else entry_p * 0.95

                if sym in db_symbols_map:
                    # Actualizar posición existente en Supabase con datos en vivo
                    db_p = db_symbols_map[sym]
                    upd_data = {
                        "current_price": b_pos["mark_price"],
                        "unrealized_pnl": round(b_pos["unrealized_pnl"], 4),
                        "size": b_pos["size"],
                    }
                    if b_pos["entry_price"] > 0 and float(db_p.get("entry_price") or 0) == 0:
                        upd_data["entry_price"] = b_pos["entry_price"]
                        upd_data["avg_entry_price"] = b_pos["entry_price"]

                    sb.table("positions").update(upd_data).eq("id", db_p["id"]).execute()
                    result["updated"].append(sym)
                else:
                    # Posición abierta en Binance pero NO existente en Supabase (ej. SOLUSDT manual o externo)
                    new_pos_data = {
                        "symbol": sym,
                        "side": b_pos["side"],
                        "entry_price": entry_p,
                        "avg_entry_price": entry_p,
                        "current_price": b_pos["mark_price"],
                        "size": b_pos["size"],
                        "stop_loss": sl_p,
                        "sl_price": sl_p,
                        "take_profit": tp_p,
                        "tp_full_price": tp_p,
                        "tp_partial_price": (entry_p + tp_p) / 2.0,
                        "unrealized_pnl": round(b_pos["unrealized_pnl"], 4),
                        "realized_pnl": 0.0,
                        "status": "open",
                        "mode": "live",
                        "rule_code": "MANUAL_BINANCE",
                        "rule_entry": "MANUAL_BINANCE",
                        "opened_at": datetime.now(timezone.utc).isoformat(),
                    }
                    ins_res = sb.table("positions").insert(new_pos_data).execute()
                    result["created"].append(sym)
                    log_info(MODULE, f"🔄 Posición externa de Binance detectada e importada a eTrade: {b_pos['side']} {b_pos['size']} {sym} @ {entry_p}")

                    # Notificar a Telegram si está activo
                    try:
                        from app.workers.alerts_service import send_telegram_message
                        await send_telegram_message(
                            f"🔄 [BROKER SYNC] Posición Binance Detectada\n"
                            f"Símbolo: {sym} ({b_pos['side']})\n"
                            f"Tamaño: {b_pos['size']}\n"
                            f"Entrada: {entry_p:.4f}\n"
                            f"Marca: {b_pos['mark_price']:.4f}\n"
                            f"PnL: {b_pos['unrealized_pnl']:+.4f} USDT"
                        )
                    except Exception as tel_e:
                        log_warning(MODULE, f"No se pudo enviar alerta Telegram: {tel_e}")

            # 4. Detectar posiciones que estaban 'open' en Supabase pero ya NO existen en Binance (Cerradas en exchange)
            for sym, db_p in db_symbols_map.items():
                if sym not in active_binance_map:
                    # Solo cerrar si es posición live de crypto
                    is_paper = db_p.get("is_paper") or (db_p.get("mode") == "paper")
                    if not is_paper:
                        entry_p = float(db_p.get("entry_price") or db_p.get("avg_entry_price") or 0)
                        close_p = float(db_p.get("current_price") or entry_p)
                        side_p = str(db_p.get("side") or "").lower()
                        size_p = float(db_p.get("size") or 0)

                        # Intentar obtener el PnL y precio de ejecución exacto del último trade en Binance
                        realized_pnl = 0.0
                        try:
                            trades = await client.futures_account_trades(symbol=sym, limit=5, recvWindow=60000)
                            if trades:
                                recent_trades = [t for t in trades if float(t.get('realizedPnl', 0)) != 0]
                                if recent_trades:
                                    last_t = recent_trades[-1]
                                    realized_pnl = float(last_t.get('realizedPnl', 0))
                                    close_p = float(last_t.get('price', close_p))
                        except Exception as tr_err:
                            log_warning(MODULE, f"No se pudo consultar trades de Binance para {sym}: {tr_err}")

                        if realized_pnl == 0.0 and entry_p > 0 and close_p > 0 and size_p > 0:
                            is_long_p = side_p in ('long', 'buy')
                            realized_pnl = ((close_p - entry_p) * size_p) if is_long_p else ((entry_p - close_p) * size_p)

                        pnl_pct = ((realized_pnl / (entry_p * size_p)) * 100.0) if (entry_p > 0 and size_p > 0) else 0.0

                        close_data = {
                            "status": "closed",
                            "closed_at": datetime.now(timezone.utc).isoformat(),
                            "close_reason": "binance_closed"[:20],
                            "current_price": close_p,
                            "realized_pnl": round(realized_pnl, 4),
                            "realized_pnl_usd": round(realized_pnl, 4),
                            "realized_pnl_pct": round(pnl_pct, 4),
                            "unrealized_pnl": 0.0,
                        }
                        sb.table("positions").update(close_data).eq("id", db_p["id"]).execute()
                        result["closed"].append(sym)
                        log_info(MODULE, f"🔄 Posición de {sym} cerrada en Binance -> PnL Realizado: ${realized_pnl:+.4f} ({pnl_pct:+.2f}%)")

            # 5. LIMPIEZA DE ÓRDENES ZOMBI / HUÉRFANAS EN BINANCE FUTURES
            cleaned = await self.cleanup_zombie_orders(client, list(active_binance_map.keys()))
            result["zombie_orders_cleaned"] = cleaned

            # 6. Sincronizar memoria BOT_STATE
            from app.workers.scheduler import sync_positions_to_memory
            await sync_positions_to_memory()

            await client.close_connection()

        except asyncio.CancelledError:
            pass
        except (TimeoutError, asyncio.TimeoutError) as te:
            log_warning(MODULE, f"Timeout temporal consultando Binance Futures (reintentará en el próximo ciclo): {te}")
            result["error"] = "TimeoutError (transient)"
        except Exception as e:
            err_msg = str(e) or repr(e)
            log_error(MODULE, f"Error en sync_binance_futures: {err_msg}")
            result["error"] = err_msg
        finally:
            self._is_running_crypto = False

        return result

    async def cleanup_zombie_orders(self, client, active_binance_symbols: List[str]) -> List[str]:
        """
        Revisa todas las órdenes abiertas en Binance Futures y cancela órdenes zombi/huérfanas
        (órdenes abiertas de símbolos que ya no tienen posición activa o que llevan más de 15 minutos pendientes).
        """
        cancelled = []
        try:
            open_orders = await client.futures_get_open_orders(recvWindow=60000)
            now_ts = datetime.now(timezone.utc).timestamp() * 1000
            for o in open_orders:
                sym = o.get('symbol', '')
                oid = o.get('orderId')
                created_ts = o.get('time', now_ts)
                age_minutes = (now_ts - created_ts) / (1000 * 60)
                
                # Si el símbolo no tiene posición abierta o la orden lleva más de 15 minutos sin llenarse
                if sym not in active_binance_symbols or age_minutes > 15:
                    try:
                        await client.futures_cancel_order(symbol=sym, orderId=oid, recvWindow=60000)
                        cancelled.append(f"{sym}_{oid}")
                        log_info(MODULE, f"🧹 [ZOMBIE ORDER CLEANER] Orden huérfana cancelada en Binance: {sym} (ID={oid}, edad={age_minutes:.1f}m)")
                    except Exception as c_err:
                        log_warning(MODULE, f"No se pudo cancelar orden zombi {sym} {oid}: {c_err}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            err_msg = str(e) or repr(e)
            log_error(MODULE, f"Error en cleanup_zombie_orders: {err_msg}")
        return cancelled


# Instancia singleton para uso en el scheduler y API endpoints
GLOBAL_BROKER_SYNC = BrokerSynchronizer()
