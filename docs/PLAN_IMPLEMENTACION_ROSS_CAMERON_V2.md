# Plan de Implementación: Blindaje Operativo Ross Cameron (Stocks & Opciones)
## Basado en Auditoría Técnica de Motores y Análisis Forense (09/11/2026 – 13/11/2026)

> **Fecha:** 15 de Noviembre de 2026  
> **Estado:** Listo para Ejecución  
> **Objetivo:** Eliminar las 5 causas raíz de pérdidas detectadas en la semana del 09/11 al 13/11/2026 e integrar las reglas estrictas del Rule Pack `RP_WARRIOR_MOMENTUM_V1` en los motores en vivo de Stocks y Opciones.

---

## Parte 1: Hallazgos Forenses de la Semana (09/11/2026 – 13/11/2026)

### 1.1 Resumen Estadístico de la Base de Datos (`opt_paper_trades` y `stocks_positions`)

| Módulo | Operaciones | Ganadas (W) | Perdidas (L) | Win Rate | PnL Neto (USD) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Opciones — Intradía Puro** | 132 | 39 | 71 | 29.5% | **+$711.69** |
| **Opciones — Retención Overnight** | 47 | 11 | 36 | 23.4% | **-$44,738.72** |
| **Stocks Spot (`stocks_positions`)** | 25 | 6 | 19 | 24.0% | **-$202.13** |

### 1.2 Las 5 Causas Raíz de las Pérdidas

1. **Retención Overnight Accidental y Re-importación en el Cierre (`-$44,738.72` en 47 trades de Opciones):**
   * Las operaciones de opciones cerradas el mismo día fueron **positivas (`+$711.69`)**. Toda la pérdida masiva provino de posiciones retenidas de un día para otro.
   * **Mecanismo del fallo:** A las `15:50 - 15:55 ET` (`20:50 - 20:55 UTC`) y `22:05 ET` (`03:05 UTC`), el sincronizador de broker (`broker_sync.py`) re-importó contratos cuya orden de venta en TWS había sido cancelada (`286 órdenes de venta canceladas`), creándolos como nuevas posiciones justo antes del cierre. Al día siguiente a las `09:30 - 09:37 ET`, abrieron con pérdidas de `-78%` a `-88%` (`META -$9,075.89`, `META -$6,866.57`, `AMZN -$5,485.59`, `META -$5,289.15`, `GOOGL -$4,486.64`, `AMZN -$4,459.70`).
2. **Apilamiento Masivo de Contratos (*Stacking* de `OPT_GAP_TRANCHE_2_CALL` — `-$31,160.11`):**
   * Se registraron **203 compras ejecutadas** bajo la regla `OPT_GAP_TRANCHE_2_CALL`, acumulando entre **21 y 35 contratos** en una sola posición (`AMZN 35 contratos`, `GOOGL 34 contratos`, `META 20 contratos`).
   * Las posiciones de 1 a 2 contratos tuvieron un impacto menor (`-$1,925.24` en 123 trades), mientras que las de $\ge 6$ contratos causaron `-$31,160.11`.
3. **Compras en el "Cementerio del Mediodía" y Sangría por `OPT_0DTE_TIME_DECAY_GUARD` (`-$3,659.43` con 0% Win Rate):**
   * **24 de 24 operaciones** cerradas por `OPT_0DTE_TIME_DECAY_GUARD` terminaron en pérdida (`0 Ganadas / 24 Perdidas`).
   * Fueron abiertas entre las **11:15 ET y las 14:45 ET** (horario sin volumen direccional), donde el precio se estancó y el guardián de decaimiento temporal las cerró automáticamente a los 25-30 minutos en pérdida.
4. **Compras en la Última Hora (`15:00 - 15:59 ET` — Win Rate `16.7%`, `-$35,961.96`):**
   * Se abrieron 36 posiciones de opciones en la última hora de mercado (6 ganadas, 27 perdidas), quedando atrapadas al cierre.
5. **En Stocks Spot: 68% de Compras Fuera de la Ventana de Ross Cameron y Persecución de Spikes (`-$202.13`, Win Rate `24%`):**
   * De las 25 compras de acciones (`ALPHA_RUNNER`, `HOT`, `inversiones_pro`), **17 se ejecutaron después de las 11:00 AM ET** (7 de ellas a las 14:00 ET con 1 sola ganada y 6 perdidas).
   * Acciones como `MF` (`-$37.40` en 19 segundos) y `SMX` (`-$55.40` en 8 minutos) se compraron en plena extensión sin esperar el micro-pullback a EMA9/VWAP, saliendo por `EMERGENCY_EXIT` o `SLIPPAGE_DEFENSIVE_EXIT`.

---

## Parte 2: Plan de Implementación Técnica (8 Fases)

### Fase 1: Conexión de Circuit Breakers Diarios en `MicroPullbackEngine` (Stocks)
* **Archivo:** `backend/app/stocks/micro_pullback_engine.py`
* **Acción:**
  * Integrar `check_safety_guardrails` de `warrior_momentum_engine.py` antes de cada disparo en `_trigger_entry()`.
  * Registrar contador `consecutive_losses` en memoria y sincronizarlo con `trades_journal`.
  * Bloquear nuevas compras por el resto de la sesión si:
    1. `consecutive_losses >= 2` (`CIRCUIT_BREAKER_2_CONSECUTIVE_LOSSES`).
    2. `daily_cushion_usd <= -150.0` (`MAX_DAILY_LOSS_REACHED`).
    3. Hora actual $\ge$ `11:00 ET` (`OUTSIDE_MOMENTUM_WINDOW`).

### Fase 2: Calibración de TP1 ("Pay the Trader") y Órdenes `LMT` Protegidas en Ventas de Stocks
* **Archivo:** `backend/app/stocks/micro_pullback_engine.py`
* **Acción:**
  * En `_manage_active_trade()`, exigir que el Tramo 1 (venta del 50% + Stop a Breakeven) se active cuando la ganancia alcance **`max($0.15 por acción, +2.5%)`** o toque el `HOD`, evitando cobrar micro-ganancias de $0.05 en acciones de bajo precio.
  * En `_send_partial_sell_to_tws()` y `_close_scalp()`, reemplazar las órdenes `MKT` puras por órdenes **`LMT Marketable`** (`round(curr_p - 0.03, 2)` en salidas de emergencia o `curr_p` en tomas de ganancia) para erradicar el deslizamiento severo en *small caps*.

### Fase 3: Bloqueo Horario Estricto (11:00 AM ET) para Compras de Momentum en el Scheduler General de Stocks
* **Archivo:** `backend/app/workers/stocks_scheduler.py` y `backend/app/stocks/decision_engine.py`
* **Acción:**
  * Aplicar la regla de oro de Ross Cameron a los grupos `HOT`, `ALPHA_RUNNER` y `OPEN_GAP_RUNNER`: bloquear la apertura de nuevas compras después de las **11:00 AM ET** (permitiendo únicamente una ventana secundaria opcional de *Power Hour* `15:00 – 15:30 ET` solo si `SPY/QQQ` están en verde y $\text{RVOL} \ge 3.0\text{x}$).
  * Exigir filtro anti-persecución (*Anti-Chase Gate*): prohibir compra si el precio actual está a más de $+1.5\times \text{ATR}_{5\text{m}}$ por encima de la `EMA9_5m` (evitando casos como `MF` y `SMX`).

### Fase 4: Ventana de Oro y Exigencia de Pullback Real en `warrior_momentum_options.py`
* **Archivo:** `backend/app/options/warrior_momentum_options.py`
* **Acción:**
  * Restringir `run_warrior_momentum_options_scan()` exclusivamente a la **Ventana de Oro (`09:35 – 11:30 ET`)**. Prohibido abrir opciones en el mediodía (`11:30 – 14:45 ET`) o después de las `15:00 ET`.
  * En `evaluate_warrior_momentum_setup()` (líneas 133 y 170), cambiar `(had_pullback_call or is_bb_expanding)` por **`had_pullback_call and is_bb_expanding`**, garantizando que siempre exista un retroceso previo de 1 a 3 velas antes del gatillo *First Candle to Make a New High/Low*.

### Fase 5: Tope Duro de Contratos (Anti-Stacking) y Bloqueo de Tranche 2 en Pérdida
* **Archivos:** `backend/app/options/aduana_gap_runner_options.py`, `backend/app/options/autonomous_options_dispatcher.py` y `backend/app/options/warrior_momentum_options.py`
* **Acción:**
  * Establecer un límite inquebrantable de **`MAX_CONTRACTS_PER_SYMBOL = 3`** (y máximo 1 posición abierta por subyacente).
  * En `OPT_GAP_TRANCHE_2_CALL`, exigir que la posición inicial esté en ganancia neta ($\ge +10\%$), que no tenga más de 1 recompra previa (`rebuys_count == 0`) y que se encuentre antes de las `11:00 ET`.

### Fase 6: Erradicación de Retención Overnight y Re-Importación Fantasma en `broker_sync.py`
* **Archivos:** `backend/app/options/broker_sync.py` y `backend/app/options/exit_engine.py`
* **Acción:**
  * Bloquear la creación/importación de nuevas posiciones en `opt_paper_trades` fuera del horario `09:30 – 15:30 ET`.
  * Si un contrato fue cerrado en base de datos pero sigue vivo en TWS por orden cancelada después de las `15:45 ET`, reenviar orden de liquidación inmediata (`LMT` agresiva al Bid) en lugar de re-importarlo como nuevo trade nocturno.
  * Adelantar el **Hard-Exit Intradía de Opciones Semanales/0DTE** a las **`15:45 ET`** con reintento automático cada 15 segundos hasta confirmar `qty = 0` en TWS.

### Fase 7: Ajuste del Guardián `OPT_0DTE_TIME_DECAY_GUARD`
* **Archivo:** `backend/app/options/exit_engine.py`
* **Acción:**
  * Con el bloqueo de compras en el mediodía (Fase 4), las entradas ocurrirán solo en alta volatilidad matutina.
  * Además, evitar que `OPT_0DTE_TIME_DECAY_GUARD` liquide una posición en pérdida menor (`-1%` a `-4%`) si el subyacente se mantiene a favor de la tendencia (`Precio > EMA9_15m` y `Precio > VWAP` en CALLs).

### Fase 8: Pruebas Unitarias e Integración de Regresión
* **Archivo:** `backend/tests/test_warrior_blindaje_v2.py`
* **Acción:**
  * Validar con tests automatizados:
    1. Bloqueo tras 2 pérdidas consecutivas y límite de $-\$150\text{ USD}$ en `MicroPullbackEngine`.
    2. Bloqueo de compras después de las 11:00 ET en Stocks y 11:30 ET en Opciones.
    3. Rechazo de `warrior_momentum_options` cuando no existe vela previa de pullback.
    4. Tope máximo de contratos por subyacente (`MAX_CONTRACTS_PER_SYMBOL = 3`).
    5. Bloqueo de importación nocturna en `broker_sync.py`.
