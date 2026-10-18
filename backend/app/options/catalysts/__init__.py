"""Modulo de catalizadores y arbitraje direccional de Opciones (CALL/PUT) y Stocks."""
from app.options.catalysts.engine import evaluate_all_catalysts
from app.options.catalysts.arbitration import resolve_arbitration, ArbitrationResolution
from app.options.catalysts.service import run_catalyst_scan

__all__ = [
    "evaluate_all_catalysts",
    "resolve_arbitration",
    "ArbitrationResolution",
    "run_catalyst_scan",
]
