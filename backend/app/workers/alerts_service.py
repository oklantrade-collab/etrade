import os
import httpx
from datetime import datetime
from app.core.logger import log_error, log_info, log_warning
from app.core.config import settings
from app.core.supabase_client import get_supabase
from app.core.memory_store import BOT_STATE

async def send_telegram_message(mensaje: str):
    """Envía mensaje a Telegram respetando la configuración de enable/disable."""
    # 1. Config Check (Lazy load)
    token = settings.telegram_bot_token or os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = settings.telegram_chat_id or os.getenv('TELEGRAM_CHAT_ID')

    if not token or not chat_id:
        log_warning("alerts_service", "Telegram Token or Chat ID not found. Message ignored.")
        return

    # 2. Status Check (trading_config)
    # We use memory cache if available, else we query DB
    enabled = True
    if BOT_STATE.config_cache and 'telegram_enabled' in BOT_STATE.config_cache:
        enabled = BOT_STATE.config_cache['telegram_enabled']
    else:
        try:
            sb = get_supabase()
            res = sb.table("trading_config").select("telegram_enabled").eq("id", 1).maybe_single().execute()
            if res.data:
                enabled = res.data.get('telegram_enabled', True)
        except: pass

    if not enabled:
        log_info("alerts_service", "Telegram deactivated in trading_config. Message ignored.")
        return

    url = f'https://api.telegram.org/bot{token}/sendMessage'
    try:
        # Usamos async post de httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json={
                'chat_id': chat_id,
                'text': mensaje,
                'parse_mode': 'Markdown'
            })
    except Exception as e:
        log_error("alerts_service", f"Error sending Telegram message: {e}")

def send_email_message(subject: str, text: str):
    if not SENDGRID_API_KEY or not ALERT_EMAIL_TO or not ALERT_EMAIL_FROM:
        return
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail, Email, To, Content
        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        from_email = Email(ALERT_EMAIL_FROM)
        to_email = To(ALERT_EMAIL_TO)
        content = Content("text/plain", text)
        mail = Mail(from_email, to_email, subject, content)
        sg.client.mail.send.post(request_body=mail.get())
    except Exception as e:
        log_error("alerts_service", f"Error sending Email: {e}")

async def send_trade_alert(executed_order: dict):
    try:
        side_emoji = '🟢' if executed_order['side'] == 'BUY' else '🔴'
        side_text  = 'BUY (LONG)' if executed_order['side'] == 'BUY' else 'SELL (SHORT)'
        
        mensaje = f"""
{side_emoji} *TRADE EJECUTADO — eTrader*

*Símbolo:* `{executed_order['symbol']}`
*Dirección:* {side_text}
*Cantidad:* `{executed_order['quantity']}`

*Precio entrada:* `${executed_order['entry_price']:,.4f}`
*Stop Loss:*      `${executed_order['stop_loss']:,.4f}`
*Take Profit:*    `${executed_order['take_profit']:,.4f}`

*R/R Ratio:* `{executed_order.get('rr_ratio', 2.5)}x`
*Comisión:*  `${executed_order.get('commission', 0):.4f}`
*Valor orden:* `${executed_order['quantity'] * executed_order['entry_price']:,.2f} USDT`

_OCO Order activa en Binance_
"""
        await send_telegram_message(mensaje)
    except Exception as e:
        log_error("alerts_service", f"send_trade_alert failed: {e}")

async def send_kill_switch_alert(reason: str):
    try:
        mensaje = f"""
🚨 *KILL SWITCH ACTIVADO — eTrader*

*Razón:* {reason}
*Hora:* {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC

⚠️ Trading detenido. Todas las posiciones cerradas.
Para reactivar: Risk Manager → bot\\_active = True
"""
        for _ in range(3):
            try:
                await send_telegram_message(mensaje)
                send_email_message("KILL SWITCH ACTIVADO", mensaje)
                break
            except:
                pass
    except Exception as e:
        log_error("alerts_service", f"send_kill_switch_alert failed: {e}")

async def send_daily_summary(supabase_client):
    try:
        now = datetime.utcnow()
        if now.hour == 20 and now.minute < 15:
            today_start = now.replace(hour=0,minute=0,second=0).isoformat()
            
            closed_today = supabase_client.table('positions') \
                .select('realized_pnl, close_reason, symbol') \
                .eq('status', 'closed') \
                .gte('closed_at', today_start) \
                .execute().data
            
            total_pnl     = sum(float(p['realized_pnl']) for p in closed_today)
            winning       = len([p for p in closed_today if float(p['realized_pnl']) > 0])
            losing        = len([p for p in closed_today if float(p['realized_pnl']) <= 0])
            total_trades  = len(closed_today)
            win_rate      = (winning / total_trades * 100) if total_trades > 0 else 0
            
            pnl_emoji = '📈' if total_pnl >= 0 else '📉'
            
            mensaje = f"""
{pnl_emoji} *RESUMEN DIARIO — eTrader*
_{now.strftime('%d/%m/%Y')}_

*PnL del día:* `{'+'if total_pnl>=0 else ''}{total_pnl:.2f} USDT`
*Trades:* {total_trades} | ✅ {winning} | ❌ {losing}
*Win Rate:* {win_rate:.1f}%
"""
            await send_telegram_message(mensaje)
            send_email_message("RESUMEN DIARIO eTrader", mensaje)
    except Exception as e:
        log_error("alerts_service", f"send_daily_summary failed: {e}")

async def send_position_closed_alert(position: dict, close_reason: str, realized_pnl: float):
    try:
        emoji_reason = '🎯' if close_reason == 'TP_HIT' else '⛔'
        emoji_result = '✅' if realized_pnl >= 0 else '📉'
        pnl_sign     = '+' if realized_pnl >= 0 else ''
        
        mensaje = f"""
{emoji_result} *POSICIÓN CERRADA — eTrader*

*Símbolo:*  `{position['symbol']}`
*Dirección:* {'📈 LONG' if position.get('side', '') == 'LONG' else '📉 SHORT'}
*Cierre:*   {emoji_reason} {close_reason.replace('_', ' ')}

*Entrada:*  `${position.get('entry_price', 0):,.4f}`
*Salida:*   `${position.get('current_price', 0):,.4f}`
*PnL:*      `{pnl_sign}{realized_pnl:.2f} USDT`
"""
        await send_telegram_message(mensaje)
    except Exception as e:
        log_error("alerts_service", f"send_position_closed_alert failed: {e}")

async def send_spike_notable_alert(
    symbol: str, 
    spike_ratio: float, 
    direction: str,
    score_final: float,
    threshold: float
):
    try:
        if spike_ratio > 3.0:
            emoji_dir = '🟢' if direction == 'BULLISH' else '🔴'
            
            mensaje = f"""⚡ *SPIKE NOTABLE (sin orden) — eTrader*

{emoji_dir} *{direction}* en `{symbol}`
*Ratio:*  ×{spike_ratio:.2f}
*Score MTF:* {score_final:.2f} (umbral: {threshold})
→ Score insuficiente, no se abrió posición
"""
            await send_telegram_message(mensaje)
    except Exception as e:
        log_error("alerts_service", f"send_spike_notable_alert failed: {e}")
async def send_parameter_guardrail_alert(
    parameter_name: str,
    old_value: float,
    new_value: float,
    reason: str,
    is_oob: bool,
    backtest_ev: float | None = None,
    accepted: bool = False
):
    try:
        status_emoji = '✅' if accepted else ('🚨' if is_oob else '🛡️')
        status_text = 'ACEPTADO' if accepted else ('FUERA DE RANGO (Requiere Aprobación)' if is_oob else 'RECHAZADO (EV Negativo)')
        
        ev_text = f"Expected Value (EV): `{backtest_ev:.4f}`" if backtest_ev is not None else "EV: `N/A`"
        
        dashboard_url = "https://etrade-frontend.render.com/settings" # TODO: De config si es posible
        
        mensaje = f"""
{status_emoji} *GUARDRAIL DE PARÁMETROS — eTrader*

*Parámetro:* `{parameter_name}`
*Valor Anterior:* `{old_value}`
*Valor Propuesto:* `{new_value}`
*Estado:* {status_text}

*Motivo:* _{reason}_
{ev_text}

[Ver Dashboard de Control]({dashboard_url})
"""
        await send_telegram_message(mensaje)
    except Exception as e:
        log_error("alerts_service", f"send_parameter_guardrail_alert failed: {e}")
