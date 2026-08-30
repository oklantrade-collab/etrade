"""
Tests unitarios para BrokerSynchronizer
"""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.execution.broker_sync import BrokerSynchronizer

def test_broker_sync_init():
    sync = BrokerSynchronizer()
    assert sync._is_running_crypto is False
    assert sync._is_running_forex is False

if __name__ == '__main__':
    print("Ejecutando tests de BrokerSynchronizer...")
    test_broker_sync_init()
    print("[PASS] test_broker_sync_init")
    print("\n>>> TODOS LOS TESTS DE BROKER SYNC PASARON EXITOSAMENTE! <<<")
