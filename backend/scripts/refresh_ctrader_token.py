"""
Script para refrescar el Access Token de cTrader Open API usando el Refresh Token.
Actualiza automáticamente el archivo .env con el nuevo Access Token y Refresh Token.
"""
import os
import re
import sys
import requests
from pathlib import Path

def find_env_path():
    candidates = [
        Path('/home/etrade/etrade/backend/.env'),
        Path(__file__).resolve().parent.parent / '.env',
        Path('.env'),
    ]
    for c in candidates:
        if c.exists():
            return c
    return None

def load_env_vars(env_path):
    env_vars = {}
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                env_vars[key.strip()] = val.strip().strip("'\"")
    return env_vars

def update_env_file(env_path, updates):
    with open(env_path, 'r', encoding='utf-8') as f:
        content = f.read()

    for key, new_val in updates.items():
        pattern = rf'^{key}=.*$'
        replacement = f'{key}={new_val}'
        if re.search(pattern, content, flags=re.MULTILINE):
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        else:
            content += f'\n{key}={new_val}\n'

    with open(env_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"[OK] Archivo {env_path} actualizado exitosamente.")

def main():
    env_path = find_env_path()
    if not env_path:
        print("[ERROR] No se encontró el archivo .env")
        sys.exit(1)

    print(f"[INFO] Leyendo variables de: {env_path}")
    env_vars = load_env_vars(env_path)

    client_id = env_vars.get('CTRADER_CLIENT_ID')
    client_secret = env_vars.get('CTRADER_CLIENT_SECRET')
    refresh_token = env_vars.get('CTRADER_REFRESH_TOKEN')

    if not client_id or not client_secret or not refresh_token:
        print("[ERROR] Faltan credenciales de cTrader en .env:")
        print(f"  CTRADER_CLIENT_ID: {'PRESENTE' if client_id else 'FALTA'}")
        print(f"  CTRADER_CLIENT_SECRET: {'PRESENTE' if client_secret else 'FALTA'}")
        print(f"  CTRADER_REFRESH_TOKEN: {'PRESENTE' if refresh_token else 'FALTA'}")
        sys.exit(1)

    print("[INFO] Contactando endpoint de cTrader Open API...")
    url = "https://openapi.ctrader.com/apps/token"
    params = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': client_id,
        'client_secret': client_secret,
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        print(f"[INFO] Código HTTP de respuesta: {response.status_code}")
        data = response.json()
    except Exception as e:
        print(f"[ERROR] Error al contactar cTrader: {e}")
        sys.exit(1)

    if data.get('errorCode'):
        err_code = data.get('errorCode')
        err_desc = data.get('errorDescription', 'Sin descripción')
        print(f"[ERROR cTrader] {err_code}: {err_desc}")
        sys.exit(2)

    new_access_token = data.get('accessToken')
    new_refresh_token = data.get('refreshToken', refresh_token)
    expires_in = data.get('expiresIn', 'desconocido')

    if not new_access_token:
        print(f"[ERROR] Respuesta inesperada de cTrader: {data}")
        sys.exit(3)

    print(f"[SUCCESS] ¡Nuevo Access Token obtenido!")
    print(f"  Expira en: {expires_in} segundos (~{int(expires_in)//86400 if str(expires_in).isdigit() else '?'} días)")
    print(f"  Longitud token: {len(new_access_token)} caracteres")

    updates = {
        'CTRADER_ACCESS_TOKEN': new_access_token,
    }
    if new_refresh_token and new_refresh_token != refresh_token:
        updates['CTRADER_REFRESH_TOKEN'] = new_refresh_token
        print("  [INFO] Refresh token también actualizado.")

    update_env_file(env_path, updates)
    
    if '--restart' in sys.argv or '-r' in sys.argv:
        try:
            import subprocess
            subprocess.run(['systemctl', 'restart', 'etrade-forex', 'etrade-forex-scheduler'], check=True)
            print("[OK] Servicios etrade-forex y etrade-forex-scheduler reiniciados exitosamente.")
        except Exception as e:
            print(f"[!] No se pudieron reiniciar los servicios: {e}")
    else:
        print("\n[LISTO] Para aplicar el nuevo token, reinicia los servicios:")
        print("  systemctl restart etrade-forex etrade-forex-scheduler")

if __name__ == '__main__':
    main()
