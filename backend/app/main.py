"""
eTrader v2 — FastAPI Main Application
REST API Gateway for the trading platform.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI(
    title="eTrader API",
    description="Plataforma de Trading Algorítmico Multimercado — Volume Spike + MTF Confirmación",
    version="2.0.0",
)

# CORS config
origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "https://etrade-flame.vercel.app",
    "https://etrade-backend.onrender.com", # Self
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Temporalmente permitir todo para diagnosticar si es un problema de la lista o de los headers
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "ok", "version": "2.0.0", "service": "eTrader API"}


# ── API Routers ──
from app.api.dashboard import router as dashboard_router
from app.api.market import router as market_router
from app.api.signals import router as signals_router
from app.api.positions import router as positions_router
from app.api.risk import router as risk_router
from app.api.logs import router as logs_router
from app.api.backtests import router as backtests_router

from app.api.performance import router as performance_router
from app.api.portfolio import router as portfolio_router
from app.api.strategies import router as strategies_router
from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.forex import router as forex_router

app.include_router(auth_router, prefix="/api/v1/auth", tags=["Autenticación"])
app.include_router(admin_router, prefix="/api/v1/admin", tags=["Administración"])
app.include_router(dashboard_router, prefix="/api/v1/dashboard", tags=["Dashboard"])
app.include_router(portfolio_router, prefix="/api/v1/portfolio", tags=["Portfolio"])
app.include_router(strategies_router, prefix="/api/v1/strategies", tags=["Strategies"])
app.include_router(market_router, prefix="/api/v1/market", tags=["Market"])
app.include_router(signals_router, prefix="/api/v1/signals", tags=["Signals"])
app.include_router(positions_router, prefix="/api/v1/positions", tags=["Positions"])
app.include_router(risk_router, prefix="/api/v1/risk", tags=["Risk"])
app.include_router(performance_router, prefix="/api/v1/performance", tags=["Performance"])
app.include_router(logs_router, prefix="/api/v1", tags=["Logs"])
app.include_router(backtests_router, prefix="/api/v1/backtests", tags=["Backtesting"])
app.include_router(forex_router, prefix="/api/v1/forex", tags=["Forex"])
