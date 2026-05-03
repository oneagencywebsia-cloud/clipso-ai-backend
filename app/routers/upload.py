"""Router /upload — Genera URLs pre-firmadas para upload directo a R2"""
from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger

from app.core.security import get_current_user, AuthUser
from app.core.config import settings
from app.services.r2 import r2
from app.schemas.models import PresignedUploadRequest, PresignedUploadResponse

router = APIRouter(prefix="/upload", tags=["upload"])

ALLOWED_TYPES = {
    "video/mp4", "video/mpeg", "video/quicktime",
    "video/x-msvideo", "video/webm", "video/x-matroska"
}


@router.post("/presigned", response_model=PresignedUploadResponse)
async def get_presigned_upload(
    payload: PresignedUploadRequest,
    user: AuthUser = Depends(get_current_user)
):
    """Genera una URL pre-firmada para que el cliente suba el vídeo directo a R2"""
    if payload.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato no soportado. Permitidos: {', '.join(ALLOWED_TYPES)}"
        )

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if payload.size_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Archivo demasiado grande. Máximo: {settings.max_upload_size_mb}MB"
        )

    key = r2.generate_key(user.user_id, payload.filename, kind="input")
    upload_url = r2.generate_upload_url(key, payload.content_type, expires_in=3600)

    logger.info(f"Presigned URL generada para {user.user_id}: {key}")

    return PresignedUploadResponse(
        upload_url=upload_url,
        key=key,
        expires_in=3600
    )
