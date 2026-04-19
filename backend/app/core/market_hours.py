from datetime import datetime, time, timezone, timedelta

def get_nyc_now():
    """
    Returns the current time in NYC (ET).
    Since we don't have pytz, we estimate based on UTC.
    NYC is typically UTC-5 (EST) and UTC-4 (EDT).
    As of April, it is EDT (UTC-4).
    """
    # UTC Now
    utc_now = datetime.now(timezone.utc)
    # Estimate NYC time (UTC-4 for EDT)
    nyc_now = utc_now - timedelta(hours=4)
    return nyc_now

def is_market_open():
    """
    Checks if the US stock market (NYC) is currently open.
    Market Hours: Mon-Fri 09:30 - 16:00 ET.
    """
    now = get_nyc_now()
    
    # Check if it's a weekday (0=Monday, 4=Friday)
    if now.weekday() > 4:
        return False, "CERRADO (Fin de semana)"
        
    start_time = time(9, 30)
    end_time = time(16, 0)
    current_time = now.time()
    
    # Simple open/close check
    if start_time <= current_time <= end_time:
        return True, "ABIERTO"
        
    if current_time < start_time:
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
