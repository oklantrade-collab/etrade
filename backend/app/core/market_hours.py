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
    now = get_nyc_now()
    
    # Calculate regular market open and close times today
    return {
        "is_open": is_open,
        "status": status_text,
        "nyc_time": now.strftime("%H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "open_time": "09:30:00",
        "close_time": "16:00:00",
        "is_trading_day": now.weekday() <= 4 and ("Feriado" not in status_text)
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
