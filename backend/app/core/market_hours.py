from datetime import datetime, time, timezone, timedelta

def get_nyc_now():
    # UTC Now
    utc_now = datetime.now(timezone.utc)
    # Estimate NYC time (UTC-4 for EDT)
    nyc_now = utc_now - timedelta(hours=4)
    return nyc_now

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
    import pandas_market_calendars as mcal
    import pandas as pd
    
    now = get_nyc_now()
    
    # Check if it's a weekday (0=Monday, 4=Friday)
    if now.weekday() > 4:
        return False, "CERRADO (Fin de semana)"
        
    try:
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
    
    return {
        "is_open": is_open,
        "status": status_text,
        "nyc_time": now.strftime("%H:%M:%S"),
        "date": now.strftime("%Y-%m-%d")
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
