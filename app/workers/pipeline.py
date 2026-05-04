"""Pipeline de procesamiento — Orquesta IA + FFmpeg"""
import tempfile
import json
import urllib.request
import random
from pathlib import Path
from loguru import logger

from app.services.db import db
from app.services.r2 import r2
from app.services import openai_service, video


ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
SFX_DIR = ASSETS_DIR / "sfx"
MUSIC_DIR = ASSETS_DIR / "music"


def update_progress(job_id: str, progress: int, status: str = "processing"):
    db.update_job(job_id, {"progress": progress, "status": status})


def _pick_sfx(name: str) -> Path | None:
    """Devuelve un SFX por nombre si existe."""
    p = SFX_DIR / f"{name}.mp3"
    return p if p.exists() else None


def _pick_music(mood: str = "chill") -> Path | None:
    """Devuelve un track de música según mood."""
    candidates = list(MUSIC_DIR.glob("*.mp3"))
    if not candidates:
        return None
    # Match por nombre
    for c in candidates:
        if mood.lower() in c.stem.lower():
            return c
    return random.choice(candidates)


def process_video_job(
    job_id: str,
    target_resolution: str = "1080p",
    target_fps: int = 30,
    parent_job_id: str | None = None
):
    """Pipeline completo: descarga → análisis → edición pro → upload"""
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

            # Paso 1: Descargar inputs (5% → 12%)
            for i, key in enumerate(job["input_keys"]):
                local_path = workdir / f"input_{i}.mp4"
                logger.info(f"Descargando {key}")
                r2.client.download_file(r2.bucket, key, str(local_path))
                input_files.append(local_path)
            update_progress(job_id, 12)

            # Paso 2: Concatenar (12% → 15%)
            if len(input_files) > 1:
                concat_path = workdir / "concat.mp4"
                video.concat_videos(input_files, concat_path)
                raw_video = concat_path
            else:
                raw_video = input_files[0]
            update_progress(job_id, 15)

            # Pre-análisis rápido para decidir jump cuts (15% → 20%)
            # Ejecutamos un análisis preliminar más adelante; por ahora aplicamos
            # cut_silences solo si el video > 30s (heurística — los cortos no lo necesitan).
            info_raw = video.get_video_info(raw_video)
            duration_raw = info_raw.get("duration", 0)

            if duration_raw > 30:
                cut_video = workdir / "cut.mp4"
                try:
                    video.cut_silences(raw_video, cut_video, min_silence_duration=0.7)
                    source_video = cut_video
                    logger.info(f"Jump cuts aplicados (video {duration_raw:.0f}s)")
                except Exception as e:
                    logger.warning(f"cut_silences falló: {e}")
                    source_video = raw_video
            else:
                logger.info(f"Saltando jump cuts (video corto: {duration_raw:.0f}s)")
                source_video = raw_video
            update_progress(job_id, 20)

            # Paso 3: Audio para Whisper (20% → 25%)
            audio_path = workdir / "audio.mp3"
            video.extract_audio(source_video, audio_path)
            update_progress(job_id, 25)

            # Paso 4: Whisper (25% → 40%)
            logger.info("Whisper transcribiendo...")
            transcription = openai_service.transcribe_audio(audio_path)
            update_progress(job_id, 40)

            # Paso 5: Frames (40% → 48%)
            frames_dir = workdir / "frames"
            frames = video.extract_frames(source_video, frames_dir, fps=0.5, max_frames=15)
            update_progress(job_id, 48)

            # Paso 6: GPT-4 Vision (48% → 60%)
            logger.info("GPT-4 Vision analizando...")
            visual_analysis = openai_service.analyze_frames(frames)
            update_progress(job_id, 60)

            # Paso 7: Production Plan (60% → 70%)
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
            update_progress(job_id, 70)

            info = video.get_video_info(source_video)
            v_w = (info.get("video") or {}).get("width") or 1080
            v_h = (info.get("video") or {}).get("height") or 1920

            # === DECISIONES ESTRATÉGICAS DEL LLM ===
            decisions = plan_data.get("decisions", {})
            reasons = plan_data.get("decision_reasons", {})
            for key, val in decisions.items():
                logger.info(f"Decisión {key}={val} — {reasons.get(key, 'sin razón')}")

            # Defaults seguros si el LLM no devolvió decisiones
            apply_captions = decisions.get("apply_captions", True)
            apply_grading = decisions.get("apply_color_grading", True)
            apply_zoom = decisions.get("apply_zoom_punch_in", False)
            apply_text_overlays = decisions.get("apply_text_overlays", False)
            apply_broll = decisions.get("apply_broll", False)
            apply_sfx = decisions.get("apply_sfx", False)
            apply_music = decisions.get("apply_background_music", False)
            apply_fade = decisions.get("apply_fade", True)

            words = (transcription or {}).get("words") or []
            highlight_keywords = plan_data.get("highlight_keywords") or []
            caption_style = plan_data.get("caption_style") or {}
            caption_emphasis = plan_data.get("caption_emphasis") or []
            grading_style = plan_data.get("color_grading", "neutral") if apply_grading else "neutral"

            # Paso 8: Captions + grading (70% → 78%)
            stage = source_video
            if apply_captions and words:
                ass_path = workdir / "viral_captions.ass"
                video.generate_viral_captions_ass(
                    words, ass_path,
                    video_width=v_w, video_height=v_h,
                    highlight_keywords=highlight_keywords,
                    caption_style=caption_style,
                    caption_emphasis=caption_emphasis
                )
                graded_path = workdir / "graded.mp4"
                video.apply_color_grading_and_subtitles(
                    stage, ass_path, graded_path,
                    grading_style=grading_style
                )
                stage = graded_path
            elif apply_grading:
                graded_path = workdir / "graded.mp4"
                video.apply_color_grading(stage, graded_path, grading_style=grading_style)
                stage = graded_path
            update_progress(job_id, 78)

            # Paso 9: Zoom punch-in SI el LLM lo decidió (78% → 82%)
            zoom_moments = plan_data.get("zoom_moments", []) if apply_zoom else []
            if apply_zoom and zoom_moments:
                try:
                    zoomed_path = workdir / "zoomed.mp4"
                    video.add_zoom_punch_in(stage, zoomed_path, zoom_moments=zoom_moments)
                    stage = zoomed_path
                except Exception as e:
                    logger.warning(f"zoom falló: {e}")
            update_progress(job_id, 82)

            # Paso 10: Text overlays SI el LLM lo decidió (82% → 86%)
            text_overlays = plan_data.get("text_overlays", []) if apply_text_overlays else []
            for i, ov in enumerate(text_overlays[:2]):
                try:
                    text = (ov.get("text") or "").strip()
                    if not text or len(text) > 30:
                        continue
                    nxt = workdir / f"with_text_{i}.mp4"
                    video.add_text_overlay(
                        stage, nxt,
                        text=text,
                        timestamp=float(ov.get("timestamp", 0)),
                        duration=float(ov.get("duration", 1.5)),
                        font_size=int(v_h * 0.06),
                        text_color="white"
                    )
                    stage = nxt
                except Exception as e:
                    logger.warning(f"text_overlay {i} falló: {e}")
            update_progress(job_id, 86)

            # Paso 11: B-roll DALL-E SI el LLM lo decidió (86% → 90%)
            broll_list = plan_data.get("broll", []) if apply_broll else []
            for i, broll in enumerate(broll_list[:2]):
                try:
                    dalle_prompt = broll.get("dalle_prompt") or broll.get("description", "")
                    if not dalle_prompt:
                        continue
                    logger.info(f"DALL-E B-roll {i+1}")
                    image_url = openai_service.generate_broll_image(dalle_prompt)
                    image_path = workdir / f"broll_{i}.jpg"
                    urllib.request.urlretrieve(image_url, str(image_path))
                    nxt = workdir / f"with_broll_{i}.mp4"
                    video.overlay_image_at_timestamp(
                        stage, image_path, nxt,
                        start_time=float(broll.get("timestamp", 0)),
                        duration=float(broll.get("duration", 2))
                    )
                    stage = nxt
                except Exception as e:
                    logger.warning(f"B-roll {i} falló: {e}")
            update_progress(job_id, 90)

            # Paso 12: SFX SI el LLM lo decidió (90% → 92%)
            sfx_events = []
            if apply_sfx:
                llm_sfx = plan_data.get("sfx_events", [])
                for ev in llm_sfx:
                    sfx_path = _pick_sfx(ev.get("type", "pop"))
                    if sfx_path:
                        sfx_events.append({
                            "path": sfx_path,
                            "timestamp": float(ev.get("timestamp", 0)),
                            "volume": 0.5
                        })
                if sfx_events:
                    try:
                        with_sfx = workdir / "with_sfx.mp4"
                        video.add_multiple_sound_effects(stage, with_sfx, sfx_events)
                        stage = with_sfx
                    except Exception as e:
                        logger.warning(f"SFX falló: {e}")
            update_progress(job_id, 92)

            # Paso 13: Música SI el LLM lo decidió (92% → 94%)
            music_path = None
            if apply_music:
                music_mood = (plan_data.get("music") or {}).get("mood", "chill")
                if music_mood and music_mood.lower() != "none":
                    music_path = _pick_music(music_mood)
                    if music_path:
                        try:
                            with_music = workdir / "with_music.mp4"
                            video.mix_background_music(stage, music_path, with_music, music_volume=0.12)
                            stage = with_music
                        except Exception as e:
                            logger.warning(f"music falló: {e}")
            update_progress(job_id, 94)

            # Paso 14: Fade SI el LLM lo decidió (94% → 96%)
            if apply_fade:
                try:
                    faded = workdir / "faded.mp4"
                    video.add_fade_in_out(stage, faded, fade_duration=0.3)
                    stage = faded
                except Exception as e:
                    logger.warning(f"fade falló: {e}")
            update_progress(job_id, 96)

            # Paso 15: Render final (96% → 98%)
            final_path = workdir / "final.mp4"
            video.upscale_to_resolution(stage, final_path, target=target_resolution)
            update_progress(job_id, 98)

            # Paso 16: Upload (98% → 100%)
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
                    "target_resolution": target_resolution,
                    "applied_effects": {
                        "captions_xl": bool(words),
                        "color_grading": grading_style,
                        "zoom_moments": len(zoom_moments),
                        "text_overlays": len(text_overlays),
                        "broll_images": len(broll_list),
                        "sfx_events": len(sfx_events),
                        "background_music": bool(music_path)
                    }
                }
            })

            logger.success(f"Job {job_id} completado: {output_key}")

    except Exception as e:
        logger.exception(f"Pipeline error en job {job_id}")
        db.update_job(job_id, {"status": "failed", "error_message": str(e)[:500]})
        raise
