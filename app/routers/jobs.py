"""Router /jobs — Encola y monitoriza trabajos de procesamiento"""
from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger

from app.core.security import get_current_user, AuthUser
from app.services.db import db
from app.services.r2 import r2
from app.schemas.models import JobCreateRequest, JobResponse, JobFeedback
from app.workers.queue import enqueue_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreateRequest,
    user: AuthUser = Depends(get_current_user)
):
    """Crea un nuevo job de procesamiento y lo encola"""
    project = db.get_project(payload.project_id, user.user_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proyecto no encontrado"
        )

    for key in payload.input_keys:
        if not r2.exists(key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Archivo no encontrado en storage: {key}"
            )

    job = db.create_job(
        project_id=payload.project_id,
        user_id=user.user_id,
        input_keys=payload.input_keys,
        preferences=payload.preferences
    )

    enqueue_job(
        job_id=job["id"],
        target_resolution=payload.target_resolution,
        target_fps=payload.target_fps
    )

    logger.info(f"Job encolado: {job['id']}")
    return job


@router.get("", response_model=list[JobResponse])
async def list_jobs(user: AuthUser = Depends(get_current_user)):
    """Lista todos los jobs del usuario"""
    return db.list_user_jobs(user.user_id)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job_status(
    job_id: str,
    user: AuthUser = Depends(get_current_user)
):
    """Estado de un job específico"""
    job = db.get_job(job_id)
    if not job or job["user_id"] != user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job no encontrado"
        )
    return job


@router.get("/{job_id}/download")
async def get_download_url(
    job_id: str,
    user: AuthUser = Depends(get_current_user)
):
    """URL pre-firmada para descargar el resultado"""
    job = db.get_job(job_id)
    if not job or job["user_id"] != user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job no encontrado"
        )

    if job["status"] != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job aún no completado. Estado: {job['status']}"
        )

    if not job.get("output_key"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay archivo de salida"
        )

    download_url = r2.generate_download_url(
        job["output_key"],
        expires_in=3600,
        download_filename=f"clipso-{job_id[:8]}.mp4"
    )

    return {"download_url": download_url, "expires_in": 3600}


@router.post("/{job_id}/feedback", response_model=JobResponse)
async def submit_feedback(
    job_id: str,
    payload: JobFeedback,
    user: AuthUser = Depends(get_current_user)
):
    """Re-edita el vídeo con instrucciones del usuario"""
    job = db.get_job(job_id)
    if not job or job["user_id"] != user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job no encontrado"
        )

    if job["status"] != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Solo puedes dar feedback en jobs completados"
        )

    new_job = db.create_job(
        project_id=job["project_id"],
        user_id=user.user_id,
        input_keys=job["input_keys"],
        preferences=payload.instructions
    )

    enqueue_job(job_id=new_job["id"], parent_job_id=job_id)

    logger.info(f"Feedback enviado, nuevo job: {new_job['id']}")
    return new_job
