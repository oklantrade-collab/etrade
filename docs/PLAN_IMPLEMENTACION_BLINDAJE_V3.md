# Plan de Implementación: Blindaje Operativo V3 (Stocks & Opciones)
## Basado en Auditoría Forense (16/11/2026 – 20/11/2026) y Directivas del Usuario

> **Fecha:** 21 de Noviembre de 2026  
> **Estado:** Desplegado en la nube (`DigitalOcean`), limpieza de BD verificada y tests aprobados (`65/65` local + remoto)  
> **Objetivo:** Corregir las 9 causas raíz de pérdidas y fallos operativos detectados en la semana del 16/11 al 20/11/2026, incorporar la salida temprana post-Bollinger 15m (sin esperar a las 15:00 ET), unificar los límites de inversión directamente desde `Settings` (`5%` del Capital Base para Stocks y `\$800` para Opciones), preparar el sistema para **OPRA US Options Market Data** en vivo y asegurar la integridad de órdenes y contabilidad en TWS / Supabase.

---

## Parte 1: Resumen Ejecutivo Forense (16/11/2026 – 20/11/2026)

### 1.1 Métricas Reales vs. Datos Distorsionados en BD

| Módulo / Segmento | Trades | Ganadas / Perdidas | Win Rate | PnL Real (USD) | Hallazgo Principal |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Opciones — Reales abiertas en la semana** | **50** | **18 W / 32 L** | **36.0%** | **-\$3,414.52** | 49 cerradas (`-$3,300.09`) + 1 abierta fin de semana (`ID 1927 QQQ`, `-$114.43`) |
| ↳ *Intradía puro (mismo día)* | 35 | 12 W / 23 L | 34.3% | -\$868.68 | Dañado por reglas TP/Ratchet disparadas en pérdida y entradas de mediodía |
| ↳ *Retención Overnight (16–20/11)* | 14 | 6 W / 8 L | 42.9% | -\$2,431.41 | 5 PUTs del 16→17 ganaron `+$1,182.79`; los otros 9 perdieron **-\$3,614.20** |
| **Opciones — Carryover (06–14/11 → 16–19/11)** | 10* | 4 W / 6 L | 40.0% | -\$321.43 | 6 CALLs perdieron `-$2,205.35`; 3 trades adicionales sin `exit_credit` causaron asignación `QQQ` |
| **Opciones — Fantasmas / Corruptas (`exit < entry`)** | 20 | 6 W / 13 L / 1 Z | — | *+\$1,086.10 (falso)* | 13 filas con duración negativa sumaron `+$1,109.75` ficticios en BD |
| **Stocks — Compras regulares del bot (18/11)** | **9** | **0 W / 8 L / 1 BE** | **0.0%** | **-\$120.22** | **100% compradas después de las 11:00 ET**; 8 de 9 retenidas overnight |
| **Stocks — Liquidación asignaciones LONG** | 2 | 0 W / 2 L | 0.0% | -\$3,947.08 | `AMZN` 300 sh (`-$3,013.23`, fill real `-$3,117.73`) y `GOOGL` 100 sh (`-$933.85`) |
| **Stocks — Asignación accidental SHORT `QQQ`** | 1 | 1 W / 0 L | 100% | +\$8,713.25 *(azar)* | 3 PUTs ITM exp. 16/11 no cerradas → OCC ejerció `-300 sh` (`$196,445` en corto sin cobertura) |

*Nota sobre dirección y ejecución:*
* **12 de 12 CALLs** (5 de la semana + 7 carryover) terminaron en pérdida (**0.0% Win Rate**, **-\$3,361.07**) en una semana bajista.
* De **530 órdenes** enviadas a `stocks_orders`, **404 fueron canceladas (76.2%)**, solo **107 se llenaron (20.2%)** y **19 quedaron atascadas en `processing`**. En compras de opciones, el fill rate fue apenas **8.3% (`23/278`)**.
* En `system_logs` (viernes 20/11, 162 errores): `56x Error 10090` (sin datos OPRA en vivo), `57x Error 202/201` (rechazo por modificación de orden `Adaptive`), `7x Error 104/10148` (cancelar/modificar órdenes ya llenadas).

### 1.2 Las 9 Causas Raíz Identificadas

1. **Retención Overnight y Ausencia de Hard-Exit EOD para Contratos >0DTE:** `should_exit_by_time()` solo cierra a las `15:45 ET` cuando `now_date == expiry_date`. Además, `is_within_options_sync_import_window()` (`09:30–15:30 ET`) es código muerto sin llamadas en `broker_sync.py` ni `ib_bridge_worker.py`.
2. **Bypass del Blindaje V2 vía `paper_execution.py` y Flag Desactivado en Stocks:** `stocks_scheduler.py` y `stock_driven_options_scanner.py` ejecutan mediante `paper_execution.py`, que omite ventana horaria, `MAX_CONTRACTS_PER_SYMBOL`, tope en USD, ADUANA, Régimen Estructural y `expires_at`. En stocks, `enforce_ross_window` inicia en `False` por defecto y `_get_config()` toma `max(pct_per_operation=10%, max_pct_per_trade=5%) = 10%`.
3. **Sin Suscripción OPRA en Vivo (`Error 10090`) + Fallback `yfinance` Contaminando `Profit Guardian`:** `stocks_scheduler.py` etiqueta cotizaciones retrasadas 15m de `yfinance` como `has_live_opt_quote = True`, inflando `highest_premium_seen` y disparando `OPT_GAP_BE_LOCK_PLUS_1PCT` / `OPT_GAP_TRAIL_TIER2` en pérdida real (`-$350.59`).
4. **Reglas de Take Profit Sin Exigir Ganancia Positiva + `0DTE Guard` en 7 DTE:** `OPT_GAP_TP_CLIMAX` y `OPT_GAP_TP_UPPER6_PARTIAL` / `LOWER6_PARTIAL` cierran en pérdida (`0% WR`, `-$303.95`). `is_zero_dte_opt` se activa por `horizon == "SCALPING"` cerrando contratos de 7 DTE (`1919 PLTR`).
5. **Chaser `Adaptive` Inviable y Cancelación Prematura en `ib_bridge_worker.py`:** Modificar órdenes `Adaptive` con pasos de `\$0.01` provoca rechazos `Error 202/201`. Borrar `PENDING_IB_ORDERS` antes de confirmar cancelación genera posiciones huérfanas sin SL (`1923 NVDA`, `1912 INTC`, `1927 QQQ`).
6. **Fallo Silencioso de `datetime.fromisoformat()` en Python 3.10 + Falta de Guardia Horaria para Stocks:** Microsegundos truncados de PostgREST disparan `ValueError` silenciado por `except: pass`, anulando TTL y deduplicación y causando fills After-Hours (`17:16–18:10 ET`) triplicados (`POWW`, `NRXP`).
7. **Hardcode `'direction': 'sell'` en `stocks_tp_manager.py`:** Al cerrar cortos (`-290 QQQ`) envió 44 órdenes `sell` rechazadas sin deduplicación.
8. **Corrupción Histórica (`exit_time < entry_time`) y Doble Journaling:** Búsqueda de `sell_ord` sin `.gte("filled_at", entry_time)` en `broker_sync.py` / `ib_bridge_worker.py` asoció ventas viejas (`+$1,109.75` falsos); `reconcile_broker_portfolio()` duplicó cada cierre de `on_ib_order_status` en `trades_journal`.
9. **Micro-Sizing en Stocks y Ausencia de Filtro Macro Diario en CALLs:** Órdenes de 2 acciones (`TTWO`, `TGT`) con comisión mínima `\$1` y CALLs contra tendencia diaria `SPY/QQQ` bajista (`0/12`).

---

## Parte 2: Plan de Implementación Técnica (9 Fases: Fase 0 a Fase 8)

### Fase 0: Acción Operativa Inmediata (Apertura Lunes 23/11 09:30 ET)
* **Objetivo:** Evitar pérdida adicional o asignación sobre la posición que quedó abierta el viernes 20/11 a las `15:57:24 ET`.
* **Acción:**
  * Liquidar inmediatamente a la apertura del lunes 23/11 (`09:30–09:35 ET`) el contrato **`ID 1927`: `QQQ 610.0P` (exp. `2026-11-23`, 1x, entrada `\$9.3602`, PnL no realizado `-\$114.43`)** directamente en TWS o invocando `close_all_open_options()` en `backend/app/options/close_all.py`.

---

### Fase 1: Salida Temprana Post-Bollinger 15m + Hard-Exit EOD Incondicional (Cero Overnight / Cero Asignaciones)

#### 1.1 Nuevo Regulador Compartido de Agotamiento Post-Bollinger 15m (Stocks & Opciones)
* **Archivo nuevo:** `backend/app/core/bb15m_exhaustion.py`
* **Requisito del usuario:** *"No esperar a las 15 horas para liquidar una posición, sino también cuando en temporalidad de 15 minutos el precio que ha superado la Bollinger superior (CALL o Stocks) y a la inversa para (PUTs), se mueve lateralmente o descendente."*
* **Lógica exacta en `evaluate_bb15m_post_breakout_exhaustion(df_15m, is_bullish, state, current_price, position_age_minutes)`:**
  * Calcula `BB(20, 2.0)` en 15m (`bb_upper`, `bb_lower`) sobre `df_15m` (requiere mínimo 21 velas).
  * **Para CALLs y Stocks LONG (`is_bullish=True`):**
    1. **Detección persistente de ruptura previa:** Marca `state["bb15m_upper_breakout_seen"] = True` (persistido en `exit_plan` de opciones y `diagnostics` de stocks) si en alguna vela cerrada tras la entrada (o en las últimas 2 velas cerradas `[-3:-1]`) se cumple `high_15m > bb_upper` o `close_15m > bb_upper`.
    2. **Gatillo de liquidación 100% (con maduración mínima `position_age_minutes >= 5.0`):** Si `bb15m_upper_breakout_seen` es `True` y en la vela actual o recién cerrada el movimiento se vuelve **lateral o descendente**:
       * `close_curr <= close_prev` (vela 15m pierde o iguala el cierre previo — estancamiento/giro), **O**
       * `close_curr < open_curr` (vela 15m roja de rechazo tras romper la banda), **O**
       * `current_price < close_prev` (retroceso en tiempo real por debajo del cierre previo de 15m), **O**
       * `high_curr <= high_prev * 1.001` y `(close_curr - close_prev) / close_prev <= 0.0015` (lateralización sin nuevo máximo ni expansión real tras la ruptura).
    3. Retorna cierre del `100%` con regla `OPT_BB15M_EXHAUSTION_EXIT` (opciones) o `STK_BB15M_EXHAUSTION_EXIT` (stocks).
  * **Para PUTs y Stocks SHORT (`is_bullish=False`, lógica inversa exacta):**
    1. **Detección persistente de ruptura previa:** Marca `state["bb15m_lower_breakout_seen"] = True` si `low_15m < bb_lower` o `close_15m < bb_lower`.
    2. **Gatillo de liquidación 100% (`position_age_minutes >= 5.0`):** Si `bb15m_lower_breakout_seen` es `True` y el subyacente se mueve **lateralmente o ascendente**:
       * `close_curr >= close_prev` (freno/rebote en 15m), **O**
       * `close_curr > open_curr` (vela verde de rechazo alcista tras romper banda inferior), **O**
       * `current_price > close_prev` (rebote intravela sobre el cierre previo de 15m), **O**
       * `low_curr >= low_prev * 0.999` y `(close_prev - close_curr) / close_prev <= 0.0015` (lateralización sin nuevo mínimo).
* **Puntos de integración:**
  * `backend/app/options/exit_engine.py`: invocar en `evaluate_technical_rules_and_stops()` (prioritario tras actualización de SL).
  * `backend/app/workers/stocks_scheduler.py`: invocar en el monitor de opciones (líneas ~2755–2850) y asegurar que **`OPT_BB15M_EXHAUSTION_EXIT` / `bb15m_exhaustion`** quede explícitamente exenta de `Candado 1 Bollinger` y `Candado 2 Swing Multi-Semana` en líneas 3016–3039 (añadir `"bb15m"` y `"exhaustion"` a `is_stop_loss_or_invalidation` o crear `is_bb15m_exhaustion`).
  * `backend/app/stocks/aduana_stocks_exit_engine.py` y `backend/app/stocks/position_monitor.py`: invocar después de la verificación EOD (`15:50 ET`) y antes del trailing macro de swing para cerrar `100%` las acciones que pierdan impulso tras superar `BB_Upper` en 15m.

#### 1.2 Hard-Exit EOD Incondicional para Todas las Opciones `DTE <= 7` (`15:45 ET`)
* **Archivos:** `backend/app/options/exit_engine.py` (L1012–1028) y `backend/app/workers/stocks_scheduler.py` (L2882–2896).
* **Acción:**
  * Modificar `should_exit_by_time(position, now, eff)` para forzar `forced_close_time` a partir de las **`15:45 ET`** (`force_close_minutes_before = 15`) cuando `dte_days <= 7` (no solo `now_date == expiry_date`), independientemente de si el PnL está positivo o negativo.
  * Mantener los reintentos cada 15s vía `request_broker_option_close()` (orden `MKT`) hasta confirmar `qty == 0` en TWS.

#### 1.3 Conectar `is_within_options_sync_import_window()` (`09:30–15:30 ET`)
* **Archivos:** `backend/app/options/broker_sync.py` (L20–36, L500–608) y `backend/app/workers/ib_bridge_worker.py` (L1351–1470).
* **Acción:**
  * Invocar `is_within_options_sync_import_window()` antes de reabrir (`target_heal`) o insertar (`v1.0-tws-sync`) cualquier contrato de opción desde TWS en `opt_paper_trades`.
  * **Entre `15:30` y `15:59 ET`:** Si TWS reporta una posición de opción no registrada (o recién cerrada en BD) con `qty > 0`, **no importarla para retenerla**; despachar una orden `SELL MKT` inmediata de liquidación (respetando deduplicación de 45s) para garantizar `qty == 0` antes del cierre.
  * **Desde las `16:00 ET` en adelante / fines de semana:** Bloquear toda inserción o reapertura fantasma en `opt_paper_trades` y emitir alerta Telegram informativa si TWS aún retiene contratos.

---

### Fase 2: Cerrar Puerta Trasera de `paper_execution.py` y Unificar Límites desde `Settings`

#### 2.1 Sizing Exacto de Stocks desde `Settings` (`5%` de `"Capital asignado (Base)"`)
* **Requisito del usuario:** `Settings / "% Inversión por Operación" == 5%` de `"Capital asignado (Base)"`.
* **Archivo:** `backend/app/stocks/stocks_order_executor.py` (`_get_config` L88–116 y `_calculate_shares` L118–140).
* **Acción:**
  * En `_get_config()`:
    * Leer `"Capital asignado (Base)"` desde `trading_config.capital_stocks_spot` (y si no existe o es `<= 0`, fallback a `stocks_config.total_capital_usd`, default `5000.0`).
    * Leer `"% Inversión por Operación"` exclusivamente desde `stocks_config.max_pct_per_trade` (que en `Settings` corresponde al campo `generalForm.max_pct_per_trade`, actualmente `"5"` en BD; default `5.0%` → `0.05`).
    * **Eliminar** `max(float(cfg.get("pct_per_operation", 10.0)), float(cfg.get("max_pct_per_trade", 10.0)))` en la línea 95 (actualmente `pct_per_operation=10` estaba duplicando el sizing al `10%`). Sincronizar `pct_per_operation` cuando se guarde `max_pct_per_trade`.
  * En `_calculate_shares(capital, max_pct, price)`:
    * `target_usd = capital * max_pct` (con `\$5,000` y `5%` = **`\$250.00`** por operación).
    * **Eliminar** el fallback `elif (capital * 0.10) >= price: shares = 1` en la línea 136 (violaba el 5% permitiendo comprar acciones de hasta `\$500`). Si `price > target_usd`, retornar `0` acciones y rechazar la orden con motivo claro (`"Capital asignado por operación (\$250.00) insuficiente para 1 acción"`).
  * **Ventana Ross Cameron Obligatoria en Stocks (L187):**
    * Cambiar `enforce_ross_window` a **`True` por defecto** en `execute_market_order()` para todo ticker/grupo intradía (`HOT`, `ALPHA_RUNNER`, `IPO_SUPER_RUNNER`, `OPEN_GAP_RUNNER`, `inversiones_pro`, `Aa30_STK`, `VOLATILITY_EXPANSION`, `APEX_AUTO`), bloqueando nuevas compras a partir de las **`11:00 ET`** (solo eximiendo estrategias explícitas de tipo `SWING` si están marcadas).
  * **Anti-duplicado en Stocks:** Antes de insertar una compra en `stocks_orders`, verificar que no exista otra orden `pending`/`processing`/`submitted` del mismo `ticker` y dirección `buy` (erradica la triplicación `POWW`/`NRXP`).

#### 2.2 Sizing Exacto de Opciones desde `Settings` (`"Riesgo máximo por operación" == \$800`) y Blindaje de `paper_execution.py`
* **Requisito del usuario:** `Settings / "Riesgo máximo por operación" == 800`.
* **Archivos:**
  * `backend/app/options/settings_defaults.py`
  * `backend/app/options/options_aduana.py` (L124–130)
  * `backend/app/options/stock_driven_options_scanner.py` (L558–580, L700–722)
  * `backend/app/options/paper_execution.py` (L350–492)
  * `backend/app/options/autonomous_options_dispatcher.py` (L126–168)
  * `backend/app/options/intraday_momentum_options_scanner.py` (L574–585)
  * `backend/app/options/eti_autonomous_dispatcher.py` (L179–208)
  * `backend/app/workers/stocks_scheduler.py` (GAP L966–1065 y VME L1110–1163)
* **Acción:**
  1. **Helper centralizado en `settings_defaults.py`:** Crear `get_effective_max_risk_per_trade_usd(sb, eff=None) -> float` que lea `opt_settings` (tabla en BD), aplique `effective_settings()` (`max_risk_per_trade_usd`, default `800.0`) y acote con `hard_caps()["max_risk_per_trade_usd"]`.
  2. **Eliminar el bypass `max_risk_megacap_usd = 1500.0`:** En `options_aduana.py` (L126–128) y `stock_driven_options_scanner.py` (L559–561), usar **siempre** `max_risk_per_trade_usd` (`\$800`) sin elevar el techo a `\$1,500` para megacaps (`SPY/QQQ/NVDA/AMD/...`).
  3. **Blindar `paper_execution.py` (`execute_selected_candidate_to_trade`):**
     * **Ventana de Oro única (`09:35–11:30 ET`):** Bloquear nuevas entradas fuera de `09:35–11:30 ET`.
     * **Tope duro de contratos y riesgo:** Forzar `qty = min(MAX_CONTRACTS_PER_SYMBOL, max(1, int(cand.get("qty") or 1)))` con `MAX_CONTRACTS_PER_SYMBOL = 3`, y validar `entry_debit * 100.0 * qty <= max_risk_usd` (`\$800`). Si incluso `1` contrato excede `\$800`, rechazar (nunca comprar `AMD \$1,925`, `MSFT \$1,205` ni `META \$1,313`). Si `qty > 1` excede `\$800`, reducir `qty = int(max_risk_usd // (entry_debit * 100.0))`.
     * **Filtros obligatorios:** Llamar `is_ticker_in_options_cooldown()`, `evaluate_structural_regime()`, `fetch_and_evaluate_options_gatekeeper()` y añadir **filtro anti-clímax al entrar** (rechazar `PUT` si `RSI 1H <= 20.0` y rechazar `CALL` si `RSI 1H >= 80.0`).
     * **TTL en BD:** Incluir `"expires_at": (now_dt + timedelta(seconds=90)).isoformat()` al insertar en `stocks_orders`.
  4. **Homologar todos los demás dispatchers (`autonomous_options_dispatcher.py`, `eti_autonomous_dispatcher.py`, `stocks_scheduler.py` GAP & VME):**
     * Reemplazar los presupuestos hardcoded (`1000.0`, `200.0`, `capital_limit * 0.20`) por `get_effective_max_risk_per_trade_usd(sb)` (`\$800`).
     * Imponer Ventana de Oro `09:35–11:30 ET` en GAP Runner Opciones, VME Opciones (`VME_EXPANSION_CALL/PUT` disparó hasta las `16:06 ET`), Intraday Momentum OTM y Autonomous Dispatcher.
     * Validar `cost_total <= max_risk_usd` y `total_qty <= MAX_CONTRACTS_PER_SYMBOL (3)`.

---

### Fase 3: Reparación de Reglas TP, `Profit Guardian`, Aislamiento de `yfinance` y `0DTE Guard`
* **Archivos:** `backend/app/options/aduana_gap_runner_options.py` (L1452–1509) y `backend/app/workers/stocks_scheduler.py` (L2641–2710, L2900–2910).
* **Acción:**
  1. **Exigir ganancia positiva en reglas de TP (`aduana_gap_runner_options.py`):**
     * En `OPT_GAP_TP_CLIMAX` (L1452–1473), `OPT_GAP_TP_UPPER6_PARTIAL` (L1489–1497) y `OPT_GAP_TP_LOWER6_PARTIAL` (L1500–1508), añadir la condición **`and unrealized_pnl_pct >= 5.0`**. Si la posición está en pérdida o plana (`< +5%`), un RSI extremo del subyacente no debe disparar un falso "Take Profit" en pérdida.
  2. **Aislar `yfinance` del cálculo de `Profit Guardian` (`stocks_scheduler.py` L2641–2710):**
     * Separar `has_live_tws_quote` (verdadero únicamente cuando el dato proviene de `ib_broker_portfolio` con `broker_port_age <= 30.0` o `opt_quotes_latest` con `market_data_type == "LIVE"`) del fallback `yfinance`.
     * **Prohibido** marcar `has_live_opt_quote = True`, actualizar `highest_premium_seen` o ejecutar `evaluate_option_profit_ratchet()` con precios de `yfinance` (15 min de retraso). Si no hay cotización LIVE de TWS, las salidas de opciones deben guiarse por el precio del subyacente (`SL EMA9 15m`, `BB15m Exhaustion`, `VWAP`, `Hard EOD`).
  3. **Restringir `OPT_0DTE_TIME_DECAY_GUARD` (`stocks_scheduler.py` L2900–2910):**
     * Cambiar la condición `is_zero_dte_opt` para que el cierre temporal de 20–25 minutos aplique **únicamente cuando `dte_days_v <= 1`** (contratos 0DTE o 1DTE), evitando liquidar swings de `7 DTE` por estancamiento de 20 minutos (caso `1919 PLTR`).

---

### Fase 4: Ciclo de Vida de Órdenes en `ib_bridge_worker.py` y `order_execution_plan.py`
* **Archivos:** `backend/app/options/order_execution_plan.py` (L15–130) y `backend/app/workers/ib_bridge_worker.py` (L512–536, L766–890, L1548–1671).
* **Acción:**
  1. **Tick mínimo de opciones (`snap_option_tick`):**
     * En `order_execution_plan.py`, agregar `snap_option_tick(price, tick_size=0.05 if price >= 3.0 else 0.01)`: redondear al múltiplo de `\$0.05` para primas `>= \$3.00` (y `\$0.01` para `< \$3.00`), con paso mínimo de `reprice` de `\$0.05` cuando `cur >= \$3.00`.
  2. **Eliminar `Adaptive` de órdenes sujetas a re-cotización (`ib_bridge_worker.py` L858–866):**
     * No asignar `ib_ord.algoStrategy = "Adaptive"` en órdenes BUY LMT gestionadas por el Chaser, eliminando los rechazos `Error 202/201` al re-cotizar.
  3. **Cancelación segura sin borrar `PENDING_IB_ORDERS` prematuramente (`manage_working_orders`):**
     * Al vencer el TTL o exceder el `max_chase_price`: enviar `self.ib.cancelOrder(ib_oid)`, marcar el registro en `WORKING_IB_ORDERS[ib_oid]["cancel_requested_at"] = now_ts` (o pasarlo a `cancelling` en BD), pero **NO marcar `stocks_orders.status = 'cancelled'` ni hacer `PENDING_IB_ORDERS.pop(ib_oid)`** hasta que `on_ib_order_status` reciba el callback definitivo `Cancelled` o `Filled` de TWS (con timeout de seguridad de `120s` validando `request_open_orders` + `request_broker_positions`). Si TWS responde `Error 10148` o `Filled`, la posición se registrará limpiamente con todas sus reglas.
  4. **Guardia de horario regular para Stocks + `outsideRth = False`:**
     * En `process_pending_orders()` (L773–800): cuando `!is_option` y `direction == "buy"`, verificar `is_market_open()` (salvo `allow_after_hours == true` en `stocks_config`) y asignar explícitamente **`ib_ord.outsideRth = False`**. Si una orden BUY de acción llega fuera de horario, cancelarla limpiamente en lugar de dejarla colgada hasta After-Hours.
  5. **Watchdog de órdenes atascadas en `processing`:**
     * En el ciclo de mantenimiento de `ib_bridge_worker.py`, marcar como `cancelled` cualquier orden en `stocks_orders` que permanezca en `status == 'processing'` durante más de `180s` sin existir en `WORKING_IB_ORDERS` ni en `request_open_orders()`.

---

### Fase 5: Helper Centralizado `parse_iso_utc()` (Compatibilidad Python 3.10 + PostgREST)
* **Archivo nuevo:** `backend/app/core/time_utils.py`
* **Acción:**
  * Implementar `parse_iso_utc(ts: Any) -> datetime | None` normalizando fracciones de segundo de 1–5 dígitos a 6 dígitos mediante regex y asegurando zona horaria UTC (`timezone.utc`), eliminando los fallos silenciosos de `datetime.fromisoformat()` en Python 3.10 cuando PostgREST devuelve `.77588+00:00`.
  * Reemplazar todos los `datetime.fromisoformat(...)` en:
    * `backend/app/workers/ib_bridge_worker.py`
    * `backend/app/options/broker_sync.py`
    * `backend/app/options/paper_execution.py`
    * `backend/app/stocks/position_monitor.py`
    * `backend/app/stocks/stocks_order_executor.py`
    * `backend/app/stocks/aduana_stocks_exit_engine.py`
    * `backend/app/workers/stocks_scheduler.py`

---

### Fase 6: Cierre de Shorts en Stocks, Reconciliación Histórica y Fin del Doble Journaling
* **Archivos:**
  * `backend/app/stocks/stocks_tp_manager.py` (L536–553)
  * `backend/app/options/broker_sync.py` (L652–673)
  * `backend/app/workers/ib_bridge_worker.py` (L450–510, L1229–1246, L1498–1519)
* **Acción:**
  1. **Soporte Short en `stocks_tp_manager.py`:**
     * Calcular `is_short = str(position.get("direction", "long")).lower() in ("short", "sell")` y despachar `direction = "buy" if is_short else "sell"`, incluyendo `group_name = position.get("group_name") or "IB_PAPER"` y deduplicación de `120s` (usando `parse_iso_utc`).
  2. **Filtro temporal en `broker_sync.py` y `ib_bridge_worker.py` (fin de `exit_time < entry_time`):**
     * Al consultar `stocks_orders` (`direction == "sell"`, `status == "filled"`) para cerrar una opción desaparecida de TWS, añadir **`.gte("filled_at", entry_time_iso)`** y validar en Python que `parse_iso_utc(sell_ord["filled_at"]) >= parse_iso_utc(opt_t["entry_time"])`. Si no existe venta posterior a la apertura, usar `last_mark_price` y `now_iso` (nunca asociar fills de días pasados).
  3. **Fin del doble journaling en `trades_journal`:**
     * En `ib_bridge_worker.py` (`reconcile_broker_portfolio` L1229–1246): antes de insertar en `trades_journal`, verificar si ya existe una fila reciente (`exit_date >= now - 120s`) para ese mismo `(ticker, shares, exit_price)` insertada por `on_ib_order_status()` (L453–465). Si ya existe, omitir el segundo `insert`.

---

### Fase 7: Filtro Macro Diario `SPY`/`QQQ` 1D y Disyuntor Diario Global
* **Archivos:**
  * `backend/app/core/circuit_breaker.py`
  * `backend/app/options/paper_execution.py`, `backend/app/options/autonomous_options_dispatcher.py`, `backend/app/options/eti_autonomous_dispatcher.py`, `backend/app/stocks/stocks_order_executor.py`, `backend/app/workers/ib_bridge_worker.py`
* **Acción:**
  1. **Veto Macro Diario (`SPY`/`QQQ` 1D) para CALLs y Stocks LONG:**
     * Crear helper compartido (en `structural_regime_engine.py` o `market_regime_gate.py`, cacheado 5 min) que evalúe `SPY` y `QQQ` en velas 1D + intradía: si ambos tienen `EMA3_1D < EMA9_1D` y `Precio < VWAP`, **bloquear nuevas aperturas de CALLs y compras LONG swing de stocks** (permitiendo únicamente `PUT` o scalping explosivo con catalizador explícito y `RVOL >= 3.0x` antes de las `11:00 ET`).
  2. **Conexión completa del Disyuntor Diario Global (`circuit_breaker.py`):**
     * Corregir el umbral de pérdida diaria en `record_trade_completion()`: usar `-abs(daily_stop_usd)` desde `opt_settings` / `stocks_config` (por defecto `-\$400` a `-\$500` con capital `\$5,000`, en lugar de `-0.5%` de `$100,000` hardcoded) y `consecutive_losses >= 3`.
     * Invocar `can_open_new_trade()` en `paper_execution.py`, `autonomous_options_dispatcher.py`, `eti_autonomous_dispatcher.py`, `stocks_order_executor.py` y `stocks_scheduler.py` (GAP/VME Opciones).
     * Invocar `record_trade_completion()` también al cerrarse una opción en `ib_bridge_worker.py` (`on_ib_order_status` L408) y `broker_sync.py` (L694) para que opciones y stocks compartan el mismo freno diario.

---

### Fase 8: Pruebas Unitarias, Regresión y Saneamiento de BD (Opcional)
* **Archivo de pruebas nuevo:** `backend/tests/test_blindaje_v3_forense.py`
* **Casos obligatorios a verificar:**
  1. **BB15m Exhaustion (CALL / Stock LONG):** Ruptura sobre `BB_Upper(15m)` seguida de vela lateral o bajista → liquida `100%` antes de las `15:00 ET` y no es bloqueada por Candado Bollinger ni Candado Swing.
  2. **BB15m Exhaustion (PUT / Stock SHORT):** Ruptura bajo `BB_Lower(15m)` seguida de vela lateral o alcista → liquida `100%`.
  3. **Hard-Exit EOD y Ventana `broker_sync`:** Opción con `DTE = 4` se cierra forzadamente a las `15:45 ET`; `broker_sync` e `ib_bridge_worker` rechazan importar contratos nuevos tras `15:30 ET` y liquidan huérfanos en `15:30–15:59 ET`.
  4. **Sizing desde `Settings`:** Stocks usa exactamente `5%` del `"Capital asignado (Base)"` (`\$250` con `\$5,000`, rechazando acciones `> \$250`); Opciones usa exactamente `\$800` de `"Riesgo máximo por operación"` incluso en megacaps (`AMD`, `SPY`, `QQQ`) y dentro de `paper_execution.py`.
  5. **TP y `Profit Guardian`:** `OPT_GAP_TP_CLIMAX` / `UPPER6` / `LOWER6` no cierran en pérdida (`pnl < +5%`); `yfinance` nunca arma `highest_premium_seen`; `OPT_0DTE_TIME_DECAY_GUARD` no cierra contratos `7 DTE`.
  6. **TWS Order Lifecycle:** `snap_option_tick` redondea a `\$0.05` si `>= \$3.00`; órdenes BUY LMT no llevan `Adaptive`; `manage_working_orders` no borra `PENDING_IB_ORDERS` hasta recibir callback; stocks rechazan órdenes tras `16:00 ET` con `outsideRth = False`.
  7. **Contabilidad e Integridad:** `parse_iso_utc` parsea microsegundos PostgREST de 5 dígitos; `stocks_tp_manager` cierra `short` con `direction='buy'`; `broker_sync` exige `filled_at >= entry_time`; `reconcile_broker_portfolio` no duplica filas en `trades_journal`.
* **Comando de verificación:**
  * `C:\Users\jyups\AppData\Local\Programs\Python\Python310\Scripts\pytest.exe backend/tests/test_blindaje_v3_forense.py backend/tests/test_warrior_blindaje_v2.py backend/tests/test_profit_guardian_and_trailing.py backend/tests/test_broker_sync_and_dynamic_trailing.py backend/tests/test_ib_order_lifecycle_and_broker_close.py backend/tests/test_bugfixes_options_and_stocks_sync.py -v`
* **Saneamiento Opcional de BD (solo si el usuario lo autoriza expresamente):**
  * Auditar y marcar/limpiar las 13 filas con `exit_time < entry_time` en `opt_paper_trades`, los registros duplicados del 19/11 en `trades_journal`, las 19 órdenes huérfanas en `processing` en `stocks_orders`, y alinear `stocks_config.pct_per_operation = "5"` con `max_pct_per_trade = "5"`.

---

## Parte 3: Guía de Activación de OPRA US Options Market Data (Interactive Brokers)

Para erradicar los `56x [IB Error 10090]` y alimentar al bot con cotizaciones Bid/Ask/Mark en tiempo real de opciones (sin retraso de 15 min):

1. **Suscribirse en la Cuenta LIVE (Client Portal):**
   * Iniciar sesión en **Interactive Brokers Client Portal** con las credenciales de la cuenta **Live** (fondeada).
   * Ir al menú de usuario (icono superior derecho) → **`Settings`** → en el menú izquierdo **`Account Settings`** → **`Market Data`**.
   * En **`Market Data Subscriptions`**, pulsar el icono de lápiz / **`Configure`**.
   * Navegar a **`North America` → `US Options`** y seleccionar el paquete **`OPRA Top of Book (L1)` (`US Option Exchanges`)** (*costo Non-Professional: **`\$1.50 USD/mes`**, exonerado si la cuenta genera al menos `\$20/mes` en comisiones*).
   * Aceptar la declaración de suscriptor **Non-Professional** y confirmar.
2. **Compartir Datos en Tiempo Real con la Cuenta Paper Trading:**
   * En el mismo **Client Portal** (Live) → **`Settings`** → **`Account Settings`** → **`Account Configuration`** → **`Paper Trading Account`**.
   * En la pregunta ***"Share real-time market data with your paper trading account?"***, seleccionar **`Yes`**, vincular el usuario Live y pulsar **`Save`**.
3. **Reglas y Tiempos de Activación:**
   * La propagación hacia Paper Trading tarda hasta **24 horas hábiles**.
   * **Restricción crítica:** No mantener abiertas al mismo tiempo la sesión **Live** y la sesión **Paper** (APOLO TWS) en dispositivos distintos; las bolsas degradan automáticamente el feed Paper a datos retrasados (`DELAYED`) si detectan sesión simultánea en Live.
   * Una vez transcurrido el plazo, reiniciar TWS Paper en APOLO (`192.168.1.105:7497`) y verificar que desaparecen los `[IB Error 10090]` en `system_logs` (el conector [ib_provider.py](file:///c:/Fuentes/eTrade/backend/app/data/ib_provider.py#L137) ya solicita `reqMarketDataType(4)`). Como paso posterior en `opt_settings`, cambiar `allow_delayed_data = False`.
