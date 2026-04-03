from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from app.core.supabase_client import get_supabase
from app.core.auth_handler import check_role

router = APIRouter()
sb = get_supabase()

# --- RBAC Dependency: Only CEO can access admin panel ---
ceo_only = Depends(check_role(["CEO"]))

# --- Pydantic Models ---
class RoleUpdate(BaseModel):
    codigo_registro: str

class RoleCreate(BaseModel):
    nombre: str
    codigo_registro: str
    descripcion: Optional[str] = ""

class UserUpdate(BaseModel):
    activo: bool
    rol_id: Optional[int] = None

# --- Endpoints ---

@router.get("/roles", dependencies=[ceo_only])
def get_roles():
    # Use RPC or select with count of active users
    # For now, select roles and we can calculate counts in memory or separate query
    res = sb.table("roles").select("*").execute()
    roles = res.data or []
    
    # Enrich with user count
    for role in roles:
        user_res = sb.table("usuarios").select("id", count="exact").eq("rol_id", role['id']).eq("activo", True).execute()
        role['usuarios_activos'] = user_res.count if user_res.count is not None else 0
        
    return roles

@router.post("/roles", dependencies=[ceo_only])
def create_role(role: RoleCreate):
    if len(role.codigo_registro) < 6:
        raise HTTPException(status_code=400, detail="El código de registro debe tener al menos 6 caracteres.")
    
    # Check if duplicate
    res_dup = sb.table("roles").select("id").eq("codigo_registro", role.codigo_registro).execute()
    if res_dup.data:
        raise HTTPException(status_code=400, detail="El código de registro ya está en uso.")
    
    new_role = {
        "nombre": role.nombre,
        "codigo_registro": role.codigo_registro,
        "descripcion": role.descripcion,
        "activo": True
    }
    
    try:
        res = sb.table("roles").insert(new_role).execute()
        return res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/roles/{role_id}", dependencies=[ceo_only])
def update_role(role_id: int, role_data: RoleUpdate):
    if len(role_data.codigo_registro) < 6:
        raise HTTPException(status_code=400, detail="El código de registro debe tener al menos 6 caracteres.")

    # Update role
    res = sb.table("roles").update({"codigo_registro": role_data.codigo_registro}).eq("id", role_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Rol no encontrado.")
    
    return res.data[0]

@router.get("/users", dependencies=[ceo_only])
def get_users():
    # List all users with their roles
    res = sb.table("usuarios").select("*, roles(nombre)").order("fecha_registro", desc=True).execute()
    return res.data or []

@router.patch("/users/{user_id}", dependencies=[ceo_only])
def update_user(user_id: str, data: UserUpdate):
    update_fields = {}
    if data.activo is not None:
        update_fields["activo"] = data.activo
    if data.rol_id is not None:
        update_fields["rol_id"] = data.rol_id
        
    res = sb.table("usuarios").update(update_fields).eq("id", user_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    
    return res.data[0]
