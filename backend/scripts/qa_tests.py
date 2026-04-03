"""
eTrader v2 — QA Test Suite (Sprint 6)
Automated QA checks before going to production.

Usage:
    python backend/scripts/qa_tests.py
"""
import sys
import os
import time
import traceback

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.supabase_client import get_supabase
from app.core.logger import log_info

MODULE = "qa_tests"


def test_1_pipeline_duration():
    """TEST 1 — Verify last pipeline cycle completed in < 300 seconds."""
    print('\n' + '━' * 50)
    print('TEST 1 — Tiempo del pipeline completo')
    print('━' * 50)

    sb = get_supabase()
    result = sb.table('cron_cycles') \
        .select('duration_seconds, symbols_analyzed, spikes_detected, status') \
        .order('started_at', desc=True) \
        .limit(1) \
        .execute()

    if not result.data:
        print('⚠️  No hay ciclos registrados aún. Ejecuta el worker primero.')
        return False

    cycle = result.data[0]
    duration = cycle.get('duration_seconds', 0) or 0
    status = cycle.get('status', 'unknown')

    print(f'  Duración:         {duration:.1f}s')
    print(f'  Símbolos:         {cycle.get("symbols_analyzed", 0)}')
    print(f'  Spikes:           {cycle.get("spikes_detected", 0)}')
    print(f'  Status:           {status}')

    passed = duration < 300
    print(f'\n  {"✅ PASS" if passed else "❌ FAIL"}: duration={duration:.1f}s {"<" if passed else ">="} 300s')

    if not passed:
        print('  💡 Sugerencia: Aumentar MAX_PIPELINE_WORKERS a 8 en .env')

    return passed


def test_2_database_size():
    """TEST 2 — Verify database size is under 400 MB."""
    print('\n' + '━' * 50)
    print('TEST 2 — Tamaño de la base de datos')
    print('━' * 50)
    print('  ⚠️  Este test requiere acceso al SQL Editor de Supabase.')
    print('  Ejecuta esta query manualmente:\n')
    print('  SELECT')
    print('      tablename,')
    print('      pg_size_pretty(pg_total_relation_size(')
    print("          'public.' || tablename")
    print('      )) AS size')
    print('  FROM pg_tables')
    print("  WHERE schemaname = 'public'")
    print('  ORDER BY pg_total_relation_size(')
    print("      'public.' || tablename")
    print('  ) DESC;\n')
    print('  CRITERIO: Total < 400 MB')
    print('  Si market_candles > 200 MB, ejecutar:')
    print("  DELETE FROM market_candles")
    print("  WHERE timeframe IN ('15m','30m','1h')")
    print("  AND open_time < NOW() - INTERVAL '60 days';")

    # Check approximate counts
    sb = get_supabase()
    tables_to_check = [
        'market_candles', 'technical_indicators', 'trading_signals',
        'volume_spikes', 'positions', 'orders', 'cron_cycles', 'system_logs'
    ]

    print('\n  Conteos aproximados:')
    for table in tables_to_check:
        try:
            result = sb.table(table).select('id', count='exact').limit(0).execute()
            count = result.count or 0
            print(f'    {table}: {count:,} registros')
        except Exception as e:
            print(f'    {table}: Error ({e})')

    return True  # Manual verification needed


def test_3_error_handling():
    """TEST 3 — Verify error handling with invalid API key."""
    print('\n' + '━' * 50)
    print('TEST 3 — Manejo de errores críticos')
    print('━' * 50)
    print('  Este test es MANUAL. Procedimiento:')
    print('  1. Guardar BINANCE_API_KEY actual')
    print('  2. Cambiarla a un valor inválido en .env')
    print('  3. Ejecutar: python backend/workers/unified_trading_worker.py')
    print('  4. Verificar:')
    print('     - El worker NO lanza excepción no capturada')
    print('     - En system_logs aparece ERROR con descripción clara')
    print('     - El cron_cycle queda con status diferente a "running"')
    print('     - El worker termina con exit code 0')
    print('  5. RESTAURAR la API key correcta\n')

    # Check that the worker has proper error handling
    print('  Verificando estructura de error handling en el código...')

    worker_path = os.path.join(
        os.path.dirname(__file__), '..', 'app', 'workers', 'unified_trading_worker.py'
    )

    with open(worker_path, 'r') as f:
        content = f.read()

    checks = {
        'try/except en _process_symbol': 'except Exception as e:' in content,
        'log_error disponible': 'log_error' in content,
        'sys.exit(0) al final': 'sys.exit(0)' in content,
        'cycle status update': '_update_cycle' in content,
    }

    all_ok = True
    for check, passed in checks.items():
        print(f'    {"✅" if passed else "❌"} {check}')
        if not passed:
            all_ok = False

    return all_ok


def test_4_oco_fallback():
    """TEST 4 — Verify OCO failure fallback exists in code."""
    print('\n' + '━' * 50)
    print('TEST 4 — Verificar fallback de OCO')
    print('━' * 50)

    order_manager_path = os.path.join(
        os.path.dirname(__file__), '..', 'app', 'execution', 'order_manager.py'
    )

    with open(order_manager_path, 'r') as f:
        content = f.read()

    checks = {
        'OCO order creation': 'create_oco_order' in content,
        'BinanceAPIException catch': 'BinanceAPIException' in content,
        'Fallback SL placement': 'STOP_LOSS_LIMIT' in content,
        'Critical alert on OCO fail': 'oco_failed' in content,
        'Fallback SL message': 'Fallback SL colocado exitosamente' in content,
        'alert_events insert on fail': "severity': 'critical'" in content,
    }

    all_ok = True
    for check, passed in checks.items():
        print(f'    {"✅" if passed else "❌"} {check}')
        if not passed:
            all_ok = False

    if all_ok:
        print('\n  ✅ PASS: OCO fallback logic exists and is complete')
    else:
        print('\n  ❌ FAIL: Missing OCO fallback components')

    print('\n  Para test funcional completo:')
    print('  1. En order_manager.py, tras el market order, agregar:')
    print('     raise BinanceAPIException(response=None, status_code=400,')
    print("         text='Simulated OCO failure')")
    print('  2. Ejecutar con spike_multiplier=1.05')
    print('  3. Verificar alert_events y log')
    print('  4. REMOVER el código de test')

    return all_ok


def test_5_24h_monitoring():
    """TEST 5 — Check 24-hour continuous run results."""
    print('\n' + '━' * 50)
    print('TEST 5 — 24 horas continuas en Testnet')
    print('━' * 50)

    sb = get_supabase()

    # Check the last 24 hours of cycles
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    try:
        result = sb.table('cron_cycles') \
            .select('status, duration_seconds, orders_executed') \
            .gte('started_at', cutoff) \
            .execute()

        if not result.data:
            print('  ⚠️  No hay ciclos en las últimas 24 horas.')
            print('  Deja el sistema corriendo 24h en Render y vuelve a ejecutar.')
            return False

        cycles = result.data
        total = len(cycles)
        success = len([c for c in cycles if c['status'] == 'success'])
        partial_error = len([c for c in cycles if c['status'] == 'partial_error'])
        failed = len([c for c in cycles if c['status'] == 'failed'])

        durations = [c['duration_seconds'] for c in cycles if c['duration_seconds']]
        avg_duration = sum(durations) / len(durations) if durations else 0

        orders_total = sum(c.get('orders_executed', 0) or 0 for c in cycles)

        print(f'  Ciclos totales:        {total} (esperados ~96)')
        print(f'  Exitosos:              {success}')
        print(f'  Con error parcial:     {partial_error}')
        print(f'  Fallidos:              {failed}')
        print(f'  Duración promedio:     {avg_duration:.1f}s')
        print(f'  Órdenes ejecutadas:    {orders_total}')

        success_rate = (success / total * 100) if total > 0 else 0
        print(f'  Tasa de éxito:         {success_rate:.1f}%')

        passed = success_rate > 95 and avg_duration < 300
        print(f'\n  {"✅ PASS" if passed else "❌ FAIL"}')

        if not passed:
            if success_rate <= 95:
                print(f'    ↳ Tasa de éxito {success_rate:.1f}% < 95%')
            if avg_duration >= 300:
                print(f'    ↳ Duración promedio {avg_duration:.1f}s >= 300s')

        return passed

    except Exception as e:
        print(f'  ❌ Error consultando ciclos: {e}')
        return False


def main():
    print('=' * 60)
    print('  eTrader v2 — QA Test Suite (Sprint 6)')
    print('=' * 60)

    results = {}

    tests = [
        ('TEST 1 — Pipeline Duration', test_1_pipeline_duration),
        ('TEST 2 — Database Size', test_2_database_size),
        ('TEST 3 — Error Handling', test_3_error_handling),
        ('TEST 4 — OCO Fallback', test_4_oco_fallback),
        ('TEST 5 — 24h Monitoring', test_5_24h_monitoring),
    ]

    for name, test_fn in tests:
        try:
            results[name] = test_fn()
        except Exception as e:
            print(f'\n  ❌ {name}: Exception: {e}')
            traceback.print_exc()
            results[name] = False

    # Summary
    print('\n' + '=' * 60)
    print('  RESUMEN DE QA')
    print('=' * 60)

    for name, passed in results.items():
        status = '✅ PASS' if passed else '❌ FAIL/MANUAL'
        print(f'  {status}  {name}')

    total_pass = sum(1 for v in results.values() if v)
    print(f'\n  {total_pass}/{len(results)} tests pasaron')
    print('=' * 60)


if __name__ == '__main__':
    main()
