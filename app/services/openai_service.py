"""OpenAI — Whisper, GPT-4 Vision, DALL-E 3"""
import base64
from pathlib import Path
from typing import Any
from openai import OpenAI
from loguru import logger

from app.core.config import settings

client = OpenAI(api_key=settings.openai_api_key)


def transcribe_audio(file_path: str | Path, language: str = "es") -> dict:
    """Whisper — transcribe audio con timestamps"""
    file_path = Path(file_path)
    logger.info(f"Whisper transcribiendo: {file_path.name}")

    with open(file_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language=language,
            response_format="verbose_json",
            timestamp_granularities=["segment", "word"]
        )

    return {
        "text": transcription.text,
        "language": transcription.language,
        "duration": transcription.duration,
        "segments": [seg.model_dump() if hasattr(seg, "model_dump") else seg for seg in (transcription.segments or [])],
        "words": [w.model_dump() if hasattr(w, "model_dump") else w for w in (transcription.words or [])]
    }


def analyze_frames(frame_paths: list[str | Path], prompt: str | None = None) -> dict:
    """GPT-4 Vision — analiza múltiples frames del vídeo"""
    logger.info(f"GPT-4 Vision analizando {len(frame_paths)} frames")

    default_prompt = (
        "Analiza estos frames de un vídeo. Describe: "
        "1) Tema principal del vídeo "
        "2) Tono emocional (alegre, serio, dinámico, calmado) "
        "3) Tipo de contenido (tutorial, vlog, presentación, etc.) "
        "4) Sugerencias de animaciones que encajarían "
        "5) Sugerencias de efectos de sonido contextuales "
        "6) Si necesita B-roll y de qué tipo. "
        "Responde en JSON con keys: tema, tono, tipo, animaciones, sonidos, broll."
    )

    content: list[dict[str, Any]] = [
        {"type": "text", "text": prompt or default_prompt}
    ]

    for frame_path in frame_paths:
        with open(frame_path, "rb") as img:
            b64 = base64.b64encode(img.read()).decode()
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
        })

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": content}],
        max_tokens=2000,
        response_format={"type": "json_object"}
    )

    return {
        "analysis": response.choices[0].message.content,
        "model": response.model,
        "usage": response.usage.model_dump() if response.usage else {}
    }


def generate_production_plan(
    transcription: dict,
    visual_analysis: dict,
    user_preferences: str | None = None
) -> dict:
    """GPT-4 — Genera el Production Plan con animaciones, subs, efectos, b-roll"""
    logger.info("Generando Production Plan con GPT-4")

    system_prompt = (
        "Eres un editor de vídeo profesional con 15 años de experiencia. "
        "Generas planes de edición precisos y creativos respetando SIEMPRE el mensaje original. "
        "NUNCA distorsionas el contenido. Solo añades elementos que potencian el mensaje. "
        "Devuelves SIEMPRE JSON válido con la estructura solicitada."
    )

    user_prompt = f"""
Genera un plan de producción detallado para este vídeo.

TRANSCRIPCIÓN:
{transcription.get('text', '')[:3000]}

ANÁLISIS VISUAL:
{visual_analysis.get('analysis', '')[:1500]}

PREFERENCIAS DEL USUARIO:
{user_preferences or 'Ninguna específica'}

Devuelve un JSON con esta estructura:
{{
  "summary": "resumen del vídeo en 1 frase",
  "style": "estilo recomendado (dinámico, minimalista, corporativo, etc.)",
  "color_grading": "tono de color (cinematográfico cálido, frío profesional, vibrante, etc.)",
  "subtitles": {{
    "style": "estilo (impactante, minimalista, neón, etc.)",
    "position": "posición en pantalla",
    "color": "color principal en hex"
  }},
  "animations": [
    {{
      "timestamp": 5.2,
      "duration": 1.5,
      "type": "tipo de animación",
      "description": "qué animación añadir y por qué"
    }}
  ],
  "sound_effects": [
    {{
      "timestamp": 3.0,
      "type": "tipo de efecto",
      "description": "qué efecto añadir"
    }}
  ],
  "broll": [
    {{
      "timestamp": 10.0,
      "duration": 3.0,
      "description": "qué imagen/vídeo complementario añadir",
      "dalle_prompt": "prompt para DALL-E si hay que generarlo"
    }}
  ],
  "music": {{
    "mood": "mood de la música",
    "intensity": "intensidad (baja, media, alta, dinámica)"
  }}
}}
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        max_tokens=3000,
        response_format={"type": "json_object"}
    )

    return {
        "plan": response.choices[0].message.content,
        "usage": response.usage.model_dump() if response.usage else {}
    }


def generate_broll_image(prompt: str, size: str = "1792x1024") -> str:
    """DALL-E 3 — Genera imagen de B-roll"""
    logger.info(f"DALL-E generando: {prompt[:60]}...")

    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size=size,
        quality="hd",
        n=1
    )

    return response.data[0].url
