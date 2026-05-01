def calculate_fibonacci_zone(current_price: float, basis: float, atr: float) -> int:
    """
    Calculates the Fibonacci Bollinger zone for a given price.
    Multipliers: [1.0, 1.618, 2.618, 3.618, 4.236, 5.618]
    Returns 0 (neutral), 1 to 6 (bullish zones), or -1 to -6 (bearish zones).
    """
    if not atr or atr <= 0:
        return 0
        
    multipliers = [1.0, 1.618, 2.618, 3.618, 4.236, 5.618]
    zone = 0
    
    for idx in range(6, 0, -1):
        # Bullish side
        if current_price > basis + (atr * multipliers[idx-1]):
            zone = idx
            break
        # Bearish side
        if current_price < basis - (atr * multipliers[idx-1]):
            zone = -idx
            break
            
    return zone
