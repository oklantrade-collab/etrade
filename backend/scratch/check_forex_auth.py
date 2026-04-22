import os
import sys
from dotenv import load_dotenv

def test_config():
    # Intentar cargar .env desde la raíz de backend
    dotenv_path = os.path.join(os.getcwd(), '.env')
    print(f"Cargando config desde: {dotenv_path}")
    load_dotenv(dotenv_path)

    acc_id = os.getenv('CTRADER_ACCOUNT_ID')
    token = os.getenv('CTRADER_ACCESS_TOKEN')
    env = os.getenv('CTRADER_ENV')
    
    print("\n--- REVISIÓN DE CONFIGURACIÓN ---")
    print(f"CTRADER_ACCOUNT_ID: {acc_id} (Tipo: {type(acc_id)})")
    print(f"CTRADER_ENV: {env}")
    
    if token:
        print(f"Token: '{token}'")
        print(f"Length: {len(token)}")
        expected = "gdPN2OHWcPPotBj0A5geeiXqNW_WnWukKIjl96DaYj8"
        if token == expected:
            print("PERFECT MATCH: The token in .env is identical to the one from sandbox.")
        else:
            print("MISMATCH: The token in .env is STILL DIFFERENT from the expected one.")
            for i, (a, b) in enumerate(zip(token, expected)):
                if a != b:
                    print(f"Diff at index {i}: .env has '{a}', expected '{b}'")
                    break
    else:
        print("ERROR: No se encontró el token en el .env")

    # Verificar si el ID es el de Sandbox correcto
    if acc_id == "46864722":
        print("✅ ID de cuenta Sandbox correcto.")
    else:
        print(f"⚠️ El ID de cuenta es {acc_id}. Para Sandbox debería ser 46864722.")

if __name__ == "__main__":
    test_config()
