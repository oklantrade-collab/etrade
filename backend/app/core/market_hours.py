from zoneinfo import ZoneInfo
from datetime import datetime, time, timezone, timedelta

try:
    NYC_TZ = ZoneInfo("America/New_York")
except Exception:
    NYC_TZ = None

def get_nyc_now():
    if NYC_TZ:
        return datetime.now(NYC_TZ)
    # Fallback to UTC-4
    utc_now = datetime.now(timezone.utc)
    return utc_now - timedelta(hours=4)

def get_lima_now():
    """Returns current time in Lima (UTC-5)."""
    utc_now = datetime.now(timezone.utc)
    return utc_now - timedelta(hours=5)

def convert_to_lima(dt_utc):
    """Converts a UTC datetime to Lima time."""
    if not dt_utc.tzinfo:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(timezone(timedelta(hours=-5)))

def is_market_open():
    """
    Checks if the US stock market (NYSE) is currently open.
    Uses pandas_market_calendars to detect holidays and half-days.
    """
    now = get_nyc_now()
    
    # Check if it's a weekday (0=Monday, 4=Friday)
    if now.weekday() > 4:
        return False, "CERRADO (Fin de semana)"
        
    try:
        import pandas_market_calendars as mcal
        import pandas as pd
        # Get NYSE calendar
        nyse = mcal.get_calendar('NYSE')
        today_str = now.strftime('%Y-%m-%d')
        
        # schedule() returns a DataFrame of open/close times
        schedule = nyse.schedule(start_date=today_str, end_date=today_str)
        
        if schedule.empty:
            return False, "CERRADO (Feriado bursátil)"
            
        # Extract market open/close times (returned as UTC Pandas Timestamps)
        market_open = schedule.iloc[0]['market_open']
        market_close = schedule.iloc[0]['market_close']
        
        # Compare with current UTC time
        utc_now = datetime.now(timezone.utc)
        utc_now_ts = pd.Timestamp(utc_now)
        
        if utc_now_ts < market_open:
            return False, "CERRADO (Pre-Apertura)"
        elif utc_now_ts > market_close:
            return False, "CERRADO (Post-Cierre)"
        else:
            return True, "ABIERTO"
            
    except Exception as e:
        # Fallback to simple time logic if library fails
        print(f"Error checking market calendar: {e}")
        start_time = time(9, 30)
        end_time = time(16, 0)
        current_time = now.time()
        
        if start_time <= current_time <= end_time:
            return True, "ABIERTO"
        elif current_time < start_time:
            return False, "CERRADO (Pre-Apertura)"
        else:
            return False, "CERRADO"

def get_market_status_dict():
    is_open, status_text = is_market_open()
    now_nyc = get_nyc_now()
    now_lima = get_lima_now()
    
    total_sec_today = now_nyc.hour * 3600 + now_nyc.minute * 60 + now_nyc.second
    open_sec = 9 * 3600 + 30 * 60  # 09:30:00 (34200)
    close_sec = 16 * 3600           # 16:00:00 (57600)

    active_time_str = ""
    remaining_time_str = ""
    time_to_open_str = ""
    summary_str = ""

    if is_open:
        elapsed_sec = max(0, total_sec_today - open_sec)
        remain_sec = max(0, close_sec - total_sec_today)
        
        h_el, rem = divmod(elapsed_sec, 3600)
        m_el, s_el = divmod(rem, 60)
        active_time_str = f"{h_el}h {m_el:02d}m"
        
        h_rem, rem = divmod(remain_sec, 3600)
        m_rem, s_rem = divmod(rem, 60)
        if h_rem > 0:
            remaining_time_str = f"{h_rem}h {m_rem:02d}m"
        else:
            remaining_time_str = f"{m_rem}m {s_rem:02d}s"
            
        summary_str = f"Activo {active_time_str} • Cierra en {remaining_time_str}"
    else:
        # Calculate time until next market open
        if now_nyc.weekday() <= 4 and total_sec_today < open_sec:
            # Pre-market on a trading day
            diff_sec = open_sec - total_sec_today
            h_diff, rem = divmod(diff_sec, 3600)
            m_diff, s_diff = divmod(rem, 60)
            if h_diff > 0:
                time_to_open_str = f"{h_diff}h {m_diff:02d}m"
            else:
                time_to_open_str = f"{m_diff}m {s_diff:02d}s"
            summary_str = f"Abre en {time_to_open_str}"
        else:
            # Post-market or weekend
            days_ahead = 1
            wd = now_nyc.weekday()
            if wd == 4:    # Friday after close -> Monday
                days_ahead = 3
            elif wd == 5:  # Saturday -> Monday
                days_ahead = 2
            elif wd == 6:  # Sunday -> Monday
                days_ahead = 1
            sec_left_today = max(0, 86400 - total_sec_today)
            sec_future = (days_ahead - 1) * 86400 + open_sec
            total_wait_sec = sec_left_today + sec_future
            h_w, rem = divmod(total_wait_sec, 3600)
            m_w, _ = divmod(rem, 60)
            time_to_open_str = f"{h_w}h {m_w:02d}m"
            if wd >= 4:
                summary_str = f"Abre el lunes en {time_to_open_str}"
            else:
                summary_str = f"Abre mañana en {time_to_open_str}"

    return {
        "is_open": is_open,
        "status": status_text,
        "nyc_time": now_nyc.strftime("%H:%M:%S"),
        "lima_time": now_lima.strftime("%H:%M:%S"),
        "date": now_nyc.strftime("%Y-%m-%d"),
        "open_time": "09:30:00",
        "close_time": "16:00:00",
        "is_trading_day": now_nyc.weekday() <= 4 and ("Feriado" not in status_text),
        "active_time_str": active_time_str,
        "remaining_time_str": remaining_time_str,
        "time_to_open_str": time_to_open_str,
        "summary_str": summary_str
    }

def is_forex_market_open() -> bool:
    """
    Checks if the Forex market is open.
    Forex is open from Sunday 5:00 PM EST to Friday 5:00 PM EST.
    """
    now = get_nyc_now()
    
    # 0 = Monday, ..., 4 = Friday, 5 = Saturday, 6 = Sunday
    if now.weekday() == 5:
        # Saturday is always closed
        return False
    elif now.weekday() == 6:
        # Sunday: open after 5:00 PM (17:00)
        if now.hour >= 17:
            return True
        return False
    elif now.weekday() == 4:
        # Friday: closed at/after 5:00 PM (17:00)
        if now.hour >= 17:
            return False
        return True
    
    # Monday to Thursday
    return True


def is_options_market_open(buffer_start_min: int = 5, buffer_end_min: int = 5) -> tuple[bool, str]:
    """
    Verifica si el mercado de opciones de EE.UU. (CBOE/NYSE) está abierto y en horario seguro de negociación.
    Horario regular: 09:30 a 16:00 EST.
    Horario seguro con buffer: 09:35 a 15:55 EST (evita spreads caóticos de apertura y rechazos de post-cierre).
    """
    now = get_nyc_now()
    if now.weekday() > 4:
        return False, "CERRADO (Fin de semana)"

    # Verificar calendario bursátil general (feriados)
    is_open_stk, reason_stk = is_market_open()
    if not is_open_stk:
        return False, f"CERRADO ({reason_stk})"

    # Hora en NYC con buffers
    nyc_time = now.time()
    t_start = time(9, 30 + buffer_start_min)  # 09:35 EST
    t_end = time(16 - 1, 60 - buffer_end_min)  # 15:55 EST

    if nyc_time < t_start:
        return False, f"CERRADO (Buffer Inicial hasta 09:35 EST, actual: {nyc_time.strftime('%H:%M')})"
    if nyc_time >= t_end:
        return False, f"CERRADO (Buffer Final desde 15:55 EST, actual: {nyc_time.strftime('%H:%M')})"

    return True, "ABIERTO (Opciones)"
