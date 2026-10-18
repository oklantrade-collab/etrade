"""Adaptador IBKR de SOLO LECTURA para opciones (doc §14.2).

Por diseno NO hereda de EClient/IBConnection (que expone placeOrder).
Usa composicion: el cliente real queda privado y solo se puede invocar
un conjunto cerrado de metodos de lectura (whitelist).
"""
from __future__ import annotations

from typing import Any

ALLOWED_METHODS = frozenset({
    "reqContractDetails",
    "reqSecDefOptParams",
    "reqMktData",
    "cancelMktData",
    "reqMarketDataType",
    "reqCurrentTime",
})

# Nombres de metodos de ordenes/cuentas que jamas deben aparecer en este modulo.
FORBIDDEN_TOKENS = (
    "placeOrder", "cancelOrder", "reqGlobalCancel", "exerciseOptions",
    "place_order", "place_bracket_order", "create_bracket_order",
    "IBProvider", "IBConnection", "unified_trading_worker",
)

# Estados de datos (doc §14.3)
DATA_STATES = ("LIVE", "DELAYED", "FROZEN", "UNKNOWN", "STALE", "ERROR")
_MDT_TO_STATE = {1: "LIVE", 2: "FROZEN", 3: "DELAYED", 4: "DELAYED"}


def market_data_type_to_state(mdt: int | None) -> str:
    return _MDT_TO_STATE.get(mdt, "UNKNOWN") if mdt is not None else "UNKNOWN"


class ForbiddenBrokerCall(RuntimeError):
    pass


class OptionsReadOnlyAdapter:
    """Envoltorio que solo deja pasar llamadas de lectura al cliente IB."""

    def __init__(self, client: Any):
        self.__client = client  # name-mangled: no accesible como atributo publico

    def call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        if method not in ALLOWED_METHODS:
            raise ForbiddenBrokerCall(f"Metodo no permitido en Options (solo lectura): {method}")
        fn = getattr(self.__client, method, None)
        if fn is None:
            raise ForbiddenBrokerCall(f"El cliente no implementa {method}")
        return fn(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        # Cualquier acceso directo (p.ej. adapter.placeOrder) falla.
        raise ForbiddenBrokerCall(f"Acceso directo no permitido: {name}. Use call() con metodos de la whitelist.")
