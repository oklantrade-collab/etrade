"""
Tests unitarios para ADUANA Exit Gatekeeper
"""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.rebote_aduana.aduana_exit_gate import AduanaExitGatekeeper, ExitOrderRequest

def test_arbitration_and_coexistence():
    gate = AduanaExitGatekeeper()
    pos_id = "pos_test_1"
    
    # 1. Enviar orden ANCLA_SL
    req_sl = ExitOrderRequest(
        position_id=pos_id,
        symbol="BTCUSDT",
        side="sell",
        order_type="STOP",
        price=48000.0,
        volume=1.0,
        classification="ACTIVA",
        module_origin="ANCLA_SL"
    )
    res1 = gate.arbitrate_and_register_order(req_sl)
    assert res1['approved'] is True
    assert res1['action'] == "PLACE"
    
    # 2. Enviar orden ANCLA_TP1 (debe coexistir con SL)
    req_tp = ExitOrderRequest(
        position_id=pos_id,
        symbol="BTCUSDT",
        side="sell",
        order_type="LIMIT",
        price=52000.0,
        volume=0.5,
        classification="ACTIVA",
        module_origin="ANCLA_TP1"
    )
    res2 = gate.arbitrate_and_register_order(req_tp)
    assert res2['approved'] is True
    assert res2['action'] == "COEXIST"
    
    pending = gate.get_pending_orders(pos_id)
    assert len(pending) == 2

def test_cross_cancellation_on_tp1_fill():
    gate = AduanaExitGatekeeper()
    pos_id = "pos_test_2"
    
    # Crear SL y TP1
    req_sl = ExitOrderRequest(
        position_id=pos_id,
        symbol="ETHUSDT",
        side="sell",
        order_type="STOP",
        price=2800.0,
        volume=2.0,
        classification="ACTIVA",
        module_origin="ANCLA_SL"
    )
    res_sl = gate.arbitrate_and_register_order(req_sl)
    
    req_tp1 = ExitOrderRequest(
        position_id=pos_id,
        symbol="ETHUSDT",
        side="sell",
        order_type="LIMIT",
        price=3200.0,
        volume=1.0,
        classification="ACTIVA",
        module_origin="ANCLA_TP1"
    )
    res_tp1 = gate.arbitrate_and_register_order(req_tp1)
    tp1_order_id = res_tp1['order_record'].order_id
    
    # Simular fill de TP1
    fill_res = gate.handle_order_fill(
        position_id=pos_id,
        filled_order_id=tp1_order_id,
        module_origin="ANCLA_TP1",
        filled_volume=1.0,
        remaining_volume=1.0,
        breakeven_sl_price=3004.5
    )
    
    assert len(fill_res['modified_orders']) == 1
    assert fill_res['modified_orders'][0]['new_volume'] == 1.0
    assert fill_res['modified_orders'][0]['new_sl_price'] == 3004.5

def test_cross_cancellation_on_sl_fill():
    gate = AduanaExitGatekeeper()
    pos_id = "pos_test_3"
    
    req_sl = ExitOrderRequest(
        position_id=pos_id,
        symbol="SOLUSDT",
        side="sell",
        order_type="STOP",
        price=100.0,
        volume=10.0,
        classification="ACTIVA",
        module_origin="ANCLA_SL"
    )
    res_sl = gate.arbitrate_and_register_order(req_sl)
    sl_order_id = res_sl['order_record'].order_id
    
    req_tp = ExitOrderRequest(
        position_id=pos_id,
        symbol="SOLUSDT",
        side="sell",
        order_type="LIMIT",
        price=120.0,
        volume=5.0,
        classification="ACTIVA",
        module_origin="ANCLA_TP1"
    )
    res_tp = gate.arbitrate_and_register_order(req_tp)
    
    # Simular fill de SL
    fill_res = gate.handle_order_fill(
        position_id=pos_id,
        filled_order_id=sl_order_id,
        module_origin="ANCLA_SL",
        filled_volume=10.0,
        remaining_volume=0.0
    )
    
    assert len(fill_res['cancelled_orders']) == 1
    assert fill_res['cancelled_orders'][0] == res_tp['order_record'].order_id
    
    # Verificar que no quedan órdenes pendientes
    pending = gate.get_pending_orders(pos_id)
    assert len(pending) == 0

if __name__ == '__main__':
    print("Ejecutando tests de ADUANA Exit Gatekeeper...")
    test_arbitration_and_coexistence()
    print("[PASS] test_arbitration_and_coexistence")
    test_cross_cancellation_on_tp1_fill()
    print("[PASS] test_cross_cancellation_on_tp1_fill")
    test_cross_cancellation_on_sl_fill()
    print("[PASS] test_cross_cancellation_on_sl_fill")
    print("\n>>> TODOS LOS TESTS DE ADUANA EXIT GATE PASARON EXITOSAMENTE! <<<")
