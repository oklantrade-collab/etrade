"""
warrior_experience_ingestor.py — Proceso de Ingesta y Aprendizaje del Playbook de Ross Cameron

Nombre Canónico del Proceso:
============================
  "WARRIOR_EXPERIENCE_INGESTOR"  (Ingestor de Experiencias y Playbook Warrior)

Permite incorporar videos diarios, bitácoras operativas y análisis de casos reales
de Ross Cameron para alimentar continuamente la base de conocimiento y el comportamiento
táctico de los robots de eTrade.

Uso por CLI:
------------
  python -m app.stocks.warrior_experience_ingestor --file ruta_al_video_caso.json
  python -m app.stocks.warrior_experience_ingestor --demo

Uso por Código / API:
---------------------
  from app.stocks.warrior_experience_ingestor import ingest_warrior_experience
  result = ingest_warrior_experience(payload_dict)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

from app.core.logger import log_error, log_info, log_warning
from app.stocks.warrior_playbook_engine import (
    WarriorSession,
    WarriorTrade,
    WarriorTradePhase,
    warrior_playbook,
)

PROCESS_NAME = "WARRIOR_EXPERIENCE_INGESTOR"
MODULE = "PLAYBOOK_INGESTOR"


def parse_session_payload(data: Dict[str, Any]) -> WarriorSession:
    """Parsea un diccionario JSON/estructurado a objetos WarriorSession, WarriorTrade y WarriorTradePhase."""
    session_date = str(data.get("session_date", "2024-01-01"))
    video_title = str(data.get("video_title", "Warrior Trading Daily Recap"))
    video_url = str(data.get("video_url", ""))
    net_pnl = float(data.get("net_pnl", 0.0))
    account_mode = str(data.get("account_mode", "main_account"))
    prior_drawdown = float(data.get("prior_drawdown", 0.0))
    mental_state = str(data.get("mental_state", ""))
    key_mindset_change = str(data.get("key_mindset_change", ""))
    stop_trading_discipline = str(data.get("stop_trading_discipline", ""))
    notes = str(data.get("notes", ""))

    trades: List[WarriorTrade] = []
    raw_trades = data.get("trades", [])

    for rt in raw_trades:
        phases: List[WarriorTradePhase] = []
        for idx, rp in enumerate(rt.get("phases", []), 1):
            phases.append(
                WarriorTradePhase(
                    sequence_order=int(rp.get("sequence_order", idx)),
                    phase_type=str(rp.get("phase_type", "ENTRY")),
                    price_level=float(rp.get("price_level", 0.0)),
                    trigger_observed=str(rp.get("trigger_observed", "")),
                    action_taken=str(rp.get("action_taken", "")),
                    risk_factor=str(rp.get("risk_factor", "")),
                    result_outcome=str(rp.get("result_outcome", "")),
                    timestamp_or_time_str=rp.get("timestamp_or_time_str"),
                    shares=rp.get("shares"),
                )
            )

        trade = WarriorTrade(
            ticker=str(rt.get("ticker", "")).upper(),
            archetype_code=str(rt.get("archetype_code", "ROSS_VWAP_BOUNCE_CLEAN")),
            pnl=float(rt.get("pnl", 0.0)),
            duration_seconds=int(rt.get("duration_seconds", 300)),
            sector=str(rt.get("sector", "Small Cap Momentum")),
            float_shares=float(rt.get("float_shares", 10_000_000)),
            running_surge_pct=float(rt.get("running_surge_pct", 50.0)),
            avg_entry_price=float(rt.get("avg_entry_price", 0.0)),
            avg_exit_price=float(rt.get("avg_exit_price", 0.0)),
            key_takeaway=str(rt.get("key_takeaway", "")),
            peak_unrealized_pnl=float(rt.get("peak_unrealized_pnl", 0.0)),
            giveback_pnl=float(rt.get("giveback_pnl", 0.0)),
            max_shares_held=rt.get("max_shares_held"),
            phases=phases,
        )
        trades.append(trade)

    return WarriorSession(
        session_date=session_date,
        video_title=video_title,
        video_url=video_url,
        net_pnl=net_pnl,
        account_mode=account_mode,
        prior_drawdown=prior_drawdown,
        mental_state=mental_state,
        key_mindset_change=key_mindset_change,
        stop_trading_discipline=stop_trading_discipline,
        notes=notes,
        trades=trades,
    )


def ingest_warrior_experience(
    payload: Dict[str, Any], persist_supabase: bool = True
) -> Dict[str, Any]:
    """
    Función principal del proceso WARRIOR_EXPERIENCE_INGESTOR.
    Recibe la bitácora estructurada, valida los campos, genera el modelo
    y lo registra en el motor de inferencia y en la base de datos.
    """
    try:
        session = parse_session_payload(payload)
        success = warrior_playbook.add_session(
            session, persist_supabase=persist_supabase
        )

        log_info(
            MODULE,
            f"✅ [PROCESO {PROCESS_NAME}] Sesión {session.session_date} ({session.video_title}) "
            f"ingestada con éxito. Net PnL: ${session.net_pnl:,.2f} | Trades: {len(session.trades)}",
        )

        return {
            "success": success,
            "process": PROCESS_NAME,
            "session_date": session.session_date,
            "video_title": session.video_title,
            "net_pnl": session.net_pnl,
            "trades_count": len(session.trades),
            "tickers": [t.ticker for t in session.trades],
            "message": f"Experiencia incorporada al cerebro táctico del robot exitosamente.",
        }
    except Exception as e:
        log_error(MODULE, f"Error en {PROCESS_NAME}: {e}")
        return {"success": False, "process": PROCESS_NAME, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(
        description="WARRIOR_EXPERIENCE_INGESTOR — Ingesta de bitácoras y videos de Ross Cameron"
    )
    parser.add_argument(
        "--file", type=str, help="Ruta al archivo JSON con la experiencia estructurada"
    )
    parser.add_argument(
        "--demo", action="store_true", help="Ingestar caso de demostración"
    )
    args = parser.parse_args()

    if args.demo:
        demo_payload = {
            "session_date": "2024-07-02",
            "video_title": "+$18,450 on Low Float Momentum Gapper",
            "video_url": "https://www.youtube.com/watch?v=warrior_demo",
            "net_pnl": 18450.00,
            "account_mode": "main_account",
            "prior_drawdown": 0.0,
            "mental_state": "Paciencia y espera de volumen calificado.",
            "key_mindset_change": "No anticipar antes de las 9:30 AM si el spread no está apretado.",
            "stop_trading_discipline": "Cerrar terminal a las 10:15 AM tras alcanzar objetivo.",
            "notes": "Operación de rebote en EMA9 con confirmación en velas de 5s.",
            "trades": [
                {
                    "ticker": "RDHL",
                    "archetype_code": "ROSS_VWAP_BOUNCE_CLEAN",
                    "pnl": 18450.00,
                    "duration_seconds": 240,
                    "sector": "Biotecnología",
                    "float_shares": 5200000,
                    "running_surge_pct": 65.0,
                    "avg_entry_price": 2.45,
                    "avg_exit_price": 3.10,
                    "key_takeaway": "Comprar rebote en EMA9 en primer retroceso de 1 minuto sin romper VWAP.",
                    "phases": [
                        {
                            "sequence_order": 1,
                            "phase_type": "ENTRY",
                            "price_level": 2.45,
                            "trigger_observed": "Toque en EMA9 con soporte en VWAP $2.40",
                            "action_taken": "Comprar 25,000 acciones",
                            "risk_factor": "Pérdida de soporte en $2.38",
                            "result_outcome": "Impulso vertical hacia $3.15",
                        },
                        {
                            "sequence_order": 2,
                            "phase_type": "EXIT",
                            "price_level": 3.10,
                            "trigger_observed": "Doble techo en $3.15 con vela doji en 1m",
                            "action_taken": "Vender 100% de la posición",
                            "risk_factor": "Retroceso abrupto",
                            "result_outcome": "+$18,450 asegurados en 4 minutos",
                        },
                    ],
                }
            ],
        }
        res = ingest_warrior_experience(demo_payload, persist_supabase=False)
        print(json.dumps(res, indent=2))
        sys.exit(0)

    if args.file:
        if not os.path.exists(args.file):
            print(f"Error: no existe el archivo {args.file}")
            sys.exit(1)
        with open(args.file, "r", encoding="utf-8") as f:
            data = json.load(f)
        res = ingest_warrior_experience(data)
        print(json.dumps(res, indent=2))
        sys.exit(0)

    parser.print_help()


if __name__ == "__main__":
    main()
