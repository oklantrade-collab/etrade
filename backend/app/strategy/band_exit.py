def evaluate_band_exit(
    position:      dict,
    current_price: float,
    next_target:   dict,
    mtf_score:     float,
    ai_result:     dict,
    config:        dict
) -> dict:
    """
    Evalúa si se debe cerrar en la banda
    Fibonacci actual usando confirmación
    de MTF y/o IA de Claude.

    REGLA:
      Precio cerca de la banda (dentro del 0.3%)
      Y (MTF retrocediendo O vela lapida IA)
      → CERRAR

      Precio en la banda pero MTF fuerte y IA alcista
      → DEJAR CORRER a siguiente banda

      Precio en la banda y señal mixta (débil pero positivo)
      → CIERRE PARCIAL 50%
    """
    side         = position.get('side', '').lower()
    target_price = next_target['target_price']
    target_name  = next_target['target_name']
    target_zone  = next_target['target_zone']

    # ── 0. ¿Hay ganancia mínima para permitir el cierre?
    entry_price   = float(position.get('avg_entry_price', 0))
    min_profit_pct = float(config.get('min_profit_exit_pct', 0.30))

    if entry_price > 0:
        if side in ['long', 'buy']:
            pnl_pct = (current_price - entry_price) / entry_price * 100
        else:
            pnl_pct = (entry_price - current_price) / entry_price * 100

        if pnl_pct < min_profit_pct:
            return {
                'action': 'hold',
                'reason': (
                    f'P&L {pnl_pct:.2f}% menor que '
                    f'mínimo {min_profit_pct:.2f}%. '
                    f'No cerrar hasta tener ganancia.'
                )
            }

    # ── 1. ¿Está el precio cerca de la banda?
    if target_price == 0:
        return {'action': 'hold', 'reason': 'precio de banda inválido (0)'}
        
    distance_pct = abs(
        current_price - target_price
    ) / target_price * 100

    at_band = distance_pct <= 0.30  # dentro del 0.3%

    if not at_band:
        return {'action': 'hold',
                'reason': 'precio lejos de la banda'}

    # ── 2. Evaluar MTF
    mtf_threshold  = float(
        config.get('exit_mtf_threshold', 0.0)
    )
    mtf_retreating = mtf_score < mtf_threshold
    mtf_weak       = 0.0 <= mtf_score <= 0.30
    mtf_strong     = mtf_score > 0.50

    # ── 3. Evaluar señal de IA
    ai_sentiment   = ai_result.get(
        'market_sentiment', 'indecision'
    )
    ai_candle_type = ai_result.get(
        'candle_type', ''
    )

    # Vela lapida = señal de rechazo en resistencia
    is_gravestone = (
        'gravestone' in (ai_candle_type or '').lower() or
        'lapida'     in (ai_candle_type or '').lower() or
        'shooting'   in (ai_candle_type or '').lower() or
        ai_result.get('is_gravestone', False)
    )

    ai_bearish = ai_sentiment in (
        'bearish', 'reversal'
    )
    ai_bullish = ai_sentiment in (
        'bullish', 'continuation'
    )

    # ── 4. Determinar acción

    # SEÑAL FUERTE DE SALIDA:
    # MTF retrocediendo O (precio en banda + vela lapida)
    strong_exit = mtf_retreating or (
        at_band and is_gravestone
    )

    # SEÑAL FUERTE DE CONTINUAR:
    # MTF fuerte Y IA alcista
    strong_continue = mtf_strong and ai_bullish

    # SEÑAL DÉBIL (mixta):
    # MTF débil positivo o IA neutral
    mixed_signal = (
        mtf_weak and not ai_bearish and not is_gravestone
    )

    if strong_exit and not strong_continue:
        # Determinar tipo de cierre
        # target_zone: 0=basis, 1=upper_1, 2=upper_2
        # Abs para manejar zonas negativas de short
        abs_zone = abs(target_zone)
        
        if abs_zone <= 2:
            # Banda baja (basis, upper_1, upper_2)
            # → cierre parcial 50%
            return {
                'action':      'partial_close',
                'pct':         0.50,
                'reason':      (
                    f'Banda {target_name}: '
                    f'MTF={mtf_score:.2f} retrocediendo'
                    + (' + vela lapida' if is_gravestone
                       else '')
                ),
                'target_name': target_name,
                'target_zone': target_zone
            }
        else:
            # Banda alta (upper_3 a upper_6)
            # → cierre total
            return {
                'action':      'full_close',
                'reason':      (
                    f'Banda {target_name}: '
                    f'MTF={mtf_score:.2f} + confirmación IA'
                ),
                'target_name': target_name,
                'target_zone': target_zone
            }

    elif strong_continue:
        return {
            'action': 'hold',
            'reason': (
                f'Precio en {target_name} pero '
                f'MTF={mtf_score:.2f} fuerte '
                f'y IA={ai_sentiment}. '
                f'Dejar correr a siguiente banda.'
            )
        }

    elif mixed_signal:
        # Señal mixta → cierre parcial siempre
        return {
            'action': 'partial_close',
            'pct':    0.50,
            'reason': (
                f'Señal mixta en {target_name}: '
                f'MTF={mtf_score:.2f} débil. '
                f'Asegurando 50%.'
            ),
            'target_name': target_name,
            'target_zone': target_zone
        }

    return {
        'action': 'hold',
        'reason': 'Sin confirmación suficiente'
    }
