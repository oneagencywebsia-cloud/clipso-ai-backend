"""Pipeline de procesamiento — Orquesta IA + FFmpeg"""
import tempfile
import json
import urllib.request
import random
from pathlib import Path
from loguru import logger

from app.services.db import db
from app.services.r2 import r2
from app.services import openai_service, video, motion


ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
SFX_DIR = ASSETS_DIR / "sfx"
MUSIC_DIR = ASSETS_DIR / "music"
AMBIENT_DIR = ASSETS_DIR / "ambient"


def update_progress(job_id: str, progress: int, status: str = "processing"):
    db.update_job(job_id, {"progress": progress, "status": status})


def _pick_sfx(name: str) -> Path | None:
    p = SFX_DIR / f"{name}.mp3"
    return p if p.exists() else None


def _pick_music(track: str) -> Path | None:
    if not track or track.lower() == "none":
        return None
    p = MUSIC_DIR / f"{track}.mp3"
    if p.exists():
        return p
    # fallback: cualquier match parcial
    for c in MUSIC_DIR.glob("*.mp3"):
        if track.lower() in c.stem.lower():
            return c
    return None


def _pick_ambient(track: str) -> Path | None:
    if not track or track.lower() == "none":
        return None
    p = AMBIENT_DIR / f"{track}.mp3"
    return p if p.exists() else None


def _build_auto_sfx_events(
    chunk_starts: list[float],
    zoom_moments: list[dict],
    motion_graphics: list[dict],
    llm_sfx: list[dict],
    duration: float,
    key_moments: list[dict] | None = None,
    keyword_animations: list[dict] | None = None
) -> list[dict]:
    """Construye lista completa de SFX events v4 con keyword_animations:
    - Click suave automático en cada caption chunk (Submagic style)
    - Whoosh automático en cada zoom punch-in (calibrado a scale_target)
    - Pop/sync automático en cada motion graphic (según sfx_sync + importance_score)
    - SFX estratégicos en key_moments (riser buildup + impact)
    - SFX por palabra en keyword_animations (requires_sfx=true)
    - sfx_events tradicionales del LLM como fallback
    """
    events = []
    used_timestamps: set[float] = set()

    def _add(sfx_name: str, ts: float, vol: float, dedup_window: float = 0.15) -> None:
        """Agrega SFX evitando duplicados en ventana de tiempo."""
        if not (0 <= ts <= duration):
            return
        for used_ts in used_timestamps:
            if abs(ts - used_ts) < dedup_window:
                return
        p = _pick_sfx(sfx_name)
        if p:
            events.append({"path": str(p), "timestamp": ts, "volume": vol})
            used_timestamps.add(ts)

    # 1. Auto-clicks en CADA caption chunk (Submagic style)
    click_path = _pick_sfx("click_soft")
    if click_path:
        for ts in chunk_starts:
            if 0 <= ts <= duration:
                events.append({"path": str(click_path), "timestamp": ts, "volume": 0.12})

    # 2. Auto-whoosh en zooms — volumen proporcional al scale_target
    whoosh_path = _pick_sfx("whoosh")
    whoosh_long = _pick_sfx("whoosh_long")
    if whoosh_path:
        for zm in zoom_moments:
            ts = float(zm.get("timestamp", 0))
            scale_t = float(zm.get("scale_target", 105))
            # Más zoom → más volumen y whoosh más largo
            vol = 0.25 + (scale_t - 105) * 0.015  # 105→0.25, 120→0.475
            vol = max(0.25, min(0.65, vol))
            sfx_p = whoosh_long if scale_t >= 118 and whoosh_long else whoosh_path
            if 0 <= ts <= duration:
                events.append({"path": str(sfx_p), "timestamp": ts, "volume": vol})

    # 3. SFX sincronizado a cada motion graphic (importance_score → volumen)
    for mg in motion_graphics:
        sync_type = mg.get("sfx_sync") or "pop"
        importance = float(mg.get("importance_score", 0.7))
        vol = 0.30 + importance * 0.20  # 0.7→0.44, 0.9→0.48, 1.0→0.50
        sync_path = _pick_sfx(sync_type) or _pick_sfx("pop")
        if sync_path:
            ts = float(mg.get("timestamp", 0))
            if 0 <= ts <= duration:
                events.append({"path": str(sync_path), "timestamp": ts, "volume": vol})

    # 4. SFX en keyword_animations donde requires_sfx=true
    for kw in (keyword_animations or []):
        if not kw.get("requires_sfx"):
            continue
        sfx_type = kw.get("sfx_type", "pop")
        importance = float(kw.get("importance_score", 0.7))
        vol = 0.25 + importance * 0.20
        ts = float(kw.get("timestamp", -1))
        if ts >= 0:
            _add(sfx_type, ts, vol)

    # 5. SFX estratégicos del LLM v4 (key_moments con riser + impact)
    if key_moments:
        for moment in key_moments:
            ts = float(moment.get("timestamp", 0))
            if 0 <= ts <= duration:
                lead_time = float(moment.get("lead_time", 0))
                sfx_buildup = moment.get("sfx_buildup")
                if sfx_buildup and lead_time > 0:
                    riser_path = _pick_sfx(sfx_buildup)
                    riser_ts = max(0.0, ts - lead_time)
                    if riser_path:
                        events.append({"path": str(riser_path), "timestamp": riser_ts, "volume": 0.55})

                sfx_impact = moment.get("sfx_impact")
                importance = float(moment.get("importance_score", 0.8))
                impact_vol = 0.50 + importance * 0.20
                if sfx_impact:
                    impact_path = _pick_sfx(sfx_impact)
                    if impact_path:
                        events.append({"path": str(impact_path), "timestamp": ts, "volume": impact_vol})

    # 6. sfx_events del LLM (siempre se aplican, no son exclusivos)
    for ev in llm_sfx:
        sfx_type = ev.get("type", "pop")
        sfx_path = _pick_sfx(sfx_type)
        if sfx_path:
            ts = float(ev.get("timestamp", 0))
            if 0 <= ts <= duration:
                events.append({"path": str(sfx_path), "timestamp": ts, "volume": float(ev.get("volume", 0.5))})

    # Ordenar por timestamp
    events.sort(key=lambda e: e["timestamp"])
    return events


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

            # Defaults AGRESIVOS si el LLM no devolvió decisiones explícitas
            apply_captions = decisions.get("apply_captions", True)
            apply_grading = decisions.get("apply_color_grading", True)
            apply_zoom = decisions.get("apply_zoom_punch_in", True)
            apply_text_overlays = decisions.get("apply_text_overlays", True)
            apply_broll = decisions.get("apply_broll", False)
            apply_sfx = decisions.get("apply_sfx", True)
            apply_music = decisions.get("apply_background_music", True)
            apply_fade = decisions.get("apply_fade", True)

            words = (transcription or {}).get("words") or []
            highlight_keywords = plan_data.get("highlight_keywords") or []
            caption_style = plan_data.get("caption_style") or {}
            caption_emphasis = plan_data.get("caption_emphasis") or []
            motion_graphics_list = plan_data.get("motion_graphics") or []
            text_overlays = plan_data.get("text_overlays") or [] if apply_text_overlays else []
            grading_style = plan_data.get("color_grading", "neutral") if apply_grading else "neutral"

            chunk_starts: list[float] = []

            # Paso 8: Captions + grading + vignette (70% → 78%)
            stage = source_video
            if apply_captions and words:
                ass_path = workdir / "viral_captions.ass"
                _, chunk_starts = video.generate_viral_captions_ass(
                    words, ass_path,
                    video_width=v_w, video_height=v_h,
                    highlight_keywords=highlight_keywords,
                    caption_style=caption_style,
                    caption_emphasis=caption_emphasis,
                    style_preset=caption_style.get("preset")
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

            # === ENFORCEMENT LAYER — Garantiza mínimos aunque el LLM devuelva vacío ===
            duration_video = video.get_video_info(source_video).get("duration", 0)
            key_moments_raw = plan_data.get("key_moments", [])

            zoom_moments = plan_data.get("zoom_moments", []) if apply_zoom else []
            if apply_zoom and not zoom_moments:
                # Auto-generar zooms en key_moments si el LLM no devolvió zoom_moments
                if key_moments_raw:
                    zoom_moments = [
                        {"timestamp": float(km.get("timestamp", 0)), "intensity": "medium"}
                        for km in key_moments_raw[:6]
                    ]
                else:
                    # Fallback: 1 zoom cada 8s
                    zoom_moments = [
                        {"timestamp": t, "intensity": "subtle"}
                        for t in range(2, int(duration_video), 8)
                    ]
                logger.info(f"Enforcement: auto-generados {len(zoom_moments)} zoom_moments")

            if not motion_graphics_list and duration_video > 5:
                # Auto-generar motion graphics mínimos si el LLM devolvió lista vacía
                auto_mg = [{"type": "title_card", "timestamp": 0.5, "duration": 2.0,
                             "params": {"text": plan_data.get("summary", "")[:30] or "WATCH THIS", "color": "#FFFF00", "size_pct": 9}, "sfx_sync": "pop"}]
                if key_moments_raw:
                    for km in key_moments_raw[:3]:
                        ts = float(km.get("timestamp", 5))
                        t = km.get("text") or km.get("type") or "WOW"
                        auto_mg.append({"type": "zoom_shake_text", "timestamp": ts, "duration": 1.5,
                                        "params": {"text": str(t)[:20].upper(), "color": "#FF3333", "size_pct": 10}, "sfx_sync": "impact_high"})
                motion_graphics_list = auto_mg
                logger.info(f"Enforcement: auto-generados {len(motion_graphics_list)} motion graphics")

            # Paso 9: Zoom punch-in (78% → 81%)
            if apply_zoom and zoom_moments:
                try:
                    zoomed_path = workdir / "zoomed.mp4"
                    video.add_zoom_punch_in(stage, zoomed_path, zoom_moments=zoom_moments)
                    stage = zoomed_path
                    logger.info(f"Zooms aplicados: {len(zoom_moments)}")
                except Exception as e:
                    logger.warning(f"zoom falló: {e}")
            update_progress(job_id, 81)

            # Paso 10: Motion graphics (todas en 1 encode) (81% → 84%)
            if motion_graphics_list:
                try:
                    mg_ass = workdir / "motion_graphics.ass"
                    motion.render_motion_graphics_ass(
                        motion_graphics_list, mg_ass,
                        video_width=v_w, video_height=v_h
                    )
                    mg_path = workdir / "with_mg.mp4"
                    mg_ass_escaped = str(mg_ass).replace("\\", "/").replace(":", "\\:")
                    import subprocess as _sp
                    _sp.run([
                        "ffmpeg", "-y", "-i", str(stage),
                        "-vf", f"ass='{mg_ass_escaped}'",
                        "-map", "0:v:0", "-map", "0:a?",
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
                        "-c:a", "copy",
                        str(mg_path)
                    ], capture_output=True, check=True)
                    stage = mg_path
                    logger.info(f"Motion graphics aplicadas: {len(motion_graphics_list)}")
                except Exception as e:
                    logger.warning(f"motion graphics falló: {e}")
            update_progress(job_id, 84)

            # Paso 10b: Text overlays del LLM (84% → 86%) — SIEMPRE aplicados si existen
            if text_overlays:
                try:
                    ov_ass = workdir / "text_overlays.ass"
                    video.generate_text_overlays_ass(
                        text_overlays, ov_ass, video_width=v_w, video_height=v_h
                    )
                    ov_path = workdir / "with_overlays.mp4"
                    ov_ass_escaped = str(ov_ass).replace("\\", "/").replace(":", "\\:")
                    import subprocess as _sp2
                    _sp2.run([
                        "ffmpeg", "-y", "-i", str(stage),
                        "-vf", f"ass='{ov_ass_escaped}'",
                        "-map", "0:v:0", "-map", "0:a?",
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
                        "-c:a", "copy",
                        str(ov_path)
                    ], capture_output=True, check=True)
                    stage = ov_path
                    logger.info(f"Text overlays aplicados: {len(text_overlays)}")
                except Exception as e:
                    logger.warning(f"text overlays falló: {e}")
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

            # Paso 12: SFX events combinados (90% → 92%)
            # Auto: clicks en CADA caption + whoosh en zooms + pop en motion graphics
            # LLM v2: riser buildup + impact en key_moments
            duration_now = video.get_video_info(stage).get("duration", 0)
            key_moments = key_moments_raw if apply_sfx else []
            llm_sfx = plan_data.get("sfx_events", []) if apply_sfx else []
            keyword_animations = plan_data.get("keyword_animations", []) if apply_sfx else []
            all_sfx_events = _build_auto_sfx_events(
                chunk_starts=chunk_starts,
                zoom_moments=zoom_moments,
                motion_graphics=motion_graphics_list,
                llm_sfx=llm_sfx,
                duration=duration_now,
                key_moments=key_moments,
                keyword_animations=keyword_animations
            )
            if all_sfx_events:
                try:
                    with_sfx = workdir / "with_sfx.mp4"
                    video.add_multiple_sound_effects(stage, with_sfx, all_sfx_events)
                    stage = with_sfx
                    logger.info(f"SFX: {len(all_sfx_events)} eventos mezclados")
                except Exception as e:
                    logger.warning(f"SFX falló: {e}")
            update_progress(job_id, 92)

            # Paso 13a: Ambient track (siempre intentar, vol muy bajo)
            ambient_track_name = plan_data.get("ambient_track") or "tiktok_ambient_beat"
            ambient_path = _pick_ambient(ambient_track_name)
            if ambient_path:
                try:
                    with_ambient = workdir / "with_ambient.mp4"
                    video.mix_background_music(stage, ambient_path, with_ambient, music_volume=0.06)
                    stage = with_ambient
                    logger.info(f"Ambient: {ambient_track_name} @ 6% vol")
                except Exception as e:
                    logger.warning(f"ambient falló: {e}")

            # Paso 13b: Música SI el LLM lo decidió (92% → 94%)
            music_path = None
            if apply_music:
                music_obj = plan_data.get("music") or {}
                music_track = music_obj.get("track") or music_obj.get("mood") or ""
                music_vol = float(music_obj.get("volume", 0.10))
                if music_track and music_track.lower() != "none":
                    music_path = _pick_music(music_track)
                    if music_path:
                        try:
                            with_music = workdir / "with_music.mp4"
                            video.mix_background_music(stage, music_path, with_music, music_volume=music_vol)
                            stage = with_music
                            logger.info(f"Music: {music_track} @ {music_vol*100:.0f}% vol")
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
                        "motion_graphics": len(motion_graphics_list),
                        "text_overlays": len(text_overlays),
                        "broll_images": len(broll_list),
                        "sfx_events": len(all_sfx_events),
                        "key_moments": len(key_moments),
                        "background_music": bool(music_path)
                    }
                }
            })

            logger.success(f"Job {job_id} completado: {output_key}")

    except Exception as e:
        logger.exception(f"Pipeline error en job {job_id}")
        db.update_job(job_id, {"status": "failed", "error_message": str(e)[:500]})
        raise
