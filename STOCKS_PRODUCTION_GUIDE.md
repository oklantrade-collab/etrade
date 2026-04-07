# eTrader v4.5 — Stocks Module (AI Decision Layer)
## Production Go-Live & Ops Guide
**Autor:** Antigravity Team / Deepmind Architecture
**Fecha de Entrega:** Abril 2026
**Módulo:** Sprint 5 al Sprint 9 (Completado)

---

### 1. Resumen de la Arquitectura Construida
Se ha expandido el sistema de Trading Algorítmico existente hacia el mercado de acciones tradicional americano a través de la integración de **Inteligencia Artificial Multinivel** y **DashScope (QWEN) / Google Gemini / Claude 3.5**.
Se ha creado un pipeline ininterrumpido de 8 capas (0 al 7):
*   **Capa 0 (Universo)**: Un `UniverseBuilder` extrae vía AI los tickers del día según catalizadores y momentum.
*   **Capas 1 y 2 (Técnico)**: Integradas con el Scheduler de los previos motores (Crypto/Forex). Descarga de velas 5m usando `yfinance` y cálculo de RVOL / Slippage.
*   **Capas 3 y 4 (Fundamental y Contexto)**: Un analizador cualitativo que sopesa y guarda datos fundamentales en `fundamental_cache`.
*   **Capa 5 (Master Decision)**: Un `DecisionEngine` resiliente. Contiene **Triple Fallback** (Claude → Gemini / Qwen → Lógica Matemática Pura).
*   **Capa 6 (Execution)**: `OrderExecutor` que despacha Bracket Orders (Entrada, Stop, Target). Soporta `Paper Mode` activo.
*   **Capa 7 (Monitoring)**: Un bot que vigila posiciones activas aplicando **Trailing Stops** a niveles del +1.5%.

### 2. Puesta en Producción (Live Trading)
ACTUALMENTE EL SISTEMA SE ENCUENTRA EN **"PAPER MODE"** (Simulación Segura).
Para activar dinero real con Interactive Brokers (IB TWS API), se deben dar los siguientes pasos desde el Panel eTrader:

1.  **Lanzar TWS (Trader Workstation)**: Entrar a Opciones > API > Settings en TWS. Marcar la opción `Enable ActiveX and Socket Clients`.
2.  **Puertos IB**:
    *   **7497** = Cuenta Simulada de IB (Paper).
    *   **7496** = Cuenta en Vivo (Real Money).
3.  **Librería Oficial**: Ejecutar en la consola principal `pip install ibapi` descargando previamente el wheel/paquete oficial desde el sitio de IB (no está en PyPI por temas de licencias).
4.  **Actualizar la Base de Datos**: Desactivar el Paper Mode desde el archivo `stocks_config` de Supabase cambiando `'paper_mode_active'` a `'false'`.

### 3. Recuperación Ante Desastres (Resiliencia)
Hemos programado inyecciones de resiliencia masivas.
*   **AI Offline?**: Si te quedas sin cuota en Gemini, Qwen o Anthropic (o fallos SSL/API), la **Capa 5** calculará entradas puramente basadas en volatilidad matemática (ATR) y tendencia.
*   **Desconexión de API de IB?**: Si el cable oficial al broker se rompe, el `OrderExecutor` volverá inmediatamente el trade a `Paper Mode` en Supabase para no perder el registro de la instrucción en base de datos.
*   **Kill-Switch de Emergencia**: Existe un botón (Post de `close-all` en la clase api) para purgar operaciones en pánico y cerrar todo a valor de mercado.

### 4. Telemetría y Controles Frontend
*   El **Dashboard de Bolsa** opera en `http://localhost:3000/stocks/dashboard`.
*   Utiliza "Long Polling" en el frontend para buscar iteraciones. Si cierras la ventana el sistema en el host y/o nube seguirá ejecutando las órdenes, y recibirás alertas vía **Telegram**.
*   **Notificaciones**: Ajustadas en `OrderExecutor` y `PositionMonitor`. Las credenciales deben estar inyectadas en tu `.env` como `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`.

---
*End of Document. All Systems Go.*
