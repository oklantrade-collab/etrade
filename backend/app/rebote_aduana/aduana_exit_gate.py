"""
ADUANA Exit Gatekeeper — Centralización de Órdenes de Salida (SL / TP / Trailing / Cascadas)
eTrade v5.0 / v6.0 (Sección 4 de ANCLA_Spec.md)

Responsabilidades:
1. Único punto de registro, arbitraje y control de órdenes de salida.
2. Clasificación: PASIVA (SLV, Trailing Stop) vs ACTIVA (ANCLA SL/TP, CASCADA).
3. Tabla de Prioridades:
   - 1: SLV/SLVM (Stop ATR de emergencia)
   - 2: ANCLA SL (Stop estructural dinámico)
   - 3: ANCLA TP1 / TP2 (Take profit en 2 etapas)
   - 4: CASCADA Giveback (Válvula de seguridad)
   - 5: Trailing Stop (Resguardo general)
4. Cancelación cruzada automática:
   - Fill de SL -> Cancela TPs pendientes.
   - Fill de TP1 -> Ajusta tamaño de SL al remanente y coloca Breakeven.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from app.core.logger import log_info, log_warning, log_error

MODULE = "ADUANA_EXIT_GATE"


@dataclass
class ExitOrderRequest:
    position_id: str
    symbol: str
    side: str                   # 'sell' para cerrar Long, 'buy' para cerrar Short
    order_type: str             # 'STOP', 'STOP_LIMIT', 'LIMIT', 'MARKET'
    price: float
    volume: float
    classification: str         # 'PASIVA' o 'ACTIVA'
    module_origin: str          # 'SLV', 'ANCLA_SL', 'ANCLA_TP1', 'ANCLA_TP2', 'CASCADA', 'TRAILING_STOP'
    reduce_only: bool = True
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ExitOrderRecord:
    order_id: str
    position_id: str
    symbol: str
    side: str
    order_type: str
    price: float
    volume: float
    classification: str
    module_origin: str
    status: str                 # 'PENDING', 'FILLED', 'CANCELLED', 'REPLACED'
    reduce_only: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AduanaExitGatekeeper:
    """
    Gatekeeper centralizado de órdenes de salida para eTrade.
    """

    PRIORITY_MAP = {
        "SLV": 1,
        "SLVM": 1,
        "ANCLA_SL": 2,
        "REBOTE_CLIMAX": 3,
        "CLIMAX_REBOTE_EXIT": 3,
        "ANCLA_TP1": 3,
        "ANCLA_TP2": 3,
        "CASCADA": 4,
        "TRAILING_STOP": 5,
    }

    def __init__(self):
        # Registro en memoria de órdenes activas por position_id
        # {position_id: [ExitOrderRecord]}
        self._orders_by_position: Dict[str, List[ExitOrderRecord]] = {}

    def arbitrate_and_register_order(
        self,
        request: ExitOrderRequest,
    ) -> Dict[str, Any]:
        """
        Evalúa una solicitud de orden de salida frente a las órdenes existentes de la posición.
        
        Returns:
            Dict con:
            - approved (bool): si la orden debe enviarse/mantenerse
            - action (str): 'PLACE', 'REPLACE', 'REJECT', 'COEXIST'
            - order_record (ExitOrderRecord): registro creado o actualizado
            - reason (str): motivo de la decisión
        """
        pos_id = request.position_id
        if pos_id not in self._orders_by_position:
            self._orders_by_position[pos_id] = []

        existing_orders = [o for o in self._orders_by_position[pos_id] if o.status == "PENDING"]
        req_priority = self.PRIORITY_MAP.get(request.module_origin, 99)

        # 1. Caso sin órdenes previas: Se aprueba directamente
        if not existing_orders:
            record = ExitOrderRecord(
                order_id=f"exit_{request.module_origin}_{pos_id}_{int(datetime.now(timezone.utc).timestamp())}",
                position_id=pos_id,
                symbol=request.symbol,
                side=request.side,
                order_type=request.order_type,
                price=request.price,
                volume=request.volume,
                classification=request.classification,
                module_origin=request.module_origin,
                status="PENDING",
            )
            self._orders_by_position[pos_id].append(record)
            log_info(f"ADUANA Salida: Orden {record.module_origin} ({record.order_type} @ {record.price:.4f}) APROBADA para {request.symbol}", MODULE)
            return {
                "approved": True,
                "action": "PLACE",
                "order_record": record,
                "reason": f"Primera orden de salida para la posición {pos_id}.",
            }

        # 2. Arbitraje frente a órdenes existentes
        # Las órdenes de TP no compiten contra SL (coexisten)
        is_request_tp = "TP" in request.module_origin
        for existing in existing_orders:
            is_existing_tp = "TP" in existing.module_origin

            # Si una es TP y la otra es SL -> Coexisten
            if is_request_tp != is_existing_tp:
                continue

            # Si ambas son del mismo módulo (ej. ANCLA_SL actualizándose con nuevo nivel)
            if existing.module_origin == request.module_origin:
                # Reemplazo de nivel
                existing.status = "REPLACED"
                new_record = ExitOrderRecord(
                    order_id=f"exit_{request.module_origin}_{pos_id}_{int(datetime.now(timezone.utc).timestamp())}",
                    position_id=pos_id,
                    symbol=request.symbol,
                    side=request.side,
                    order_type=request.order_type,
                    price=request.price,
                    volume=request.volume,
                    classification=request.classification,
                    module_origin=request.module_origin,
                    status="PENDING",
                )
                self._orders_by_position[pos_id].append(new_record)
                return {
                    "approved": True,
                    "action": "REPLACE",
                    "order_record": new_record,
                    "old_order_id": existing.order_id,
                    "reason": f"Reemplazo dinámico de {request.module_origin} a nuevo nivel {request.price:.4f}.",
                }

            # Si ambas son de protección (SL): gana la de mayor prioridad o el nivel más protector
            existing_prio = self.PRIORITY_MAP.get(existing.module_origin, 99)
            if req_priority < existing_prio:
                # Nueva orden tiene mayor prioridad -> Reemplaza
                existing.status = "CANCELLED"
                new_record = ExitOrderRecord(
                    order_id=f"exit_{request.module_origin}_{pos_id}_{int(datetime.now(timezone.utc).timestamp())}",
                    position_id=pos_id,
                    symbol=request.symbol,
                    side=request.side,
                    order_type=request.order_type,
                    price=request.price,
                    volume=request.volume,
                    classification=request.classification,
                    module_origin=request.module_origin,
                    status="PENDING",
                )
                self._orders_by_position[pos_id].append(new_record)
                return {
                    "approved": True,
                    "action": "REPLACE",
                    "order_record": new_record,
                    "old_order_id": existing.order_id,
                    "reason": f"Orden {request.module_origin} (prio {req_priority}) reemplaza a {existing.module_origin} (prio {existing_prio}).",
                }
            elif req_priority == existing_prio:
                # Misma prioridad: coexisten protegiendo en el nivel más cercano
                pass
            else:
                # Nueva orden tiene menor prioridad
                return {
                    "approved": False,
                    "action": "REJECT",
                    "order_record": None,
                    "reason": f"Rechazada: {existing.module_origin} ya tiene mayor prioridad ({existing_prio} < {req_priority}).",
                }

        # Coexistencia permitida (ej. SL y TP1 activos simultáneamente)
        new_record = ExitOrderRecord(
            order_id=f"exit_{request.module_origin}_{pos_id}_{int(datetime.now(timezone.utc).timestamp())}",
            position_id=pos_id,
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            price=request.price,
            volume=request.volume,
            classification=request.classification,
            module_origin=request.module_origin,
            status="PENDING",
        )
        self._orders_by_position[pos_id].append(new_record)
        return {
            "approved": True,
            "action": "COEXIST",
            "order_record": new_record,
            "reason": f"Orden {request.module_origin} coexiste con órdenes activas.",
        }

    def handle_order_fill(
        self,
        position_id: str,
        filled_order_id: str,
        module_origin: str,
        filled_volume: float,
        remaining_volume: float,
        breakeven_sl_price: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Ejecuta la cancelación cruzada y el ajuste de tamaño tras el fill de una orden.
        
        - Si fill es de SL (o CASCADA total) -> Cancela todos los TPs pendientes.
        - Si fill es de TP1 -> Marca TP1 como ejecutado, ajusta el volumen del SL al 50% remanente
          y eleva el SL a Breakeven.
        """
        orders = self._orders_by_position.get(position_id, [])
        cancelled_orders = []
        modified_orders = []

        # Marcar la orden como FILLED
        for o in orders:
            if o.order_id == filled_order_id:
                o.status = "FILLED"

        is_tp1_fill = "TP1" in module_origin
        is_sl_fill = ("SL" in module_origin) or ("CASCADA" in module_origin)

        # 1. Caso Fill de SL: Cancelar TPs pendientes
        if is_sl_fill:
            for o in orders:
                if o.status == "PENDING" and "TP" in o.module_origin:
                    o.status = "CANCELLED"
                    cancelled_orders.append(o.order_id)
            log_info(f"ADUANA Cancelación Cruzada: SL ejecutado en {position_id}. Cancelados TPs: {cancelled_orders}", MODULE)

        # 2. Caso Fill de TP1: Reducir volumen de SL al 50% remanente y mover a Breakeven
        if is_tp1_fill:
            for o in orders:
                if o.status == "PENDING" and ("SL" in o.module_origin or o.order_type == "STOP"):
                    o.volume = remaining_volume
                    if breakeven_sl_price > 0:
                        o.price = breakeven_sl_price
                    modified_orders.append({
                        "order_id": o.order_id,
                        "new_volume": remaining_volume,
                        "new_sl_price": o.price,
                    })
            log_info(f"ADUANA Fill TP1 en {position_id}: SL remanente ajustado a volumen {remaining_volume} y Breakeven {breakeven_sl_price:.4f}", MODULE)

        return {
            "position_id": position_id,
            "filled_order_id": filled_order_id,
            "cancelled_orders": cancelled_orders,
            "modified_orders": modified_orders,
        }

    def cancel_all_orders_for_position(self, position_id: str) -> List[str]:
        """Cancela todas las órdenes registradas de una posición cerrada."""
        orders = self._orders_by_position.get(position_id, [])
        cancelled = []
        for o in orders:
            if o.status == "PENDING":
                o.status = "CANCELLED"
                cancelled.append(o.order_id)
        return cancelled

    def get_pending_orders(self, position_id: str) -> List[ExitOrderRecord]:
        """Retorna las órdenes pendientes para una posición."""
        return [o for o in self._orders_by_position.get(position_id, []) if o.status == "PENDING"]


# Instancia singleton para uso en el backend
GLOBAL_ADUANA_EXIT_GATE = AduanaExitGatekeeper()
