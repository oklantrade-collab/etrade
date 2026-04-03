import os
from datetime import datetime, timedelta
from typing import Optional, Any, Dict
from jose import jwt, JWTError
from passlib.context import CryptContext
from app.core.config import settings
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# Password Hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Constants
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "etrade-ultra-secret-key-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 24 hours
VERIFICATION_TOKEN_EXPIRE_HOURS = 24
RESET_PASSWORD_TOKEN_EXPIRE_HOURS = 1

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Optional[dict]:
    try:
        decoded_token = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return decoded_token if decoded_token["exp"] >= datetime.utcnow().timestamp() else None
    except JWTError:
        return None

def send_email(to_email: str, subject: str, content: str):
    """Sends an email using SendGrid."""
    if not settings.sendgrid_api_key:
        print(f"[WARNING] SendGrid API Key not configured. Simulate email to {to_email}: {subject}")
        return
    
    message = Mail(
        from_email=settings.sendgrid_from_email or "noreply@etrade.com",
        to_emails=to_email,
        subject=subject,
        html_content=content
    )
    try:
        sg = SendGridAPIClient(settings.sendgrid_api_key)
        response = sg.send(message)
        print(f"[SUCCESS] Email sent to {to_email}. Status: {response.status_code}")
    except Exception as e:
        print(f"[ERROR] Error sending email: {str(e)}")

def send_verification_email(name: str, email: str, token: str):
    verify_url = f"{settings.next_public_url}/auth/verify?token={token}"
    subject = "Verifica tu cuenta en eTrade"
    content = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: auto; padding: 20px; background: #121212; color: #ffffff; border-radius: 10px;">
        <h2 style="color: #10b981;">Hola, {name}!</h2>
        <p>Gracias por registrarte en <b>eTrade</b>. Para activar tu cuenta, haz clic en el siguiente botón:</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{verify_url}" style="background: #10b981; color: #000; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">Verificar mi cuenta</a>
        </div>
        <p style="font-size: 12px; color: #888;">Este enlace expirará en 24 horas.</p>
        <hr style="border: 0; border-top: 1px solid #333; margin: 20px 0;">
        <p style="font-size: 11px; text-align: center;">eTrade Platform — Financial Institutions Premium</p>
    </div>
    """
    send_email(email, subject, content)

def send_reset_password_email(name: str, email: str, token: str):
    reset_url = f"{settings.next_public_url}/auth/reset-password?token={token}"
    subject = "Restablecer contraseña - eTrade"
    content = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: auto; padding: 20px; background: #121212; color: #ffffff; border-radius: 10px;">
        <h2 style="color: #10b981;">Restablecer contraseña</h2>
        <p>Hola, {name}. Has solicitado restablecer tu contraseña. Haz clic en el botón de abajo para continuar:</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{reset_url}" style="background: #10b981; color: #000; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">Nueva contraseña</a>
        </div>
        <p style="font-size: 12px; color: #888;">Este enlace expirará en 1 hora.</p>
        <hr style="border: 0; border-top: 1px solid #333; margin: 20px 0;">
        <p style="font-size: 11px; text-align: center;">eTrade Platform — Financial Institutions Premium</p>
    </div>
    """
    send_email(email, subject, content)

# --- Dependencies for RBAC ---
from fastapi import Request, HTTPException, Depends
from typing import List

# Dependency for current user
def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        # Check Authorization header as fallback if not in cookies
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")
    
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Sesión expirada")
    
    return payload # Contains sub, email, role

# Dependency for RBAC
def check_role(allowed_roles: List[str]):
    def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user.get('role') not in allowed_roles:
            raise HTTPException(
                status_code=403, 
                detail=f"Permisos insuficientes. Se requiere rol: {', '.join(allowed_roles)}"
            )
        return current_user
    return role_checker
