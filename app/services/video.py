"""FFmpeg — Edición y procesamiento de vídeo"""
import ffmpeg
import shutil
import urllib.request
from pathlib import Path
from loguru import logger


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

    video_stream = next(
        (s for s in probe["streams"] if s["codec_type"] == "video"), None
    )
    audio_stream = next(
        (s for s in probe["streams"] if s["codec_type"] == "audio"), None
    )

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
    """Quema subtítulos en el vídeo (no editables, parte del frame)"""
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
            preset="medium",
            crf=20
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
    """Re-renderiza preservando el aspect ratio original (vertical/horizontal)"""
    target_heights = {"720p": 720, "1080p": 1080, "4k": 2160}
    target_h = target_heights.get(target.lower(), 1080)

    probe = ffmpeg.probe(str(video_path))
    video_stream = next((s for s in probe["streams"] if s["codec_type"] == "video"), None)
    src_w = int(video_stream["width"])
    src_h = int(video_stream["height"])
    is_vertical = src_h > src_w

    if is_vertical:
        # Vertical: la dimensión menor es width, la mayor es height
        new_h = target_h * 16 // 9 if src_h / src_w >= 16 / 9 else target_h
        new_w = target_h
        scale_filter = f"scale={new_w}:-2:flags=lanczos"
    else:
        scale_filter = f"scale=-2:{target_h}:flags=lanczos"

    (
        ffmpeg
        .input(str(video_path))
        .output(
            str(output_path),
            vf=scale_filter,
            vcodec="libx264",
            acodec="aac",
            preset="medium",
            crf=18
        )
        .overwrite_output()
        .run(quiet=True)
    )
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
        .output(joined[0], joined[1], str(output_path), vcodec="libx264", acodec="aac")
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
    logger.info(f"Aplicando color grading '{grading_style}' a {video_path.name}")

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
            acodec="aac",
            preset="medium",
            crf=18
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
    """Superpone imagen en timestamp específico con fade in/out"""
    video_path = Path(video_path)
    image_path = Path(image_path)
    output_path = Path(output_path)

    logger.info(f"Overlay image @ {start_time}s duration={duration}s de {image_path.name}")

    end_time = start_time + duration
    enable = f"between(t,{start_time},{end_time})"

    (
        ffmpeg
        .input(str(video_path))
        .input(str(image_path))
        .filter(
            "overlay",
            x="(W-w)/2",
            y="(H-h)/2",
            enable=enable
        )
        .output(
            str(output_path),
            vcodec="libx264",
            acodec="aac",
            preset="medium",
            crf=18
        )
        .overwrite_output()
        .run(quiet=True)
    )
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
    """Añade texto animado con fade in/out en timestamp específico"""
    video_path = Path(video_path)
    output_path = Path(output_path)

    logger.info(f"Añadiendo texto en {timestamp}s: {text[:30]}...")

    start = timestamp
    end = timestamp + duration
    fade_end = min(start + fade_duration, end)

    ass_color = hex_to_ass_color(text_color)
    fontcolor_rgb = f"fontcolor={text_color}:fontsize={font_size}"

    enable_fade = f"between(t,{start},{fade_end})*({fade_duration}/(t-{start}+0.0001)) + between(t,{fade_end},{end})"

    text_escaped = text.replace("'", "\\'")

    (
        ffmpeg
        .input(str(video_path))
        .drawtext(
            text=text_escaped,
            fontsize=font_size,
            fontcolor=text_color,
            x="(w-text_w)/2",
            y="(h-text_h)/2",
            enable=enable_fade
        )
        .output(
            str(output_path),
            vcodec="libx264",
            acodec="aac",
            preset="medium",
            crf=18
        )
        .overwrite_output()
        .run(quiet=True)
    )
    return output_path


def generate_viral_captions_ass(
    words: list[dict],
    output_path: str | Path,
    video_width: int = 1080,
    video_height: int = 1920,
    highlight_color: str = "#FFFF00",
    base_color: str = "#FFFFFF",
    font_size: int = 90
) -> Path:
    """Genera archivo .ass con captions estilo viral (palabra por palabra, una palabra grande centrada).

    Cada palabra es un evento independiente que aparece centrada en pantalla
    durante su duración exacta (timestamps de Whisper).
    """
    output_path = Path(output_path)

    primary = hex_to_ass_color(highlight_color)
    base = hex_to_ass_color(base_color)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Viral,Impact,{font_size},{primary},{base},&H000000&,&H80000000&,1,0,0,0,100,100,0,0,1,6,2,5,40,40,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def fmt_time(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}:{minutes:02d}:{secs:05.2f}"

    events = []
    for w in words:
        start = w.get("start", 0)
        end = w.get("end", start + 0.3)
        text = (w.get("word") or "").strip().upper()
        if not text:
            continue
        text_escaped = text.replace("{", "(").replace("}", ")").replace(",", "")
        events.append(
            f"Dialogue: 0,{fmt_time(start)},{fmt_time(end)},Viral,,0,0,0,,{text_escaped}"
        )

    output_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    logger.info(f"Generado ASS viral captions: {len(events)} palabras → {output_path.name}")
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
            preset="medium",
            crf=20
        )
        .overwrite_output()
        .run(quiet=True)
    )
    return output_path


def cut_silences(
    video_path: str | Path,
    output_path: str | Path,
    min_silence_duration: float = 0.7,
    silence_threshold_db: int = -30
) -> Path:
    """Detecta y elimina silencios largos del video (jump cuts).

    Usa silencedetect para encontrar silencios > min_silence_duration,
    luego corta y concatena los segmentos hablados.
    """
    import subprocess
    import re

    video_path = Path(video_path)
    output_path = Path(output_path)

    logger.info(f"Detectando silencios > {min_silence_duration}s en {video_path.name}")

    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-af", f"silencedetect=noise={silence_threshold_db}dB:d={min_silence_duration}",
        "-f", "null", "-"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stderr

    silence_starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", output)]
    silence_ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", output)]

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
    select_a = select_v

    (
        ffmpeg
        .input(str(video_path))
        .output(
            str(output_path),
            vf=f"select='{select_v}',setpts=N/FRAME_RATE/TB",
            af=f"aselect='{select_a}',asetpts=N/SR/TB",
            vcodec="libx264",
            acodec="aac",
            preset="medium",
            crf=18
        )
        .overwrite_output()
        .run(quiet=True)
    )
    return output_path
