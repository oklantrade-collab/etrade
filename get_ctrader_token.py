import urllib.parse
import webbrowser
import requests
import json
import re
import os
import subprocess
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import sys

CLIENT_ID = "24593_jdx856V6lzBMafxq01cDVFM9jWUeBxWzDQwni64HxOhJkKCaQK"
CLIENT_SECRET = "Zq6CGNHpsevUpS7ig7JMBlOA5A3lk8meEV01edc1hommDn5KSY"
REDIRECT_URI = "http://localhost:8080/callback"

SSH_KEY = Path("C:/Users/jyups/.ssh/etrade_cloud_key")
DROPLET_IP = "165.22.87.171"
DROPLET_ENV = "/home/etrade/etrade/backend/.env"
LOCAL_ENV = Path(__file__).resolve().parent / "backend" / ".env"

def update_env_file(env_path: Path, updates: dict):
    if not env_path.exists():
        print(f"[!] Archivo {env_path} no encontrado.")
        return
    with open(env_path, "r", encoding="utf-8") as f:
        content = f.read()

    for key, new_val in updates.items():
        pattern = rf'^{key}=.*$'
        replacement = f'{key}="{new_val}"'
        if re.search(pattern, content, flags=re.MULTILINE):
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        else:
            content += f'\n{key}="{new_val}"\n'

    with open(env_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ Archivo local actualizado: {env_path}")

def deploy_to_droplet(access_token: str, refresh_token: str):
    print("\n📡 Sincronizando nuevo token con el Droplet de producción...")
    cmd_sed = (
        f'ssh -i {SSH_KEY} -o StrictHostKeyChecking=no root@{DROPLET_IP} '
        f'"sed -i -E \\"s/^CTRADER_ACCESS_TOKEN=.*/CTRADER_ACCESS_TOKEN=\\\\\\"{access_token}\\\\\\"/\\" {DROPLET_ENV} && '
        f'sed -i -E \\"s/^CTRADER_REFRESH_TOKEN=.*/CTRADER_REFRESH_TOKEN=\\\\\\"{refresh_token}\\\\\\"/\\" {DROPLET_ENV} && '
        f'systemctl restart etrade-forex etrade-forex-scheduler && '
        f'echo OK"'
    )
    try:
        res = subprocess.run(cmd_sed, shell=True, capture_output=True, text=True, timeout=30)
        if "OK" in res.stdout:
            print("🚀 Droplet actualizado y servicios reiniciados con éxito (etrade-forex, etrade-forex-scheduler).")
        else:
            print(f"[!] Salida Droplet: {res.stdout} {res.stderr}")
    except Exception as ex:
        print(f"[!] Error al sincronizar con Droplet: {ex}")

class AuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        
        if 'code' in params:
            auth_code = params['code'][0]
            print(f"\n[+] Código de autorización recibido: {auth_code[:8]}...")
            print("[+] Solicitando tokens a cTrader Open API...")
            
            token_url = "https://openapi.ctrader.com/apps/token"
            payload = {
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": REDIRECT_URI,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET
            }
            try:
                res = requests.post(token_url, data=payload, timeout=20)
                data = res.json()
                if 'accessToken' in data:
                    access_token = data['accessToken']
                    refresh_token = data.get('refreshToken', '')
                    expires_in = data.get('expiresIn', 2592000)
                    
                    print(f"\n🎉 ¡AUTENTICACIÓN EXITOSA CON CTRADER!")
                    print(f"🔑 Access Token: {access_token[:12]}... (Longitud: {len(access_token)})")
                    print(f"🔄 Refresh Token: {refresh_token[:12]}... (Longitud: {len(refresh_token)})")
                    print(f"⏳ Validez: {expires_in} segundos (~{int(expires_in)//86400} días)")
                    
                    # Guardar archivo de respaldo
                    with open("token_result.txt", "w", encoding="utf-8") as f:
                        f.write(json.dumps(data, indent=2))
                    print("💾 Guardado en token_result.txt")
                    
                    # Actualizar local .env
                    updates = {
                        "CTRADER_ACCESS_TOKEN": access_token,
                        "CTRADER_REFRESH_TOKEN": refresh_token,
                    }
                    update_env_file(LOCAL_ENV, updates)
                    
                    # Sincronizar Droplet
                    deploy_to_droplet(access_token, refresh_token)
                    
                    html_ok = (
                        "<html><body style='font-family:sans-serif;text-align:center;padding:50px;background:#f0fdf4;color:#166534;'>"
                        "<h1>✅ ¡Autenticación con cTrader Exitosa!</h1>"
                        "<p>Los nuevos Access Token y Refresh Token han sido guardados y sincronizados con el servidor.</p>"
                        "<p>Ya puedes cerrar esta ventana y regresar a la consola.</p>"
                        "</body></html>"
                    )
                    self.wfile.write(html_ok.encode("utf-8"))
                else:
                    err_msg = json.dumps(data)
                    print(f"[!] Error al obtener tokens: {err_msg}")
                    html_err = f"<html><body style='font-family:sans-serif;color:red;'><h1>Fallo al obtener Token</h1><pre>{err_msg}</pre></body></html>"
                    self.wfile.write(html_err.encode("utf-8"))
            except Exception as e:
                print(f"[!] Error de conexión con cTrader: {e}")
                self.wfile.write(f"<h1>Error de conexion: {e}</h1>".encode("utf-8"))
        else:
            self.wfile.write(b"<h1>No se recibio codigo de autorizacion.</h1>")
            print("[!] No se recibió parámetro 'code' en la URL de callback.")
            
        def kill_me():
            self.server.shutdown()
        threading.Thread(target=kill_me).start()

def main():
    auth_url = (
        f"https://openapi.ctrader.com/apps/auth?"
        f"client_id={CLIENT_ID}&"
        f"redirect_uri={urllib.parse.quote(REDIRECT_URI)}&"
        f"scope=trading"
    )
    
    print("=" * 70)
    print("  eTrader — Asistente de Renovación de Token cTrader Open API")
    print("=" * 70)
    print("\nIniciando servidor local en el puerto 8080...")
    try:
        server_address = ('', 8080)
        httpd = HTTPServer(server_address, AuthHandler)
    except OSError as e:
        print(f"[!] Error al abrir puerto 8080: {e}")
        print("    Asegúrate de que no haya otra instancia corriendo.")
        return
        
    print("Servidor local activo en http://localhost:8080/callback")
    print("\nAbriendo navegador automáticamente para autorizar...")
    print(f"\nSi no abre automáticamente, ingresa manualmente a esta URL:\n\n{auth_url}\n")
    
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass
        
    print("Esperando autorización en el navegador...")
    httpd.serve_forever()
    print("\n[OK] Servidor local cerrado. Proceso completado.")

if __name__ == "__main__":
    main()
