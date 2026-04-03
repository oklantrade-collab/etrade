# eTrader v2 — Runbook de Operación

> Manual operativo para el sistema de trading automatizado eTrader.
> Última actualización: Sprint 6

---

## 1. INICIO NORMAL DEL SISTEMA

### Verificaciones de arranque

| # | Verificación | Cómo verificar | Criterio |
|---|-------------|----------------|----------|
| 1 | Cron Job activo | Render Dashboard → etrader-unified-worker → Status | Status = "Active" |
| 2 | Último ciclo exitoso | Supabase → `cron_cycles` → último registro | `status = 'success'` y `started_at < 15 min` |
| 3 | Dashboard accesible | Abrir `/dashboard` en el navegador | Last Cycle muestra fecha reciente |
| 4 | Bot activo | Supabase → `risk_config` | `bot_active = true` |

### Query de verificación rápida
```sql
SELECT status, started_at, duration_seconds, symbols_analyzed, errors
FROM cron_cycles
ORDER BY started_at DESC
LIMIT 3;
```

---

## 2. ACTIVAR / DESACTIVAR EL BOT

### Desactivar (pausa sin cerrar posiciones)

**Opción A — Dashboard:**
- Ir a `/risk` → Click en "Pause Bot"

**Opción B — Supabase:**
```sql
UPDATE risk_config SET bot_active = false;
```

### Reactivar

**Opción A — Dashboard:**
- Ir a `/risk` → Cambiar Bot Status a ACTIVE

**Opción B — Supabase:**
```sql
UPDATE risk_config SET bot_active = true;
```

> [!IMPORTANT]
> "Pause Bot" **NO** cierra posiciones abiertas. Solo detiene la apertura de nuevas órdenes.
> Las OCO activas en Binance siguen vigentes para proteger posiciones existentes.

---

## 3. QUÉ HACER SI EL KILL SWITCH SE ACTIVA

### Síntomas
- 🚨 Llega alerta **CRÍTICA** por Telegram
- El dashboard muestra "Bot detenido"
- Los ciclos muestran `status = 'skipped_kill_switch'`

### Procedimiento

1. **Revisar en Binance** que todas las posiciones están cerradas:
   - Ir a [binance.com](https://www.binance.com) → Spot → Open Orders
   - Verificar que NO hay órdenes activas ni posiciones abiertas

2. **Revisar el motivo** en system_logs:
   ```sql
   SELECT message, context, created_at 
   FROM system_logs 
   WHERE level = 'CRITICAL' 
   ORDER BY created_at DESC 
   LIMIT 5;
   ```

3. **Analizar la causa:**
   - ¿Movimiento extremo del mercado?
   - ¿Bug en el cálculo de PnL?
   - ¿Error de API?

4. **Solo reactivar cuando estés seguro:**
   ```sql
   UPDATE risk_config 
   SET bot_active = true, 
       kill_switch_triggered = false;
   ```

> [!CAUTION]
> NUNCA reactivar el Kill Switch sin antes verificar manualmente en Binance
> que no hay posiciones abiertas sin protección OCO.

---

## 4. QUÉ HACER SI EL CRON JOB FALLA EN RENDER

### Síntomas
- Render envía email de fallo del cron job
- El dashboard muestra Last Cycle con `status = 'failed'`
- No llegan alertas del sistema

### Procedimiento

1. **Ver logs del fallo:**
   - Render Dashboard → etrader-unified-worker → Logs
   - Buscar el error más reciente

2. **Errores comunes y soluciones:**

   | Error | Causa probable | Solución |
   |-------|---------------|----------|
   | Timeout (>600s) | Demasiados símbolos o workers | Reducir `MAX_PIPELINE_WORKERS` o `top_symbols` |
   | Supabase connection error | Límite de conexiones alcanzado | Verificar `SUPABASE_URL` y reiniciar |
   | Binance connection error | API keys expiradas o IP bloqueada | Verificar API keys en Render env vars |
   | ModuleNotFoundError | Dependencia faltante | Verificar `requirements.txt` y re-deploy |

3. **Reiniciar manualmente** desde Render si es necesario:
   - Render Dashboard → etrader-unified-worker → Manual Run

4. **CRÍTICO:** Verificar que posiciones abiertas tienen OCO:
   ```sql
   SELECT p.symbol, p.status, o.oco_list_client_id
   FROM positions p
   LEFT JOIN orders o ON p.order_id = o.id
   WHERE p.status = 'open';
   ```
   - Si alguna posición NO tiene `oco_list_client_id` → verificar manualmente en Binance

---

## 5. CAMBIAR PARÁMETROS DE RIESGO

### Parámetros seguros de ajustar EN OPERACIÓN (sin parar el bot)

| Parámetro | Descripción | Rango sugerido |
|-----------|-------------|----------------|
| `max_risk_per_trade_pct` | % del capital arriesgado por trade | 0.5% - 2.0% |
| `sl_multiplier` | Multiplicador ATR para Stop Loss | 1.5 - 3.0 |
| `mtf_signal_threshold` | Umbral mínimo de score MTF | 0.55 - 0.80 |
| `max_daily_loss_pct` | Pérdida diaria máxima | 2% - 5% |

> Los cambios aplican en el **PRÓXIMO** ciclo (no el actual).

### Parámetros que requieren PARAR el bot primero

| Parámetro | Razón |
|-----------|-------|
| `spike_multiplier` | Afecta directamente el volumen de señales generadas |
| `rr_ratio` | Cambia SL/TP en órdenes nuevas |
| `max_open_trades` | Podría abrir posiciones inmediatamente |

```sql
-- Ejemplo: ajustar a modo conservador
UPDATE risk_config SET
    max_risk_per_trade_pct = 0.5,
    sl_multiplier = 2.5,
    max_daily_loss_pct = 2.0;

-- Ejemplo: ajustar spike_multiplier (PARAR BOT ANTES)
UPDATE risk_config SET bot_active = false;
UPDATE system_config SET value = '3.0' WHERE key = 'spike_multiplier';
-- Esperar al siguiente ciclo
UPDATE risk_config SET bot_active = true;
```

---

## 6. PASAR DE TESTNET A PRODUCCIÓN LIVE

### Prerequisitos (verificar TODOS antes de ejecutar)

- [ ] Test de 24 horas en Testnet completado
- [ ] Al menos 1 ciclo completo: spike → señal → orden → OCO → cierre por SL o TP
- [ ] Kill Switch probado y funcionando
- [ ] Telegram alertas llegando correctamente
- [ ] Backtest ejecutado con resultados coherentes
- [ ] Este Runbook leído y entendido

### PASO 1 — Preparar credenciales Live

1. En [binance.com](https://www.binance.com) → Account → API Management → Create API
2. Nombre: `eTrader-Production`
3. Permisos:
   - ✅ Enable Reading
   - ✅ Enable Spot & Margin Trading
   - ❌ **NUNCA** activar Enable Withdrawals
4. Restringir acceso a IP de Render (mejor práctica)
5. Guardar API Key y Secret en lugar seguro

### PASO 2 — Parar el bot

```sql
UPDATE risk_config SET bot_active = false;

-- Verificar que no hay posiciones abiertas
SELECT COUNT(*) FROM positions WHERE status = 'open';
-- → Debe ser 0
```

### PASO 3 — Cambiar variables en Render

En Render Dashboard → etrader-unified-worker → Environment:

| Variable | Cambiar a |
|----------|-----------|
| `BINANCE_API_KEY` | Nueva key de producción |
| `BINANCE_SECRET` | Nuevo secret de producción |
| `BINANCE_TESTNET` | **`false`** ← CRÍTICO |

**NO cambiar:** `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`

### PASO 4 — Configurar parámetros conservadores

```sql
UPDATE risk_config SET
    max_risk_per_trade_pct = 0.5,   -- 0.5% (mitad del normal)
    max_open_trades        = 1,     -- solo 1 posición a la vez
    max_daily_loss_pct     = 2.0,   -- stop diario en 2%
    kill_switch_loss_pct   = 1.5,   -- kill switch muy sensible
    sl_multiplier          = 2.5,   -- stop más amplio para ruido
    bot_active             = false; -- aún desactivado

UPDATE system_config 
SET value = '3.0' 
WHERE key = 'spike_multiplier';     -- muy selectivo al inicio
```

### PASO 5 — Verificar conectividad

```bash
python backend/scripts/test_binance_connection.py
```

Criterio:
- ✅ Conexión OK
- ✅ Balance USDT Live: $XXX.XX (tu capital real)
- ✅ BTCUSDT step_size correcto

### PASO 6 — Primer ciclo manual supervisado

```sql
UPDATE risk_config SET bot_active = true;
```

```bash
python backend/workers/unified_trading_worker.py
```

Monitorear en tiempo real:
- Terminal: ver logs
- Supabase: tabla `cron_cycles`
- Binance.com: verificar que no se abrió ninguna orden inesperada

### PASO 7 — Monitoreo las primeras 72 horas

| Hora | Acción |
|------|--------|
| Cada 4-6h | Revisar dashboard |
| Cada 8h | Verificar OCO en Binance.com |
| Si orden sin OCO | Activar Kill Switch **inmediatamente** |
| Después de 72h | Ajustar a parámetros normales |

```sql
-- Después de 72h sin incidentes:
UPDATE risk_config SET
    max_risk_per_trade_pct = 1.0,
    max_open_trades        = 3;

UPDATE system_config 
SET value = '2.5' 
WHERE key = 'spike_multiplier';
```

---

## 7. QUERIES ÚTILES DE MONITOREO

### Resumen de las últimas 24 horas
```sql
SELECT 
    COUNT(*) as ciclos_totales,
    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as exitosos,
    SUM(CASE WHEN status = 'partial_error' THEN 1 ELSE 0 END) as con_error,
    AVG(duration_seconds) as duracion_promedio,
    SUM(orders_executed) as ordenes_total
FROM cron_cycles
WHERE started_at > NOW() - INTERVAL '24 hours';
```

### Posiciones abiertas con detalle
```sql
SELECT 
    p.symbol, p.side, p.entry_price, p.current_price, 
    p.unrealized_pnl, p.stop_loss, p.take_profit,
    o.oco_list_client_id
FROM positions p
LEFT JOIN orders o ON p.order_id = o.id
WHERE p.status = 'open';
```

### PnL por día (últimos 7 días)
```sql
SELECT 
    DATE(closed_at) as dia,
    COUNT(*) as trades,
    SUM(realized_pnl) as pnl_total,
    AVG(realized_pnl) as pnl_promedio
FROM positions
WHERE status = 'closed' 
AND closed_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(closed_at)
ORDER BY dia DESC;
```

### Errores recientes
```sql
SELECT module, message, created_at
FROM system_logs
WHERE level IN ('ERROR', 'CRITICAL')
ORDER BY created_at DESC
LIMIT 20;
```

### Tamaño de la base de datos
```sql
SELECT 
    tablename,
    pg_size_pretty(pg_total_relation_size('public.' || tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size('public.' || tablename) DESC;
```

---

## 8. CONTACTO Y ESCALACIÓN

- **Logs del sistema:** Render Dashboard → Logs
- **Base de datos:** Supabase Dashboard → Table Editor
- **Exchange:** Binance.com → Open Orders / Trade History
- **Alertas:** Telegram Bot → eTrader

> [!NOTE]
> El sistema está diseñado para ser conservador. Con `spike_multiplier = 3.0` y 
> `mtf_signal_threshold = 0.65` al inicio, es posible que pasen varios días sin 
> señales — eso es **correcto**. Resiste la tentación de bajar los umbrales en 
> las primeras semanas.
