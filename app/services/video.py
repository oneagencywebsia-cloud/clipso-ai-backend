"""FFmpeg — Edición y procesamiento de vídeo"""
import ffmpeg
from pathlib import Path
from loguru import logger


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
    font_color: str = "white"
) -> Path:
    """Quema subtítulos en el vídeo (no editables, parte del frame)"""
    video_path = Path(video_path)
    srt_path = Path(srt_path)
    output_path = Path(output_path)

    style = (
        f"FontName=Inter,FontSize={font_size},"
        f"PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,"
        f"BorderStyle=3,Outline=2,Shadow=1,Alignment=2"
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
