"""Router /projects — Gestión de proyectos del usuario"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_user, AuthUser
from app.services.db import db
from app.schemas.models import ProjectCreate, ProjectResponse

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    user: AuthUser = Depends(get_current_user)
):
    """Crea un nuevo proyecto del usuario"""
    project = db.create_project(user_id=user.user_id, name=payload.name)
    return project


@router.get("", response_model=list[ProjectResponse])
async def list_projects(user: AuthUser = Depends(get_current_user)):
    """Lista todos los proyectos del usuario"""
    return db.list_user_projects(user.user_id)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    user: AuthUser = Depends(get_current_user)
):
    """Obtiene un proyecto por ID"""
    project = db.get_project(project_id, user.user_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proyecto no encontrado"
        )
    return project
