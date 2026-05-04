"""Pipeline de procesamiento — Orquesta IA + FFmpeg"""
import tempfile
import json
import urllib.request
from pathlib import Path
from loguru import logger

from app.services.db import db
from app.services.r2 import r2
from app.services import openai_service, video


def update_progress(job_id: str, progress: int, status: str = "processing"):
    db.update_job(job_id, {"progress": progress, "status": status})


def process_video_job(
    job_id: str,
    target_resolution: str = "1080p",
    target_fps: int = 30,
    parent_job_id: str | None = None
):
    """Pipeline completo: descarga → análisis → edición → upload"""
    logger.info(f"Iniciando pipeline para job {job_id}")

    job = db.get_job(job_id)
    if not job:
        logger.error(f"Job {job_id} no encontrado")
        return

    try:
        update_progress(job_id, 5, "processing")

        with tempfile.TemporaryDirectory(prefix=f"clipso_{job_id[:8]}_") as tmp:
            workdir = Path(tmp)
            input_files = []

            # Paso 1: Descargar inputs de R2 (5% → 15%)
            for i, key in enumerate(job["input_keys"]):
                local_path = workdir / f"input_{i}.mp4"
                logger.info(f"Descargando {key}")
                r2.client.download_file(r2.bucket, key, str(local_path))
                input_files.append(local_path)

            update_progress(job_id, 15)

            # Paso 2: Concatenar si hay varios (15% → 20%)
            if len(input_files) > 1:
                concat_path = workdir / "concat.mp4"
                video.concat_videos(input_files, concat_path)
                source_video = concat_path
            else:
                source_video = input_files[0]

            update_progress(job_id, 20)

            # Paso 3: Extraer audio para Whisper (20% → 30%)
            audio_path = workdir / "audio.mp3"
            video.extract_audio(source_video, audio_path)
            update_progress(job_id, 30)

            # Paso 4: Transcripción Whisper (30% → 45%)
            logger.info("Whisper transcribiendo...")
            transcription = openai_service.transcribe_audio(audio_path)
            update_progress(job_id, 45)

            # Paso 5: Extraer frames para análisis visual (45% → 55%)
            frames_dir = workdir / "frames"
            frames = video.extract_frames(source_video, frames_dir, fps=0.5, max_frames=15)
            update_progress(job_id, 55)

            # Paso 6: GPT-4 Vision análisis (55% → 70%)
            logger.info("GPT-4 Vision analizando frames...")
            visual_analysis = openai_service.analyze_frames(frames)
            update_progress(job_id, 70)

            # Paso 7: Generar Production Plan (70% → 80%)
            logger.info("Generando Production Plan...")
            plan = openai_service.generate_production_plan(
                transcription=transcription or {},
                visual_analysis=visual_analysis or {},
                user_preferences=job.get("preferences")
            )
            try:
                plan_data = json.loads(plan.get("plan", "{}"))
            except (json.JSONDecodeError, AttributeError):
                plan_data = {}
                logger.warning("No se pudo parsear Production Plan JSON")
            update_progress(job_id, 80)

            # Paso 8: Aplicar edición — subtítulos quemados (80% → 92%)
            segments = (transcription or {}).get("segments") or []
            srt_content = video.transcription_to_srt(segments)
            srt_path = workdir / "subs.srt"
            srt_path.write_text(srt_content, encoding="utf-8")

            sub_config = plan_data.get("subtitles", {})
            sub_font_size = sub_config.get("font_size", 28)
            sub_color = sub_config.get("color", "white")
            sub_position = sub_config.get("position", "bottom")

            with_subs = workdir / "with_subs.mp4"
            video.burn_subtitles(
                source_video,
                srt_path,
                with_subs,
                font_size=sub_font_size,
                font_color=sub_color,
                position=sub_position
            )
            update_progress(job_id, 92)

            # Paso 8.5: Aplicar color grading desde Production Plan
            grading_style = plan_data.get("color_grading", "neutral")
            graded_path = workdir / "graded.mp4"
            video.apply_color_grading(with_subs, graded_path, grading_style=grading_style)

            # Paso 8.6: Aplicar B-roll con DALL-E
            broll_list = plan_data.get("broll", [])[:3]
            broll_output = graded_path
            for i, broll in enumerate(broll_list):
                try:
                    dalle_prompt = broll.get("dalle_prompt", "")
                    if not dalle_prompt:
                        continue
                    logger.info(f"Generando B-roll {i+1}/{len(broll_list)}")
                    image_url = openai_service.generate_broll_image(dalle_prompt)
                    image_path = workdir / f"broll_{i}.jpg"
                    urllib.request.urlretrieve(image_url, str(image_path))

                    broll_next = workdir / f"with_broll_{i}.mp4"
                    video.overlay_image_at_timestamp(
                        broll_output,
                        image_path,
                        broll_next,
                        start_time=broll.get("timestamp", 0),
                        duration=broll.get("duration", 2)
                    )
                    broll_output = broll_next
                except Exception as e:
                    logger.warning(f"Error generando B-roll {i}: {e}")

            # Paso 8.7: Aplicar animaciones de texto
            animations = plan_data.get("animations", [])[:5]
            anim_output = broll_output
            for i, anim in enumerate(animations):
                try:
                    text = anim.get("description", "")[:30]
                    if not text:
                        continue
                    logger.info(f"Añadiendo animación de texto {i+1}/{len(animations)}")

                    anim_next = workdir / f"with_anim_{i}.mp4"
                    video.add_text_overlay(
                        anim_output,
                        anim_next,
                        text=text,
                        timestamp=anim.get("timestamp", 0),
                        duration=anim.get("duration", 1.5),
                        font_size=48,
                        text_color="white"
                    )
                    anim_output = anim_next
                except Exception as e:
                    logger.warning(f"Error en animación {i}: {e}")

            # Paso 9: Render final a resolución objetivo (93% → 96%)
            final_path = workdir / "final.mp4"
            video.upscale_to_resolution(anim_output, final_path, target=target_resolution)
            update_progress(job_id, 96)

            # Paso 10: Subir resultado a R2 (96% → 100%)
            output_key = f"output/{job['user_id']}/{job_id}.mp4"
            with open(final_path, "rb") as f:
                r2.upload_file(f, output_key, content_type="video/mp4")

            db.update_job(job_id, {
                "status": "completed",
                "progress": 100,
                "output_key": output_key,
                "metadata": {
                    "transcription": transcription.get("text", "")[:500],
                    "language": transcription.get("language"),
                    "duration": transcription.get("duration"),
                    "plan": plan.get("plan"),
                    "visual_analysis": visual_analysis.get("analysis"),
                    "target_resolution": target_resolution
                }
            })

            logger.success(f"Job {job_id} completado: {output_key}")

    except Exception as e:
        logger.exception(f"Pipeline error en job {job_id}")
        db.update_job(job_id, {
            "status": "failed",
            "error_message": str(e)[:500]
        })
        raise
