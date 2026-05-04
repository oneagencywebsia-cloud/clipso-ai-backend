"""FFmpeg — Edición y procesamiento de vídeo"""
import ffmpeg
import shutil
import subprocess
import re
from pathlib import Path
from loguru import logger

# Preset para encodes intermedios (archivos temporales)
_TMP_PRESET = "ultrafast"
_TMP_CRF = 26

# Preset solo para el render final (output del usuario)
_FINAL_PRESET = "fast"
_FINAL_CRF = 20


def hex_to_ass_color(hex_color: str) -> str:
    """Convierte color hex (#RRGGBB) a formato ASS (&HBBGGRR&)"""
    hex_color = hex_color.lstrip("#").upper()
    if len(hex_color) == 6:
        r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
        return f"&H{b}{g}{r}&"
    return "&HFFFFFF&"


def extract_audio(video_path: str | Path, output_path: str | Path) -> Path:
    """Extrae el audio de un vídeo (para Whisper)"""
    video_path = Path(video_path)
    output_path = Path(output_path)
    logger.info(f"Extrayendo audio: {video_path.name}")
    (
        ffmpeg
        .input(str(video_path))
        .output(str(output_path), acodec="libmp3lame", ac=1, ar=16000)
        .overwrite_output()
        .run(quiet=True)
    )
    return output_path


def extract_frames(
    video_path: str | Path,
    output_dir: str | Path,
    fps: float = 0.5,
    max_frames: int = 20
) -> list[Path]:
    """Extrae frames cada X segundos para análisis visual"""
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = output_dir / "frame_%04d.jpg"
    logger.info(f"Extrayendo frames @ {fps}fps de {video_path.name}")
    (
        ffmpeg
        .input(str(video_path))
        .output(str(pattern), vf=f"fps={fps},scale=1280:-1", **{"frames:v": max_frames})
        .overwrite_output()
        .run(quiet=True)
    )
    return sorted(output_dir.glob("frame_*.jpg"))


def get_video_info(video_path: str | Path) -> dict:
    """Devuelve metadata del vídeo (duración, resolución, fps, codec)"""
    video_path = Path(video_path)
    probe = ffmpeg.probe(str(video_path))
    video_stream = next((s for s in probe["streams"] if s["codec_type"] == "video"), None)
    audio_stream = next((s for s in probe["streams"] if s["codec_type"] == "audio"), None)
    return {
        "duration": float(probe["format"]["duration"]),
        "size_bytes": int(probe["format"]["size"]),
        "format": probe["format"]["format_name"],
        "video": {
            "codec": video_stream["codec_name"] if video_stream else None,
            "width": video_stream["width"] if video_stream else None,
            "height": video_stream["height"] if video_stream else None,
            "fps": eval(video_stream["r_frame_rate"]) if video_stream else None
        } if video_stream else None,
        "audio": {
            "codec": audio_stream["codec_name"] if audio_stream else None,
            "sample_rate": int(audio_stream["sample_rate"]) if audio_stream else None
        } if audio_stream else None
    }


def burn_subtitles(
    video_path: str | Path,
    srt_path: str | Path,
    output_path: str | Path,
    font_size: int = 28,
    font_color: str = "white",
    position: str = "bottom"
) -> Path:
    """Quema subtítulos SRT en el vídeo"""
    video_path = Path(video_path)
    srt_path = Path(srt_path)
    output_path = Path(output_path)
    position_map = {"bottom": 2, "top": 8, "center": 5}
    alignment = position_map.get(position.lower(), 2)
    ass_color = hex_to_ass_color(font_color)
    style = (
        f"FontName=Inter,FontSize={font_size},"
        f"PrimaryColour={ass_color},OutlineColour=&H000000&,"
        f"BorderStyle=3,Outline=2,Shadow=1,Alignment={alignment}"
    )
    (
        ffmpeg
        .input(str(video_path))
        .output(
            str(output_path),
            vf=f"subtitles={srt_path}:force_style='{style}'",
            vcodec="libx264",
            acodec="copy",
            preset=_TMP_PRESET,
            crf=_TMP_CRF
        )
        .overwrite_output()
        .run(quiet=True)
    )
    return output_path


def upscale_to_resolution(
    video_path: str | Path,
    output_path: str | Path,
    target: str = "1080p"
) -> Path:
    """Render final — preserva aspect ratio + audio."""
    target_heights = {"720p": 720, "1080p": 1080, "4k": 2160}
    target_h = target_heights.get(target.lower(), 1080)

    probe = ffmpeg.probe(str(video_path))
    video_stream = next((s for s in probe["streams"] if s["codec_type"] == "video"), None)
    has_audio = any(s["codec_type"] == "audio" for s in probe["streams"])
    src_w = int(video_stream["width"])
    src_h = int(video_stream["height"])
    is_vertical = src_h > src_w

    if is_vertical:
        new_w = target_h
        scale_filter = f"scale={new_w}:-2:flags=lanczos"
    else:
        scale_filter = f"scale=-2:{target_h}:flags=lanczos"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", scale_filter,
        "-map", "0:v:0",
        "-c:v", "libx264",
        "-preset", _FINAL_PRESET,
        "-crf", str(_FINAL_CRF),
    ]
    if has_audio:
        cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "192k"]
    cmd += [str(output_path)]
    logger.info(f"Render final {target} (audio={'yes' if has_audio else 'no'})")
    subprocess.run(cmd, capture_output=True, check=True)
    return Path(output_path)


def concat_videos(video_paths: list[str | Path], output_path: str | Path) -> Path:
    """Une múltiples vídeos en uno solo"""
    output_path = Path(output_path)
    inputs = [ffmpeg.input(str(p)) for p in video_paths]
    streams = []
    for inp in inputs:
        streams.append(inp.video)
        streams.append(inp.audio)
    joined = ffmpeg.concat(*streams, v=1, a=1).node
    (
        ffmpeg
        .output(joined[0], joined[1], str(output_path), vcodec="libx264", acodec="aac",
                preset=_TMP_PRESET, crf=_TMP_CRF)
        .overwrite_output()
        .run(quiet=True)
    )
    return output_path


def transcription_to_srt(segments: list[dict]) -> str:
    """Convierte segments de Whisper a formato SRT"""
    def format_time(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        ms = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"

    srt_lines = []
    for i, seg in enumerate(segments, 1):
        srt_lines.append(str(i))
        srt_lines.append(f"{format_time(seg['start'])} --> {format_time(seg['end'])}")
        srt_lines.append(seg["text"].strip())
        srt_lines.append("")
    return "\n".join(srt_lines)


def apply_color_grading_and_subtitles(
    video_path: str | Path,
    ass_path: str | Path,
    output_path: str | Path,
    grading_style: str = "neutral"
) -> Path:
    """Combina color grading + captions ASS en un SOLO encode (preserva audio explícitamente)."""
    video_path = Path(video_path)
    ass_path = Path(ass_path)
    output_path = Path(output_path)

    grading_filters = {
        "cinematico": "eq=contrast=1.18:saturation=0.85:brightness=-0.04,vignette=PI/5",
        "vibrante": "eq=contrast=1.12:saturation=1.35,vignette=PI/6",
        "minimalista": "eq=saturation=0.75:brightness=0.04",
        "oscuro": "eq=contrast=1.25:brightness=-0.08:saturation=0.9,vignette=PI/4",
        "warm": "eq=contrast=1.1:saturation=1.15,colorchannelmixer=rr=1.05:gg=1.0:bb=0.92,vignette=PI/6",
        "cold": "eq=contrast=1.1:saturation=1.05,colorchannelmixer=rr=0.92:gg=1.0:bb=1.08,vignette=PI/6",
    }

    ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")
    eq_filter = grading_filters.get(grading_style.lower(), "vignette=PI/7")
    vf = f"{eq_filter},ass='{ass_escaped}'"

    logger.info(f"Encode combinado: grading='{grading_style}' + captions ASS")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", vf,
        "-map", "0:v:0",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", _TMP_PRESET,
        "-crf", str(_TMP_CRF),
        "-c:a", "copy",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def apply_color_grading(
    video_path: str | Path,
    output_path: str | Path,
    grading_style: str = "neutral"
) -> Path:
    """Aplica color grading vía filtro eq de FFmpeg"""
    video_path = Path(video_path)
    output_path = Path(output_path)

    styles = {
        "cinematico": "eq=contrast=1.2:saturation=0.8:brightness=-0.05",
        "vibrante": "eq=contrast=1.1:saturation=1.4",
        "minimalista": "eq=saturation=0.7:brightness=0.05",
        "oscuro": "eq=contrast=1.3:brightness=-0.1:saturation=0.9"
    }

    vf = styles.get(grading_style.lower(), "")
    logger.info(f"Aplicando color grading '{grading_style}'")

    if not vf:
        shutil.copy(str(video_path), str(output_path))
        return output_path

    (
        ffmpeg
        .input(str(video_path))
        .output(
            str(output_path),
            vf=vf,
            vcodec="libx264",
            acodec="copy",
            preset=_TMP_PRESET,
            crf=_TMP_CRF
        )
        .overwrite_output()
        .run(quiet=True)
    )
    return output_path


def overlay_image_at_timestamp(
    video_path: str | Path,
    image_path: str | Path,
    output_path: str | Path,
    start_time: float,
    duration: float,
    fade_duration: float = 0.3
) -> Path:
    """Superpone imagen en timestamp específico (preserva audio)."""
    video_path = Path(video_path)
    image_path = Path(image_path)
    output_path = Path(output_path)
    end_time = start_time + duration
    enable = f"between(t,{start_time},{end_time})"
    logger.info(f"Overlay image @ {start_time}s duration={duration}s")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(image_path),
        "-filter_complex",
        f"[0:v][1:v]overlay=x=(W-w)/2:y=(H-h)/2:enable='{enable}'[v]",
        "-map", "[v]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", _TMP_PRESET,
        "-crf", str(_TMP_CRF),
        "-c:a", "copy",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def add_text_overlay(
    video_path: str | Path,
    output_path: str | Path,
    text: str,
    timestamp: float,
    duration: float,
    font_size: int = 48,
    text_color: str = "white",
    fade_duration: float = 0.3
) -> Path:
    """Añade texto en timestamp específico con fade (preserva audio)."""
    video_path = Path(video_path)
    output_path = Path(output_path)
    start = timestamp
    end = timestamp + duration
    enable = f"between(t,{start},{end})"
    text_escaped = text.replace("'", "\\'").replace(":", "\\:")
    logger.info(f"Texto overlay en {timestamp}s: {text[:30]}")

    vf = (
        f"drawtext=text='{text_escaped}':fontsize={font_size}:fontcolor={text_color}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:enable='{enable}':"
        f"borderw=4:bordercolor=black"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", vf,
        "-map", "0:v:0",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", _TMP_PRESET,
        "-crf", str(_TMP_CRF),
        "-c:a", "copy",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def _hex_to_ass_bgr(hex_color: str) -> str:
    """#RRGGBB → &HBBGGRR& (formato ASS)"""
    h = (hex_color or "").lstrip("#").upper()
    if len(h) != 6:
        return "&H00FFFFFF&"
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}&"


def _ensure_high_contrast(hex_color: str, fallback: str = "#FFFF00") -> str:
    """Si el color es muy claro/desaturado, devuelve el fallback."""
    h = (hex_color or "").lstrip("#")
    if len(h) != 6:
        return fallback
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return fallback
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    saturation = (max(r, g, b) - min(r, g, b)) / 255
    if luminance > 0.85 and saturation < 0.2:
        logger.warning(f"Color {hex_color} bajo contraste (lum={luminance:.2f}) → fallback {fallback}")
        return fallback
    return hex_color


def _position_to_alignment(position: str) -> tuple[int, float]:
    """Devuelve (Alignment ASS, marginV_pct desde el borde correspondiente)"""
    p = (position or "bottom_third").lower()
    if p == "top":
        return 8, 0.10
    if p == "center":
        return 5, 0.0
    if p == "bottom":
        return 2, 0.08
    # bottom_third (default)
    return 2, 0.22


# Presets de estilos de captions (catálogo que el LLM elige)
CAPTION_STYLE_PRESETS = {
    "tiktok_yellow": {
        "fontname": "Impact",
        "base_color": "#FFFFFF",
        "highlight_color": "#FFFF00",
        "outline_color": "#000000",
        "font_size_pct": 7.0,
        "outline": 8,
        "shadow": 2,
        "position": "bottom_third",
        "weight": 1,
    },
    "mrbeast_bold": {
        "fontname": "Arial Black",
        "base_color": "#FFFFFF",
        "highlight_color": "#FF3333",
        "outline_color": "#000000",
        "font_size_pct": 8.0,
        "outline": 10,
        "shadow": 3,
        "position": "bottom_third",
        "weight": 1,
    },
    "minimal_clean": {
        "fontname": "Arial",
        "base_color": "#FFFFFF",
        "highlight_color": "#00FFFF",
        "outline_color": "#000000",
        "font_size_pct": 5.5,
        "outline": 4,
        "shadow": 1,
        "position": "bottom",
        "weight": 1,
    },
    "neon_cyber": {
        "fontname": "Impact",
        "base_color": "#00FFFF",
        "highlight_color": "#FF00FF",
        "outline_color": "#000000",
        "font_size_pct": 7.0,
        "outline": 6,
        "shadow": 4,
        "position": "bottom_third",
        "weight": 1,
    },
    "comic_pop": {
        "fontname": "Impact",
        "base_color": "#FFFFFF",
        "highlight_color": "#FFD700",
        "outline_color": "#FF0000",
        "font_size_pct": 7.5,
        "outline": 8,
        "shadow": 2,
        "position": "bottom_third",
        "weight": 1,
    },
    "elegant_serif": {
        "fontname": "Georgia",
        "base_color": "#F5F5F5",
        "highlight_color": "#D4AF37",
        "outline_color": "#000000",
        "font_size_pct": 6.0,
        "outline": 3,
        "shadow": 2,
        "position": "bottom_third",
        "weight": 0,
    },
    "energetic_orange": {
        "fontname": "Impact",
        "base_color": "#FFFFFF",
        "highlight_color": "#FF6B00",
        "outline_color": "#000000",
        "font_size_pct": 7.5,
        "outline": 8,
        "shadow": 3,
        "position": "bottom_third",
        "weight": 1,
    },
}


def _calc_dynamic_font_size(text: str, video_width: int, base_pct: float, video_height: int) -> int:
    """Reduce el tamaño si el texto es largo para evitar overflow lateral."""
    base = int(video_height * base_pct / 100)
    char_count = max(1, len(text))
    # Ancho disponible: 78% del video (12% margen cada lado, ~2% buffer)
    available_w = video_width * 0.78
    # Heurística: ~0.55 píxel por char en fontes Impact
    max_size = int(available_w / (char_count * 0.55))
    return max(60, min(base, max_size))


def _split_long_chunk(chunk: list[dict], max_chars: int = 14) -> list[list[dict]]:
    """Divide un chunk si su texto unido excede max_chars."""
    text = " ".join((w.get("word") or "").strip() for w in chunk)
    if len(text) <= max_chars or len(chunk) <= 1:
        return [chunk]
    mid = len(chunk) // 2
    return [chunk[:mid], chunk[mid:]]


def generate_viral_captions_ass(
    words: list[dict],
    output_path: str | Path,
    video_width: int = 1080,
    video_height: int = 1920,
    highlight_keywords: list[str] | None = None,
    caption_style: dict | None = None,
    caption_emphasis: list[dict] | None = None,
    style_preset: str | None = None
) -> tuple[Path, list[float]]:
    """Captions virales con estilos predefinidos + custom override.

    Returns (path, chunk_start_timestamps) — los timestamps son útiles para
    sincronizar SFX clicks automáticos.
    """
    output_path = Path(output_path)

    # Resolver estilo: preset > custom > default
    preset_name = (style_preset or (caption_style or {}).get("preset") or "tiktok_yellow").lower()
    preset = CAPTION_STYLE_PRESETS.get(preset_name, CAPTION_STYLE_PRESETS["tiktok_yellow"])

    # Custom puede sobreescribir el preset
    custom = caption_style or {}
    fontname = custom.get("fontname", preset["fontname"])
    base_color_hex = _ensure_high_contrast(custom.get("base_color", preset["base_color"]), "#FFFFFF")
    highlight_color_hex = _ensure_high_contrast(
        custom.get("highlight_color", preset["highlight_color"]),
        "#FFFF00"
    )
    outline_color_hex = custom.get("outline_color", preset["outline_color"])
    base_font_pct = float(custom.get("font_size_pct", preset["font_size_pct"]))
    outline = int(custom.get("outline_thickness", preset["outline"]))
    shadow = int(custom.get("shadow", preset["shadow"]))
    position = custom.get("position", preset["position"])
    weight_bold = 1 if custom.get("font_weight", "bold" if preset["weight"] else "regular") == "bold" else 0

    base_color = _hex_to_ass_bgr(base_color_hex)
    highlight_color = _hex_to_ass_bgr(highlight_color_hex)
    outline_color = _hex_to_ass_bgr(outline_color_hex)
    base_alignment, base_margin_pct = _position_to_alignment(position)
    base_margin_v = int(video_height * base_margin_pct)

    # Margins laterales generosos: 12% del ancho cada lado
    margin_lr = int(video_width * 0.12)

    keywords_set = set()
    for kw in (highlight_keywords or []):
        for w in str(kw).split():
            cleaned = w.strip(".,;:!?¿¡()[]\"'").upper()
            if cleaned:
                keywords_set.add(cleaned)

    emphasis = caption_emphasis or []

    # Header con WrapStyle=0 (smart wrap) — clave para no cortar palabras
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,{fontname},80,{base_color},{base_color},{outline_color},&HA0000000&,{weight_bold},0,0,0,100,100,0,0,1,{outline},{shadow},{base_alignment},{margin_lr},{margin_lr},{base_margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def fmt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    def find_emphasis(timestamp: float) -> dict | None:
        for em in emphasis:
            ts = float(em.get("timestamp", -1))
            dur = float(em.get("duration", 0))
            if ts <= timestamp <= ts + dur:
                return em
        return None

    # Paso 1: agrupar en chunks de 2-3 palabras
    raw_chunks: list[list[dict]] = []
    chunk: list[dict] = []
    for w in words:
        text = (w.get("word") or "").strip()
        if not text:
            continue
        chunk.append(w)
        if len(chunk) >= 3 or text.endswith((".", ",", "!", "?")):
            raw_chunks.append(chunk)
            chunk = []
    if chunk:
        raw_chunks.append(chunk)

    # Paso 2: split chunks largos
    chunks: list[list[dict]] = []
    for c in raw_chunks:
        chunks.extend(_split_long_chunk(c, max_chars=14))

    # Paso 3: generar eventos ASS con tamaño dinámico + animación scale-in
    events = []
    chunk_starts: list[float] = []
    for c in chunks:
        if not c:
            continue
        start = c[0].get("start", 0)
        end = c[-1].get("end", start + 0.5)
        chunk_starts.append(start)
        em = find_emphasis(start)

        # Construir línea con keywords destacados
        parts = []
        full_text_chars = []
        for w in c:
            word_text = (w.get("word") or "").strip().upper()
            word_clean = word_text.strip(".,;:!?¿¡()[]\"'")
            word_escaped = word_text.replace("{", "(").replace("}", ")").replace(",", "")
            full_text_chars.append(word_text)
            if word_clean in keywords_set:
                parts.append(f"{{\\c{highlight_color}}}{word_escaped}{{\\c{base_color}}}")
            else:
                parts.append(word_escaped)

        line_text = " ".join(full_text_chars)
        line = " ".join(parts)

        # Tamaño dinámico según longitud
        dynamic_size = _calc_dynamic_font_size(line_text, video_width, base_font_pct, video_height)

        # Scale-in pop animation: empieza al 80% y crece a 100% en 150ms
        anim = (
            f"\\fad(80,40)"
            f"\\fscx80\\fscy80"
            f"\\t(0,150,\\fscx100\\fscy100)"
            f"\\fs{dynamic_size}"
        )

        if em:
            em_color = _hex_to_ass_bgr(_ensure_high_contrast(
                em.get("color", highlight_color_hex),
                "#FFFF00"
            ))
            em_size_pct = float(em.get("size_pct", base_font_pct + 2))
            em_size = _calc_dynamic_font_size(line_text, video_width, em_size_pct, video_height)
            em_align, em_margin_pct = _position_to_alignment(em.get("position", position))
            anim = (
                f"\\fad(120,80)"
                f"\\fscx70\\fscy70"
                f"\\t(0,200,\\fscx105\\fscy105)"
                f"\\t(200,250,\\fscx100\\fscy100)"
                f"\\c{em_color}"
                f"\\fs{em_size}"
                f"\\an{em_align}"
            )

        line = "{" + anim + "}" + line
        events.append(f"Dialogue: 0,{fmt_time(start)},{fmt_time(end)},Base,,0,0,0,,{line}")

    output_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    logger.info(
        f"ASS '{preset_name}': {len(chunks)} chunks (split={len(chunks)-len(raw_chunks)}), "
        f"{len(emphasis)} emphasis, {len(keywords_set)} keywords, font={fontname}"
    )
    return output_path, chunk_starts


def add_zoom_punch_in(
    video_path: str | Path,
    output_path: str | Path,
    zoom_moments: list[dict] | None = None
) -> Path:
    """Zoom punch-in suave en momentos específicos.

    Usa crop con dimensiones dinámicas. Zoom máximo 1.10x para no destruir el frame.
    Usa subprocess directo con -map para garantizar que el audio se preserve.
    """
    video_path = Path(video_path)
    output_path = Path(output_path)

    if not zoom_moments:
        shutil.copy(str(video_path), str(output_path))
        return output_path

    intensity_map = {"subtle": 1.04, "medium": 1.07, "strong": 1.10}

    probe = ffmpeg.probe(str(video_path))
    vstream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    src_w = int(vstream["width"])
    src_h = int(vstream["height"])

    # Construir expresión de zoom continua: max de todas las ventanas
    parts = []
    for m in zoom_moments[:3]:
        ts = float(m.get("timestamp", 0))
        zoom = intensity_map.get(m.get("intensity", "subtle"), 1.04)
        # Easing: in 0.3s, hold 0.6s, out 0.3s
        parts.append(
            f"if(between(t\\,{ts}\\,{ts+0.3})\\,1+({zoom-1})*(t-{ts})/0.3\\,"
            f"if(between(t\\,{ts+0.3}\\,{ts+0.9})\\,{zoom}\\,"
            f"if(between(t\\,{ts+0.9}\\,{ts+1.2})\\,{zoom}-({zoom-1})*(t-{ts+0.9})/0.3\\,1)))"
        )

    z = parts[0]
    for p in parts[1:]:
        z = f"max({z}\\,{p})"

    # crop con tamaño dinámico, luego scale al original
    vf = f"crop=w='{src_w}/({z})':h='{src_h}/({z})':x='({src_w}-{src_w}/({z}))/2':y='({src_h}-{src_h}/({z}))/2',scale={src_w}:{src_h}"

    logger.info(f"Zoom punch-in: {len(zoom_moments)} momentos (max 1.10x)")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", vf,
        "-map", "0:v:0",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", _TMP_PRESET,
        "-crf", str(_TMP_CRF),
        "-c:a", "copy",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def add_fade_in_out(
    video_path: str | Path,
    output_path: str | Path,
    fade_duration: float = 0.4
) -> Path:
    """Fade in/out (preserva audio explícitamente)."""
    video_path = Path(video_path)
    output_path = Path(output_path)
    probe = ffmpeg.probe(str(video_path))
    duration = float(probe["format"]["duration"])
    fade_out_start = max(0, duration - fade_duration)
    has_audio = any(s["codec_type"] == "audio" for s in probe["streams"])

    vf = f"fade=t=in:st=0:d={fade_duration},fade=t=out:st={fade_out_start}:d={fade_duration}"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", vf,
        "-map", "0:v:0",
        "-c:v", "libx264",
        "-preset", _TMP_PRESET,
        "-crf", str(_TMP_CRF),
    ]
    if has_audio:
        af = f"afade=t=in:st=0:d={fade_duration},afade=t=out:st={fade_out_start}:d={fade_duration}"
        cmd += ["-af", af, "-map", "0:a:0", "-c:a", "aac"]
    cmd += [str(output_path)]
    logger.info(f"Fade in/out {fade_duration}s (audio={'yes' if has_audio else 'no'})")
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def burn_ass_subtitles(
    video_path: str | Path,
    ass_path: str | Path,
    output_path: str | Path
) -> Path:
    """Quema un archivo .ass con todo su styling embebido"""
    video_path = Path(video_path)
    ass_path = Path(ass_path)
    output_path = Path(output_path)
    ass_path_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")
    (
        ffmpeg
        .input(str(video_path))
        .output(
            str(output_path),
            vf=f"ass='{ass_path_escaped}'",
            vcodec="libx264",
            acodec="copy",
            preset=_TMP_PRESET,
            crf=_TMP_CRF
        )
        .overwrite_output()
        .run(quiet=True)
    )
    return output_path


def mix_background_music(
    video_path: str | Path,
    music_path: str | Path,
    output_path: str | Path,
    music_volume: float = 0.15,
    fade_duration: float = 1.0
) -> Path:
    """Mezcla música de fondo con el audio original (música a 15% volumen)."""
    video_path = Path(video_path)
    music_path = Path(music_path)
    output_path = Path(output_path)

    probe = ffmpeg.probe(str(video_path))
    duration = float(probe["format"]["duration"])

    logger.info(f"Mezclando música de fondo @ {music_volume*100:.0f}% volumen")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-stream_loop", "-1", "-i", str(music_path),
        "-filter_complex",
        f"[1:a]volume={music_volume},afade=t=in:st=0:d={fade_duration},"
        f"afade=t=out:st={duration-fade_duration}:d={fade_duration},atrim=duration={duration}[bg];"
        f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def add_sound_effect(
    video_path: str | Path,
    sfx_path: str | Path,
    output_path: str | Path,
    timestamp: float,
    volume: float = 0.7
) -> Path:
    """Inserta un sound effect en un timestamp específico."""
    video_path = Path(video_path)
    sfx_path = Path(sfx_path)
    output_path = Path(output_path)

    logger.info(f"Insertando SFX {sfx_path.name} @ {timestamp}s")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(sfx_path),
        "-filter_complex",
        f"[1:a]volume={volume},adelay={int(timestamp*1000)}|{int(timestamp*1000)}[sfx];"
        f"[0:a][sfx]amix=inputs=2:duration=first[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def add_multiple_sound_effects(
    video_path: str | Path,
    output_path: str | Path,
    sfx_events: list[dict]
) -> Path:
    """Inserta múltiples SFX en un solo encode. sfx_events: [{path, timestamp, volume}]"""
    video_path = Path(video_path)
    output_path = Path(output_path)

    if not sfx_events:
        shutil.copy(str(video_path), str(output_path))
        return output_path

    inputs = ["-i", str(video_path)]
    for ev in sfx_events:
        inputs += ["-i", str(ev["path"])]

    filter_parts = []
    mix_inputs = ["[0:a]"]
    for i, ev in enumerate(sfx_events, start=1):
        ts_ms = int(float(ev.get("timestamp", 0)) * 1000)
        vol = ev.get("volume", 0.7)
        filter_parts.append(f"[{i}:a]volume={vol},adelay={ts_ms}|{ts_ms}[s{i}]")
        mix_inputs.append(f"[s{i}]")

    filter_parts.append(
        f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0[a]"
    )

    logger.info(f"Mezclando {len(sfx_events)} SFX en un solo encode")

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filter_parts),
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def cut_silences(
    video_path: str | Path,
    output_path: str | Path,
    min_silence_duration: float = 0.7,
    silence_threshold_db: int = -30
) -> Path:
    """Detecta y elimina silencios largos del video (jump cuts)."""
    video_path = Path(video_path)
    output_path = Path(output_path)
    logger.info(f"Detectando silencios > {min_silence_duration}s en {video_path.name}")

    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-af", f"silencedetect=noise={silence_threshold_db}dB:d={min_silence_duration}",
        "-f", "null", "-"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    raw = result.stderr

    silence_starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", raw)]
    silence_ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", raw)]

    probe = ffmpeg.probe(str(video_path))
    total_duration = float(probe["format"]["duration"])

    if not silence_starts:
        logger.info("No se detectaron silencios — copiando video tal cual")
        shutil.copy(str(video_path), str(output_path))
        return output_path

    keep_segments = []
    cursor = 0.0
    for s_start, s_end in zip(silence_starts, silence_ends):
        if s_start > cursor:
            keep_segments.append((cursor, s_start))
        cursor = s_end
    if cursor < total_duration:
        keep_segments.append((cursor, total_duration))

    keep_segments = [(s, e) for s, e in keep_segments if e - s > 0.2]

    if not keep_segments:
        logger.warning("No quedan segmentos válidos tras corte — copiando original")
        shutil.copy(str(video_path), str(output_path))
        return output_path

    logger.info(f"Cortando {len(silence_starts)} silencios, manteniendo {len(keep_segments)} segmentos")

    select_v = "+".join(f"between(t,{s},{e})" for s, e in keep_segments)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"select='{select_v}',setpts=N/FRAME_RATE/TB",
        "-af", f"aselect='{select_v}',asetpts=N/SR/TB",
        "-map", "0:v:0",
        "-map", "0:a:0",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", _TMP_PRESET,
        "-crf", str(_TMP_CRF),
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path
