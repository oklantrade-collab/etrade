import urllib.parse
import webbrowser
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import sys

CLIENT_ID = "24593_jdx856V6lzBMafxq01cDVFM9jWUeBxWzDQwni64HxOhJkKCaQK"
CLIENT_SECRET = "Zq6CGNHpsevUpS7ig7JMBlOA5A3lk8meEV01edc1hommDn5KSY"
REDIRECT_URI = "http://localhost:8080/callback"

class AuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        
        if 'code' in params:
            auth_code = params['code'][0]
            
            # Intercambiar código por token
            print("\n[+] Codigo de autorizacion recibido. Intercambiando por Access Token...")
            token_url = "https://openapi.ctrader.com/apps/token"
            payload = {
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": REDIRECT_URI,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET
            }
            try:
                res = requests.post(token_url, data=payload)
                data = res.json()
                if 'accessToken' in data:
                    print("🎉 SUCCESS! Token obtenido exitosamente.")
                    with open("token_result.txt", "w") as f:
                        f.write(data['accessToken'])
                    self.wfile.write(b"<h1>Autenticacion exitosa. Ya puedes cerrar esta ventana.</h1>")
                else:
                    print("Error al obtener el token:", data)
                    self.wfile.write(b"<h1>Fallo la autenticacion con la API</h1>")
            except Exception as e:
                print("Error de conexion:", e)
                self.wfile.write(b"<h1>Error de conexion</h1>")
        else:
            self.wfile.write(b"<h1>Fallo la autenticacion</h1>")
            print("No se recibio un auth code.")
            
        # Apagar servidor
        def kill_me():
            self.server.shutdown()
        threading.Thread(target=kill_me).start()

def main():
    print("Iniciando servidor local en el puerto 8080...")
    server_address = ('', 8080)
    httpd = HTTPServer(server_address, AuthHandler)
    print("Servidor corriendo. Esperando a que el usuario haga clic en Permitir el acceso...")
    httpd.serve_forever()
    print("Servidor cerrado. Proceso terminado.")

if __name__ == "__main__":
    main()
