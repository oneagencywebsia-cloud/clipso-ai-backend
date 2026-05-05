"""OpenAI — Whisper · GPT-4 Vision · GPT-4o Structured Outputs · DALL-E 3"""
from __future__ import annotations

import base64
import uuid
from pathlib import Path
from typing import Annotated, Any, Literal, Union

from loguru import logger
from openai import AsyncOpenAI, OpenAI
from pydantic import BaseModel, Field

from app.core.config import settings

# ── Clients ──────────────────────────────────────────────────────────────────
_sync_client  = OpenAI(api_key=settings.openai_api_key)
_async_client = AsyncOpenAI(api_key=settings.openai_api_key)


# ══════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS — DirectorTimeline v5.0
# Replica exacta de la interfaz TypeScript en app/src/remotion/types/timeline.ts
# ══════════════════════════════════════════════════════════════════════════════

# ── Primitivos ────────────────────────────────────────────────────────────────

AnimationStyle = Literal["pop", "bounce", "slide", "shake", "highlight", "fade"]

SfxType = Literal[
    "click_soft", "pop", "swoosh", "whoosh", "whoosh_long",
    "impact_low", "impact_high", "riser_short", "riser_long",
    "ding", "boom", "notification",
]

ColorGrading  = Literal["cinematico", "vibrante", "minimalista", "oscuro", "neutral"]
CaptionPreset = Literal[
    "tiktok_yellow", "mrbeast_bold", "minimal_clean",
    "neon_cyber", "comic_pop", "elegant_serif", "energetic_orange",
]
MotionGraphicType = Literal[
    "title_card", "text_pop", "lower_third", "counter", "call_out",
    "zoom_shake_text", "highlight_box", "arrow_pointer", "progress_bar",
]
AspectRatio = Literal["9:16", "16:9", "1:1", "4:5"]
Tone        = Literal["energico", "calmado", "informativo", "emotivo", "divertido", "profesional"]
Pace        = Literal["rapido", "medio", "lento"]
SfxTrigger  = Literal["zoom", "overlay", "emphasis", "keyword", "manual"]


class SpringConfig(BaseModel):
    stiffness: float = Field(..., ge=80,  le=500)
    damping:   float = Field(..., ge=8,   le=35)
    mass:      float = Field(..., ge=0.5, le=2.0)


class NormalizedPosition(BaseModel):
    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)


# ── Pista 1: Video ────────────────────────────────────────────────────────────

class ZoomEvent(BaseModel):
    startFrame:     int   = Field(..., ge=0)
    scalePeak:      float = Field(..., ge=1.02, le=1.25)
    framesIn:       int   = Field(..., ge=3,  le=15)
    framesHold:     int   = Field(..., ge=6,  le=30)
    framesOut:      int   = Field(..., ge=3,  le=15)
    importanceScore: int  = Field(..., ge=1,  le=10)


class VideoTrack(BaseModel):
    src:            str
    durationFrames: int
    colorGrading:   ColorGrading
    zoomEvents:     list[ZoomEvent]
    applyJumpCuts:  bool
    aspectRatio:    AspectRatio


# ── Pista 2: Texto / Subtítulos ───────────────────────────────────────────────

class WordToken(BaseModel):
    word:            str
    startFrame:      int
    endFrame:        int
    importanceScore: int            = Field(..., ge=1, le=10)
    animationStyle:  AnimationStyle | None = None
    requiresSfx:     bool
    sfxType:         SfxType | None = None


class CaptionChunk(BaseModel):
    id:              str
    text:            str
    words:           list[WordToken]
    startFrame:      int
    endFrame:        int
    fontSizePct:     float           = Field(..., ge=2.0, le=12.0)
    baseColor:       str
    highlightColor:  str
    animationStyle:  AnimationStyle
    springConfig:    SpringConfig | None = None
    isEmphasis:      bool
    importanceScore: int             = Field(..., ge=1, le=10)
    entryRotation:   float | None    = None


class TextTrack(BaseModel):
    preset:            CaptionPreset
    chunks:            list[CaptionChunk]
    highlightKeywords: list[str]
    verticalPosition:  float = Field(..., ge=0.0, le=1.0)


# ── Pista 3: Overlays (unión discriminada) ────────────────────────────────────

class _BaseOverlay(BaseModel):
    id:              str
    startFrame:      int
    durationFrames:  int
    position:        NormalizedPosition
    animationStyle:  AnimationStyle
    springConfig:    SpringConfig
    importanceScore: int  = Field(..., ge=1, le=10)
    sfxSync:         SfxType | None = None


class MotionGraphicOverlay(_BaseOverlay):
    type:         Literal["motion_graphic"] = "motion_graphic"
    graphicType:  MotionGraphicType
    text:         str
    color:        str
    fontSizePct:  float = Field(..., ge=4.0, le=12.0)
    counterRange: dict[str, Any] | None = None


class BrollImageOverlay(_BaseOverlay):
    type:        Literal["broll_image"] = "broll_image"
    imageUrl:    str
    displayMode: Literal["fullscreen", "pip"]
    opacity:     float = Field(..., ge=0.0, le=1.0)


class IconPopupOverlay(_BaseOverlay):
    type:    Literal["icon_popup"] = "icon_popup"
    iconUrl: str
    sizePct: float = Field(..., ge=10.0, le=40.0)


class TextOverlayItem(_BaseOverlay):
    type:        Literal["text_overlay"] = "text_overlay"
    text:        str
    color:       str
    fontSizePct: float = Field(..., ge=6.0, le=10.0)


class LowerThirdOverlay(_BaseOverlay):
    type:        Literal["lower_third"] = "lower_third"
    title:       str
    subtitle:    str | None = None
    accentColor: str


AnyOverlay = Annotated[
    Union[
        MotionGraphicOverlay,
        BrollImageOverlay,
        IconPopupOverlay,
        TextOverlayItem,
        LowerThirdOverlay,
    ],
    Field(discriminator="type"),
]


class OverlayTrack(BaseModel):
    overlays: list[AnyOverlay]


# ── Pista 4: Audio ────────────────────────────────────────────────────────────

class SfxEvent(BaseModel):
    id:         str
    sfxType:    SfxType
    startFrame: int
    volume:     float   = Field(..., ge=0.0, le=1.0)
    trigger:    SfxTrigger


class MusicTrack(BaseModel):
    trackName:    str | None
    volume:       float = Field(..., ge=0.0, le=1.0)
    fadeInFrames: int
    fadeOutFrames: int


class AmbientTrack(BaseModel):
    trackName: str
    volume:    float = Field(..., ge=0.03, le=0.08)


class AudioTrack(BaseModel):
    sfxEvents: list[SfxEvent]
    music:     MusicTrack
    ambient:   AmbientTrack


# ── Raíz: DirectorTimeline ────────────────────────────────────────────────────

class TimelineMeta(BaseModel):
    title:          str
    tone:           Tone
    pace:           Pace
    summary:        str
    language:       str
    durationFrames: int
    fps:            Literal[30, 60]
    aspectRatio:    AspectRatio


class DirectorTimeline(BaseModel):
    schemaVersion: Literal["5.0"] = "5.0"
    jobId:         str
    meta:          TimelineMeta
    tracks: dict[Literal["video", "text", "overlays", "audio"], Any]

    @property
    def video(self)    -> VideoTrack:    return VideoTrack(**self.tracks["video"])
    @property
    def text(self)     -> TextTrack:     return TextTrack(**self.tracks["text"])
    @property
    def overlays(self) -> OverlayTrack:  return OverlayTrack(**self.tracks["overlays"])
    @property
    def audio(self)    -> AudioTrack:    return AudioTrack(**self.tracks["audio"])


# ── Modelo intermedio que GPT-4o rellena ─────────────────────────────────────
# Separamos VideoTrack/TextTrack/etc. en campos top-level para que el JSON
# schema resultante sea plano y compatible con structured outputs de OpenAI.

class _TracksPayload(BaseModel):
    video:    VideoTrack
    text:     TextTrack
    overlays: OverlayTrack
    audio:    AudioTrack


class DirectorTimelinePayload(BaseModel):
    """Modelo que GPT-4o rellena via structured outputs."""
    schemaVersion: Literal["5.0"] = "5.0"
    jobId:         str
    meta:          TimelineMeta
    tracks:        _TracksPayload


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT — Director IA
# ══════════════════════════════════════════════════════════════════════════════

_DIRECTOR_SYSTEM_PROMPT = """\
Eres CLIPSO Director, el editor de retención extrema más agresivo del mundo (estilo B2B/Hormozi).
Tu único objetivo: transformar una transcripción plana en un DirectorTimeline v5.0 que obligue
al espectador a no apartar los ojos de la pantalla.

═══════════════════════════════════
REGLAS DE DIRECCIÓN — OBLIGATORIAS
═══════════════════════════════════

[VIDEO TRACK — ZOOM PUNCH-INS]
• Genera un ZoomEvent cada 3-5 segundos. Sin excepciones.
• scalePeak 1.15-1.25. framesIn 6, framesHold 12-18, framesOut 6.
• Primer zoom SIEMPRE en los primeros 3s (importanceScore 9-10).
• Zoom en revelaciones/punchlines: scalePeak 1.22-1.25.
• importanceScore del ZoomEvent = importanceScore del momento clave.

[TEXT TRACK — KINETIC CAPTIONS]
• Agrupa palabras en bloques de 1-3 para máxima legibilidad.
• importanceScore 10 + animationStyle "pop" + isEmphasis true en:
  "dinero", "escalar", "IA", "ventas", "secreto", "resultados", "gratis",
  "automatizar", "fácil", "rápido", "millón", "agencia", números con unidad.
• Resto de palabras: importanceScore 3-6, animationStyle "slide".
• Palabras de importanceScore >= 9: requiresSfx true, sfxType "pop" o "ding".
• highlightKeywords: mínimo 5 palabras del texto, las más emocionales.
• verticalPosition: 0.72 para 9:16, 0.80 para 16:9.
• fontSizePct: 7.5 base. isEmphasis chunks → motor aplica ×1.35 automáticamente.
• springConfig para isEmphasis: stiffness 400, damping 10, mass 0.8.
• entryRotation: chunks de énfasis entre -3.0 y 3.0 grados.

[OVERLAY TRACK]
• SIEMPRE un LowerThirdOverlay en frame 0-45 con nombre/canal si hay contexto.
• title_card en los primeros 2s si el vídeo tiene hook claro.
• IconPopupOverlay cuando el speaker menciona una lista o app/herramienta.
• Mínimo 2 overlays en vídeos de cualquier duración.

[AUDIO TRACK — SFX SINCRONIZADOS]
• OBLIGATORIO: un SfxEvent tipo "whoosh" por cada ZoomEvent (mismo startFrame).
• OBLIGATORIO: un SfxEvent tipo "pop" o "ding" por cada WordToken con requiresSfx true.
• SfxEvent tipo "swoosh" en el startFrame de cada LowerThirdOverlay.
• SfxEvent tipo "boom" o "whoosh_long" en los primeros 6 frames del vídeo.
• Volumen: whoosh 0.45-0.55 · pop/ding 0.35-0.50 · impact_high 0.60-0.70.
• music.trackName: "upbeat_energetic" para contenido B2B/agencia. Nunca null.
• ambient.trackName: "tiktok_ambient_beat". volume entre 0.04 y 0.06.

[COHERENCIA TEMPORAL]
• Todos los startFrame <= meta.durationFrames.
• Los CaptionChunks NO se solapan. endFrame de uno = startFrame del siguiente.
• Los SfxEvents van ordenados por startFrame ASC.
• Los ZoomEvents van ordenados por startFrame ASC.
• jobId: UUID v4 generado (ej: "3fa85f64-5717-4562-b3fc-2c963f66afa6").

[RESTRICCIÓN FINAL]
Devuelve EXCLUSIVAMENTE el JSON del DirectorTimeline. Sin texto adicional.
"""


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL — generate_director_timeline
# ══════════════════════════════════════════════════════════════════════════════

async def generate_director_timeline(
    transcription_data: list[dict],
    metadata: dict,
) -> DirectorTimelinePayload:
    """
    Recibe la salida de Whisper (lista de WordTokens con start/end en segundos)
    y los metadatos del vídeo, y devuelve un DirectorTimeline v5.0 validado
    usando OpenAI Structured Outputs (response_format = modelo Pydantic).

    Args:
        transcription_data: lista de dicts con keys "word", "start", "end".
        metadata: dict con keys "fps", "duration_seconds", "total_frames",
                  "aspect_ratio", "channel_name".

    Returns:
        DirectorTimelinePayload validado. Lanza ValidationError si el modelo
        devuelve datos incoherentes.
    """
    fps             = int(metadata.get("fps", 30))
    duration_s      = float(metadata.get("duration_seconds", 0))
    total_frames    = int(metadata.get("total_frames", round(duration_s * fps)))
    aspect_ratio    = metadata.get("aspect_ratio", "9:16")
    channel_name    = metadata.get("channel_name", "")

    # Convierte segundos → frames en los word tokens
    words_with_frames = [
        {
            "word":       w["word"],
            "start":      w["start"],
            "end":        w["end"],
            "startFrame": round(w["start"] * fps),
            "endFrame":   round(w["end"]   * fps),
        }
        for w in transcription_data
    ]

    full_text = " ".join(w["word"] for w in transcription_data)

    user_prompt = (
        f"DATOS DEL VÍDEO:\n"
        f"  canal: {channel_name}\n"
        f"  fps: {fps} | duración: {duration_s:.2f}s | frames: {total_frames}\n"
        f"  aspect_ratio: {aspect_ratio}\n\n"
        f"TRANSCRIPCIÓN COMPLETA:\n{full_text}\n\n"
        f"PALABRAS CON TIMESTAMPS (frames a {fps}fps):\n"
        + "\n".join(
            f"  [{w['startFrame']:>4} → {w['endFrame']:>4}]  {w['word']}"
            for w in words_with_frames
        )
        + f"\n\nGenera el DirectorTimeline v5.0 completo. jobId: {uuid.uuid4()}"
    )

    logger.info(
        f"generate_director_timeline | {len(transcription_data)} palabras | "
        f"{duration_s:.1f}s | {aspect_ratio}"
    )

    response = await _async_client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=[
            {"role": "system",  "content": _DIRECTOR_SYSTEM_PROMPT},
            {"role": "user",    "content": user_prompt},
        ],
        response_format=DirectorTimelinePayload,
        max_tokens=6000,
        temperature=0.4,
    )

    result = response.choices[0].message.parsed
    if result is None:
        raise ValueError(
            "GPT-4o structured output devolvió None. "
            f"Refusal: {response.choices[0].message.refusal}"
        )

    logger.success(
        f"DirectorTimeline generado | jobId={result.jobId} | "
        f"chunks={len(result.tracks.text.chunks)} | "
        f"zooms={len(result.tracks.video.zoomEvents)} | "
        f"sfx={len(result.tracks.audio.sfxEvents)}"
    )
    return result


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIONES EXISTENTES (sin cambios)
# ══════════════════════════════════════════════════════════════════════════════

def transcribe_audio(file_path: str | Path, language: str = "es") -> dict:
    """Whisper — transcribe audio con timestamps por palabra y segmento."""
    file_path = Path(file_path)
    logger.info(f"Whisper transcribiendo: {file_path.name}")

    with open(file_path, "rb") as audio_file:
        transcription = _sync_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language=language,
            response_format="verbose_json",
            timestamp_granularities=["segment", "word"],
        )

    return {
        "text":     transcription.text,
        "language": transcription.language,
        "duration": transcription.duration,
        "segments": [
            seg.model_dump() if hasattr(seg, "model_dump") else seg
            for seg in (transcription.segments or [])
        ],
        "words": [
            w.model_dump() if hasattr(w, "model_dump") else w
            for w in (transcription.words or [])
        ],
    }


def analyze_frames(frame_paths: list[str | Path], prompt: str | None = None) -> dict:
    """GPT-4 Vision — analiza múltiples frames del vídeo."""
    logger.info(f"GPT-4 Vision analizando {len(frame_paths)} frames")

    default_prompt = (
        "Analiza estos frames de un vídeo. Describe: "
        "1) Tema principal 2) Tono emocional 3) Tipo de contenido "
        "4) Sugerencias de animaciones 5) SFX contextuales "
        "6) Si necesita B-roll y de qué tipo. "
        "Responde en JSON con keys: tema, tono, tipo, animaciones, sonidos, broll."
    )

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt or default_prompt}]

    for frame_path in frame_paths:
        with open(frame_path, "rb") as img:
            b64 = base64.b64encode(img.read()).decode()
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })

    response = _sync_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": content}],
        max_tokens=2000,
        response_format={"type": "json_object"},
    )

    return {
        "analysis": response.choices[0].message.content,
        "model":    response.model,
        "usage":    response.usage.model_dump() if response.usage else {},
    }


def generate_production_plan(
    transcription: dict,
    visual_analysis: dict,
    user_preferences: str | None = None,
) -> dict:
    """
    Legacy — genera el Production Plan como JSON string (sin structured outputs).
    Usar generate_director_timeline() para producción nueva.
    """
    logger.warning("generate_production_plan() es legacy. Migra a generate_director_timeline().")

    duration   = transcription.get("duration") or 0
    user_prompt = (
        f"TRANSCRIPCIÓN ({duration:.1f}s):\n"
        f"{transcription.get('text', '')[:3000]}\n\n"
        f"ANÁLISIS VISUAL:\n{visual_analysis.get('analysis', '')[:1500]}\n\n"
        f"PREFERENCIAS: {user_preferences or 'Ninguna'}\n\n"
        "Devuelve JSON con: tone, pace, color_grading, zoom_moments, "
        "motion_graphics, sfx_events, music, caption_style."
    )

    response = _sync_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _DIRECTOR_SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens=5000,
        response_format={"type": "json_object"},
    )

    return {
        "plan":  response.choices[0].message.content,
        "usage": response.usage.model_dump() if response.usage else {},
    }


def generate_broll_image(prompt: str, size: str = "1792x1024") -> str:
    """DALL-E 3 — Genera imagen de B-roll. Devuelve URL temporal."""
    logger.info(f"DALL-E generando: {prompt[:60]}...")

    response = _sync_client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size=size,
        quality="hd",
        n=1,
    )

    return response.data[0].url
