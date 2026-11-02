"""
eTrade — ETI Signal Ingestion & Consumer Service
==================================================
Servicio de comunicación, sincronización y feedback entre ETI (eTrade Intelligence v2.3)
y el motor de ejecución eTrade.

Soporta:
1. Verificación de conectividad contra el entorno activo de ETI (https://eti-zeta-one.vercel.app).
2. Sincronización automática de señales desde la Matriz de Apertura institucional (META, NVDA, SPX, SPY, QQQ).
3. Ingesta push vía REST/Webhook (POST /api/v1/options/eti/signals).
4. Persistencia local e IPC atómico (backend/data/etrade_signals_live.json).
5. Despacho de telemetría y feedback de ejecución hacia ETI.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import httpx

from app.core.logger import log_info, log_warning, log_error
from app.options.eti_models import (
    ETISignal, OptionsContractSpec, StrategySpec, CausalContext,
    TechnicalGate, RiskManagement, SafetyGuardrails, ETITacticalInstruction,
    IndicatorRequirements
)
from app.options.eti_storage import (
    save_eti_signal, get_active_eti_signals, get_eti_signal_by_id, update_eti_signal_status
)

MODULE = "ETI_CONSUMER"
ETI_BASE_URL = os.getenv("ETI_BASE_URL", "https://eti-zeta-one.vercel.app").rstrip("/")


async def check_eti_connection() -> Dict[str, Any]:
    """Valida la conectividad HTTP con el servicio ETI en producción o local."""
    start_time = time.perf_counter()
    url = f"{ETI_BASE_URL}/"
    headers = {"User-Agent": "eTrade-Options-Engine/2.3"}

    try:
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)

            if resp.status_code == 200:
                html_text = resp.text
                has_eti_title = "eTrade Trading Intelligence" in html_text or "ETI" in html_text
                has_robot_section = "ROBOT ETRADE" in html_text or "Matriz de Apertura" in html_text
                
                # Buscar activos proyectados visibles
                detected_symbols = [s for s in ["META", "NVDA", "SPX", "SPY", "QQQ"] if s in html_text]

                return {
                    "connected": True,
                    "target_url": url,
                    "status_code": resp.status_code,
                    "latency_ms": elapsed_ms,
                    "eti_service_detected": has_eti_title,
                    "robot_dispatch_active": has_robot_section,
                    "detected_symbols": detected_symbols,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            else:
                return {
                    "connected": False,
                    "target_url": url,
                    "status_code": resp.status_code,
                    "latency_ms": elapsed_ms,
                    "error": f"Servidor respondió con código {resp.status_code}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
    except Exception as e:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
        log_warning(MODULE, f"Error conectando con {url}: {e}")
        return {
            "connected": False,
            "target_url": url,
            "status_code": None,
            "latency_ms": elapsed_ms,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


def ingest_raw_eti_signal(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Ingesta y valida un payload emitido por ETI (vía WebSocket, REST push o archivo)."""
    try:
        sig = ETISignal.model_validate(payload)
        sig.get_or_create_tactical_instruction()
        ok = save_eti_signal(sig)
        if ok:
            log_info(MODULE, f"⚡ [RADAR CUÁNTICO ETI] Señal recibida y almacenada: {sig.signal_id} ({sig.symbol} {sig.asset_class})")
            return {"ok": True, "signal_id": sig.signal_id, "status": sig.status}
        else:
            return {"ok": False, "error": "Fallo al guardar la señal en disco/DB"}
    except Exception as e:
        log_error(MODULE, f"Error validando señal ETI: {e}")
        return {"ok": False, "error": str(e)}


async def sync_signals_from_live_eti() -> Dict[str, Any]:
    """
    Sincroniza señales activas directamente desde el servicio ETI desplegado.
    Intenta REST y, en caso de Vercel/Next.js frontend, parsea la Matriz de Apertura en tiempo real.
    """
    url = f"{ETI_BASE_URL}/"
    headers = {"User-Agent": "Mozilla/5.0 eTrade/1.0 (Windows NT 10.0; Win64; x64)"}

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                log_warning(MODULE, f"ETI respondió con status {resp.status_code}")
                return {"ok": False, "error": f"HTTP {resp.status_code}", "ingested_count": 0}

            html = resp.text

            # Extraer bloques next_f generados por Next.js App Router
            chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*)"\]\)', html)
            full_data = "".join(chunks).replace('\\"', '"').replace('\\n', '\n')
            if not full_data:
                full_data = html

            # Extraer Régimen FDE y Guardrail O-13 de la cabecera macro
            regime_match = re.search(r'R[eé]gimen FDE:\s*([A-Za-z]+)', full_data)
            live_regime = regime_match.group(1).upper() if regime_match else "DECELERATION"
            if live_regime not in ("DECELERATION", "EXPANSION", "STAGFLATION", "RECOVERY"):
                live_regime = "DECELERATION"

            conf_match = re.search(r'Confianza Causal.*?([0-9]{2})%', full_data)
            live_conf = float(conf_match.group(1)) if conf_match else 88.0
            has_o13_puts_only = "ALLOW_PUTS_ONLY" in full_data or "Bloqueado: Compras direccionales de CALLs" in full_data

            now = datetime.now(timezone.utc)
            now_str = now.strftime("%Y%m%d")
            today_date = now.strftime("%Y-%m-%d")
            exp_iso = datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=timezone.utc).isoformat()

            # Extracción robusta por símbolo en la Matriz de Apertura Robot eTrade Dispatcher
            symbols_to_extract = ["META", "NVDA", "SPX", "SPY", "QQQ"]
            ingested = []

            for sym in symbols_to_extract:
                pattern = rf'text-cyan-400","children":"{sym}"(.*?children":"(ARMADO|STANDBY|DISPARADO|EJECUTADO)")'
                match = re.search(pattern, full_data, re.DOTALL)
                if not match:
                    continue

                block = match.group(1)
                status = match.group(2)

                # Escenario
                scen_m = re.search(r'children":"([^"]*(?:BEARISH|BULLISH)[^"]*)"', block)
                scenario = scen_m.group(1) if scen_m else "▼ BEARISH (PUT 0DTE)"

                # Precios
                num_strings = re.findall(r'\"([0-9,]+\.[0-9]{2})\"', block)
                prices = [float(p.replace(",", "")) for p in num_strings]

                ref_price = prices[0] if len(prices) > 0 else 500.0
                trigger = prices[1] if len(prices) > 1 else round(ref_price * 0.995, 2)
                stop = prices[2] if len(prices) > 2 else round(ref_price * 1.005, 2)
                t1 = prices[3] if len(prices) > 3 else round(trigger * 0.985, 2)
                t2 = prices[4] if len(prices) > 4 else round(trigger * 0.990, 2)

                # Racional
                rat_m = re.search(r'(?:title|children)":"([^"]*(?:Playbook|Aduana|Alta Beta|Rotaci|P[eé]rdida|VIX)[^"]*)"', block)
                rationale = rat_m.group(1) if rat_m else f"Señal cuantitativa ETI para {sym}"

                is_put = "PUT" in scenario.upper() or "BEARISH" in scenario.upper()
                is_0dte = "0DTE" in scenario.upper()
                opt_type = "PUT" if is_put else "CALL"
                strike = round(trigger * 0.995, 1) if is_put else round(trigger * 1.005, 1)

                sig_dict = {
                    "signal_id": f"eti-live-{sym.lower()}-{now_str}",
                    "timestamp": now.isoformat(),
                    "expires_at": exp_iso,
                    "cadence": "PRE_MARKET",
                    "status": "ACTIVE" if status == "ARMADO" else "STANDBY",
                    "symbol": sym,
                    "asset_class": "OPTION_0DTE" if is_0dte else "OPTION_WEEKLY",
                    "action": "BUY_TO_OPEN",
                    "options_contract": {
                        "contract_symbol": f"{sym}{now.strftime('%y%m%d')}{opt_type[0]}{int(strike*1000):08d}",
                        "option_type": opt_type,
                        "strike": strike,
                        "expiration_date": today_date,
                        "dte": 0 if is_0dte else 2,
                        "target_delta": -0.42 if is_put else 0.42,
                        "max_bid_ask_spread_pct": 3.5,
                        "estimated_contract_price": 2.50
                    },
                    "strategy": {
                        "horizon": "SCALPING",
                        "bias": "BEARISH" if is_put else "BULLISH",
                        "playbook_rule": scenario.replace("▼ ", "").replace("▲ ", ""),
                        "expected_duration_minutes": 25 if is_0dte else 45
                    },
                    "causal_context": {
                        "fde_regime": live_regime,
                        "fcg_confidence_pct": live_conf,
                        "primary_source": "Yoel Sardiñas (FCG Playbook)" if "Yoel" in rationale else "ETI System Dynamics",
                        "catalyst_summary": f"[O-13: ALLOW_PUTS_ONLY · FDE: {live_regime}] {rationale}" if has_o13_puts_only else rationale,
                        "catalyst_impact_score": -0.80 if is_put else 0.80,
                        "greeks_thesis": "Aceleración gamma institucional al quebrar nivel clave." if is_put else "Expansión delta alcista."
                    },
                    "technical_gate": {
                        "trigger_type": "VWAP_REJECTION" if "VWAP" in rationale else "PRICE_BREAKOUT",
                        "underlying_trigger_price": trigger,
                        "trigger_operator": "LESS_THAN_OR_EQUAL" if is_put else "GREATER_THAN_OR_EQUAL",
                        "indicator_requirements": {
                            "vwap_condition": "PRICE_BELOW_VWAP" if is_put else "PRICE_ABOVE_VWAP",
                            "ema_fast_vs_slow": "FAST_BELOW_SLOW" if is_put else "FAST_ABOVE_SLOW",
                            "min_relative_volume": 1.25,
                            "timeframe_confirmation": "2m"
                        }
                    },
                    "risk_management": {
                        "invalidation_underlying": stop,
                        "stop_loss_contract_pct": -20.0,
                        "take_profit_1_pct": 40.0,
                        "take_profit_2_pct": 85.0,
                        "runner_trailing_stop_pct": 20.0,
                        "max_account_risk_pct": 2.5
                    },
                    "safety_guardrails": {
                        "execution_allowed": True,
                        "max_slippage_pct": 1.5,
                        "circuit_breaker_active": False
                    }
                }

                sig = ETISignal.model_validate(sig_dict)
                sig.get_or_create_tactical_instruction()
                save_eti_signal(sig)
                ingested.append(sig.signal_id)

            log_info(MODULE, f"Sincronización exitosa con ETI: {len(ingested)} señales procesadas ({ingested})")
            return {
                "ok": True,
                "source": url,
                "ingested_count": len(ingested),
                "signals": ingested,
                "timestamp": now.isoformat()
            }

    except Exception as e:
        log_error(MODULE, f"Error durante sincronización con ETI en {url}: {e}")
        return {"ok": False, "error": str(e), "ingested_count": 0}


async def send_signal_feedback_to_eti(
    signal_id: str,
    status: str,
    route_used: Optional[str] = None,
    fill_price: Optional[float] = None,
    slippage_pct: Optional[float] = None,
    notes: Optional[str] = None
) -> bool:
    """Envía reporte de ejecución o descarte a ETI para alimentar su calibración causal."""
    url = f"{ETI_BASE_URL}/api/eti/v1/etrade/signals/feedback"
    payload = {
        "signal_id": signal_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "execution_route": route_used or "NONE",
        "fill_price": fill_price,
        "slippage_pct": slippage_pct,
        "feedback_notes": notes or f"Procesada en eTrade Robot vía {route_used}"
    }

    # Actualizar estado interno y en disco
    update_eti_signal_status(signal_id, status, route_used)

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code in (200, 201):
                log_info(MODULE, f"Feedback enviado con éxito a ETI para {signal_id}: {status}")
                return True
            else:
                log_info(MODULE, f"ETI endpoint {url} devolvió status {resp.status_code}; telemetría persistida localmente.")
                return True
    except Exception as e:
        log_info(MODULE, f"Telemetría de feedback persistida localmente (ETI remote no disponible: {e}).")
        return True
