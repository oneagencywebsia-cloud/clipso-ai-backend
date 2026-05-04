"""CLIPSO.AI Backend — Entry point FastAPI"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from loguru import logger

from app.core.config import settings
from app.routers import upload, projects, jobs
from app.schemas.models import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 {settings.app_name} v{settings.app_version} arrancando...")
    logger.info(f"📦 Environment: {settings.environment}")
    logger.info(f"🌐 R2 endpoint: {settings.r2_endpoint}")
    yield
    logger.info("👋 Apagando servicio...")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API de CLIPSO.AI — Edición de vídeo con IA",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

logger.info(f"✅ CORS configured for origins: {settings.cors_origins}")


@app.get("/", tags=["health"])
async def root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "online",
        "docs": "/docs"
    }


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment
    )


# Routers
app.include_router(upload.router, prefix="/v1")
app.include_router(projects.router, prefix="/v1")
app.include_router(jobs.router, prefix="/v1")


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception("Error no controlado")
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor"}
    )
