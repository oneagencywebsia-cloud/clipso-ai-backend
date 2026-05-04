"""Redis Queue - encola y procesa jobs"""
from redis import Redis
from rq import Queue
from loguru import logger

from app.core.config import settings


_redis_conn = None
_queue = None


def get_redis():
    global _redis_conn
    if _redis_conn is None:
        _redis_conn = Redis.from_url(settings.redis_url)
    return _redis_conn


def get_queue():
    global _queue
    if _queue is None:
        _queue = Queue("clipso-pipeline", connection=get_redis(), default_timeout=3600)
    return _queue


def enqueue_job(
    job_id: str,
    target_resolution: str = "1080p",
    target_fps: int = 30,
    parent_job_id: str | None = None
) -> str:
    """Encola un job de procesamiento de vídeo"""
    queue = get_queue()
    rq_job = queue.enqueue_call(
        func="app.workers.pipeline.process_video_job",
        kwargs={
            "job_id": job_id,
            "target_resolution": target_resolution,
            "target_fps": target_fps,
            "parent_job_id": parent_job_id
        },
        job_id=f"clipso-{job_id}",
        result_ttl=86400
    )
    logger.info(f"Encolado en Redis: {rq_job.id}")
    return rq_job.id


def get_queue_stats() -> dict:
    """Estadisticas de la cola"""
    queue = get_queue()
    return {
        "queued": queue.count,
        "started": queue.started_job_registry.count,
        "finished": queue.finished_job_registry.count,
        "failed": queue.failed_job_registry.count
    }
