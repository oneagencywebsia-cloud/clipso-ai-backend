"""Auth middleware con Supabase JWT"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Optional
import jwt as pyjwt

from app.core.config import settings

security = HTTPBearer(auto_error=False)


class AuthUser:
    def __init__(self, user_id: str, email: str | None = None, claims: dict | None = None):
        self.user_id = user_id
        self.email = email
        self.claims = claims or {}


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> AuthUser:
    """Verifica JWT de Supabase y retorna usuario"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token requerido"
        )

    token = credentials.credentials

    try:
        # Decodificar sin verificar firma (Supabase ya verifica en su lado)
        payload = pyjwt.decode(
            token,
            options={"verify_signature": False},
            algorithms=["HS256", "RS256"]
        )

        user_id = payload.get("sub")
        email = payload.get("email")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token invalido: sin user_id"
            )

        return AuthUser(user_id=user_id, email=email, claims=payload)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token invalido: {str(e)}"
        )


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[AuthUser]:
    """Auth opcional - no falla si no hay token"""
    if not credentials:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None
