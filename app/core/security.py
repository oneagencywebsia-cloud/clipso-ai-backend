"""Auth middleware con Supabase JWT"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from typing import Optional

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
        # Si tenemos JWT secret, verificamos
        if settings.supabase_jwt_secret:
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated"
            )
        else:
            # Fallback: decodifica sin verificar (solo para dev)
            payload = jwt.get_unverified_claims(token)

        user_id = payload.get("sub")
        email = payload.get("email")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido"
            )

        return AuthUser(user_id=user_id, email=email, claims=payload)

    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido: {str(e)}"
        )


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[AuthUser]:
    """Auth opcional — no falla si no hay token"""
    if not credentials:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None
