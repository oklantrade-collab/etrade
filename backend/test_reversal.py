import asyncio
import sys
import os

# Mock the MODULE for independent testing
MODULE = "TEST"

async def check_signal_reversal(
    position:     dict,
    current_mtf:  float,
    current_price: float,
    config:       dict
) -> dict:
    if not config.get('exit_on_signal_reversal', True):
        return {'should_exit': False}

    side      = position.get('side', '').lower()
    entry     = float(position.get('avg_entry_price') or position.get('entry_price') or 0)
    threshold = float(config.get('exit_mtf_threshold', 0.0))
    min_pct   = float(config.get('min_profit_exit_pct', 0.30))
    min_usd   = float(config.get('min_profit_exit_usd', 1.00))

    if entry == 0:
        return {'should_exit': False}

    # Calcular P&L actual
    if side == 'long':
        pnl_pct = (current_price - entry) / entry * 100
    else:
        pnl_pct = (entry - current_price) / entry * 100

    capital  = float(position.get('size', 0)) * entry
    pnl_usd  = capital * (pnl_pct / 100)

    # Verificar si MTF giró en contra
    mtf_reversed = (
        (side == 'long'  and current_mtf < threshold) or
        (side == 'short' and current_mtf > abs(threshold))
    )

    if not mtf_reversed:
        return {'should_exit': False}

    # MTF giró — pero ¿hay ganancia mínima?
    has_min_profit = (
        pnl_pct >= min_pct or
        pnl_usd >= min_usd
    )

    if not has_min_profit:
        return {
            'should_exit': False,
            'mtf_reversed': True,
            'waiting_for_profit': True,
            'current_pnl_pct': round(pnl_pct, 2),
            'needed_pct': min_pct,
            'detail': (
                f'MTF giró ({current_mtf:.4f}) pero '
                f'P&L {pnl_pct:.2f}% < mínimo {min_pct}%. '
                f'Esperando recuperación o SL.'
            )
        }

    return {
        'should_exit':   True,
        'reason':        'signal_reversal_with_profit',
        'pnl_pct':       round(pnl_pct, 2),
        'pnl_usd':       round(pnl_usd, 2),
        'current_mtf':   current_mtf,
        'detail': (
            f'MTF giró a {current_mtf:.4f} y '
            f'P&L = +{pnl_pct:.2f}% (+${pnl_usd:.2f}). '
            f'Asegurando ganancia.'
        )
    }

async def run_tests():
    config = {
        'exit_on_signal_reversal': True,
        'exit_mtf_threshold': 0.00,
        'min_profit_exit_pct': 0.30,
        'min_profit_exit_usd': 1.00
    }
    
    # Caso A — MTF negativo SIN ganancia → NO salir:
    pos_a = {'side':'long', 'avg_entry_price': 70934, 'size': 0.00634}
    price_a = 69329  # pérdida actual
    mtf_a = -0.35
    res_a = await check_signal_reversal(pos_a, mtf_a, price_a, config)
    print("\n--- Caso A (MTF Negativo, No Ganancia) ---")
    print(f"MTF: {mtf_a}, Price: {price_a}")
    print(f"Result: should_exit={res_a['should_exit']}, waiting_for_profit={res_a.get('waiting_for_profit')}")
    print(f"Detail: {res_a.get('detail')}")

    # Caso B — MTF negativo CON ganancia → SALIR:
    price_b = 71150  # ganancia +0.30% approx
    mtf_b = -0.35
    res_b = await check_signal_reversal(pos_a, mtf_b, price_b, config)
    print("\n--- Caso B (MTF Negativo, Con Ganancia) ---")
    print(f"MTF: {mtf_b}, Price: {price_b}")
    print(f"Result: should_exit={res_b['should_exit']}, reason={res_b.get('reason')}")
    print(f"Detail: {res_b.get('detail')}")

    # Caso C — MTF positivo → NO salir:
    mtf_c = 0.45
    res_c = await check_signal_reversal(pos_a, mtf_c, price_b, config)
    print("\n--- Caso C (MTF Positivo) ---")
    print(f"MTF: {mtf_c}, Price: {price_b}")
    print(f"Result: should_exit={res_c['should_exit']}")

if __name__ == "__main__":
    asyncio.run(run_tests())
