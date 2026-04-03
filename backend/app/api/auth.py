from fastapi import APIRouter, HTTPException, Response, Request, Depends, Cookie
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timedelta
from app.core.supabase_client import get_supabase
from app.core.auth_handler import (
    hash_password, verify_password, create_access_token, decode_token,
    send_verification_email, send_reset_password_email
)
import uuid

router = APIRouter()
sb = get_supabase()

# --- Pydantic Models ---
class RegisterUser(BaseModel):
    nombre: str
    correo: EmailStr
    password: str
    confirm_password: str
    codigo_registro: str

class LoginUser(BaseModel):
    correo: EmailStr
    password: str

class ForgotPassword(BaseModel):
    correo: EmailStr

class ResetPassword(BaseModel):
    token: str
    new_password: str

# --- Endpoints ---

@router.post("/register")
def register(user: RegisterUser):
    if user.password != user.confirm_password:
        raise HTTPException(status_code=400, detail="Las contraseñas no coinciden.")
    
    if len(user.password) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres.")

    # Validate Registration Code and get Role
    res_role = sb.table("roles").select("*").eq("codigo_registro", user.codigo_registro).eq("activo", True).execute()
    if not res_role.data:
        raise HTTPException(status_code=400, detail="Código de registro inválido.")
    
    role_id = res_role.data[0]['id']
    role_name = res_role.data[0]['nombre']

    # Check if user already exists
    res_user = sb.table("usuarios").select("*").eq("correo", user.correo.lower()).execute()
    if res_user.data:
        raise HTTPException(status_code=400, detail="El correo electrónico ya está registrado.")

    # Create User
    hashed_pwd = hash_password(user.password)
    verification_token = str(uuid.uuid4())
    token_exp = datetime.utcnow() + timedelta(hours=24)

    new_user = {
        "nombre": user.nombre,
        "correo": user.correo.lower(),
        "password_hash": hashed_pwd,
        "rol_id": role_id,
        "verificado": False,
        "token_verificacion": verification_token,
        "token_expiracion": token_exp.isoformat(),
        "activo": True
    }

    try:
        res_create = sb.table("usuarios").insert(new_user).execute()
        if res_create.data:
            # Send Email
            send_verification_email(user.nombre, user.correo, verification_token)
            return {"status": "success", "message": "Registro exitoso. Por favor verifica tu correo electrónico."}
        else:
            raise HTTPException(status_code=500, detail="Error al crear el usuario.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.post("/login")
def login(user: LoginUser, response: Response):
    # Get user
    res_user = sb.table("usuarios").select("*, roles(nombre)").eq("correo", user.correo.lower()).execute()
    if not res_user.data:
        raise HTTPException(status_code=401, detail="Credenciales inválidas.")
    
    db_user = res_user.data[0]
    
    if not verify_password(user.password, db_user['password_hash']):
        raise HTTPException(status_code=401, detail="Credenciales inválidas.")
    
    if not db_user['verificado']:
        raise HTTPException(status_code=403, detail="Por favor verifica tu correo electrónico antes de ingresar.")
    
    if not db_user['activo']:
        raise HTTPException(status_code=403, detail="Tu cuenta está desactivada. Contacta al administrador.")

    # Create JWT
    token_data = {
        "sub": str(db_user['id']),
        "email": db_user['correo'],
        "role": db_user['roles']['nombre']
    }
    access_token = create_access_token(data=token_data)

    # Set Cookie
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True, # In production
        samesite="lax",
        max_age=3600 * 24 # 1 day
    )

    return {
        "status": "success",
        "user": {
            "nombre": db_user['nombre'],
            "correo": db_user['correo'],
            "rol": db_user['roles']['nombre']
        }
    }

@router.get("/verify/{token}")
def verify_email(token: str):
    res_user = sb.table("usuarios").select("*").eq("token_verificacion", token).execute()
    if not res_user.data:
        raise HTTPException(status_code=400, detail="Token de verificación inválido.")
    
    user = res_user.data[0]
    
    # Check expiry
    if datetime.fromisoformat(user['token_expiracion'].replace('Z', '+00:00')) < datetime.utcnow().replace(tzinfo=None):
        raise HTTPException(status_code=400, detail="El token de verificación ha expirado.")

    # Verify user
    sb.table("usuarios").update({
        "verificado": True,
        "token_verificacion": None,
        "token_expiracion": None
    }).eq("id", user['id']).execute()

    return {"status": "success", "message": "Correo verificado correctamente. Ahora puedes iniciar sesión."}

@router.post("/forgot-password")
def forgot_password(data: ForgotPassword):
    res_user = sb.table("usuarios").select("*").eq("correo", data.correo.lower()).execute()
    if not res_user.data:
        # Don't reveal if user exists for security
        return {"status": "success", "message": "Si el correo está registrado, recibirás un enlace para restablecer tu contraseña."}
    
    user = res_user.data[0]
    reset_token = str(uuid.uuid4())
    token_exp = datetime.utcnow() + timedelta(hours=1)

    sb.table("usuarios").update({
        "token_reset_pass": reset_token,
        "token_reset_exp": token_exp.isoformat()
    }).eq("id", user['id']).execute()

    send_reset_password_email(user['nombre'], user['correo'], reset_token)

    return {"status": "success", "message": "Enlace enviado al correo proporcionado."}

@router.post("/reset-password")
def reset_password(data: ResetPassword):
    res_user = sb.table("usuarios").select("*").eq("token_reset_pass", data.token).execute()
    if not res_user.data:
        raise HTTPException(status_code=400, detail="Token inválido o expirado.")
    
    user = res_user.data[0]
    
    # Check expiry
    if datetime.fromisoformat(user['token_reset_exp'].replace('Z', '+00:00')) < datetime.utcnow().replace(tzinfo=None):
        raise HTTPException(status_code=400, detail="El token ha expirado.")

    # Update password
    sb.table("usuarios").update({
        "password_hash": hash_password(data.new_password),
        "token_reset_pass": None,
        "token_reset_exp": None
    }).eq("id", user['id']).execute()

    return {"status": "success", "message": "Contraseña actualizada correctamente."}

@router.get("/me")
def get_me(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado.")
    
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Sesión expirada.")
    
    res_user = sb.table("usuarios").select("nombre, correo, roles(nombre)").eq("id", payload['sub']).execute()
    if not res_user.data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    
    user_data = res_user.data[0]
    return {
        "nombre": user_data['nombre'],
        "correo": user_data['correo'],
        "rol": user_data['roles']['nombre']
    }

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"status": "success", "message": "Sesión cerrada correctamente."}
