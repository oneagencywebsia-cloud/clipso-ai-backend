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

            # Paso 2: Concatenar si hay varios (15% → 18%)
            if len(input_files) > 1:
                concat_path = workdir / "concat.mp4"
                video.concat_videos(input_files, concat_path)
                raw_video = concat_path
            else:
                raw_video = input_files[0]

            update_progress(job_id, 18)

            # Paso 2.5: Jump cuts — eliminar silencios largos (18% → 22%)
            cut_video = workdir / "cut.mp4"
            try:
                video.cut_silences(raw_video, cut_video, min_silence_duration=0.7)
                source_video = cut_video
            except Exception as e:
                logger.warning(f"cut_silences falló, usando video original: {e}")
                source_video = raw_video

            update_progress(job_id, 22)

            # Paso 3: Extraer audio para Whisper (22% → 30%)
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

            # Paso 8: Captions virales palabra-por-palabra (80% → 92%)
            words = (transcription or {}).get("words") or []
            sub_config = plan_data.get("subtitles", {})
            highlight_color = sub_config.get("color", "#FFFF00")

            info = video.get_video_info(source_video)
            v_w = (info.get("video") or {}).get("width") or 1080
            v_h = (info.get("video") or {}).get("height") or 1920

            with_subs = workdir / "with_subs.mp4"
            if words:
                ass_path = workdir / "viral_captions.ass"
                video.generate_viral_captions_ass(
                    words,
                    ass_path,
                    video_width=v_w,
                    video_height=v_h,
                    highlight_color=highlight_color
                )
                video.burn_ass_subtitles(source_video, ass_path, with_subs)
            else:
                segments = (transcription or {}).get("segments") or []
                srt_content = video.transcription_to_srt(segments)
                srt_path = workdir / "subs.srt"
                srt_path.write_text(srt_content, encoding="utf-8")
                video.burn_subtitles(source_video, srt_path, with_subs)

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
