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
        "Eres un editor de vídeo profesional con 15 años de experiencia editando contenido viral "
        "para Instagram Reels, TikTok y YouTube Shorts. "
        "Tu trabajo es analizar CADA vídeo individualmente y decidir ESTRATÉGICAMENTE qué "
        "elementos de edición aportan valor real. NO aplicas efectos por defecto: cada decisión "
        "se justifica según el contenido, tono, ritmo y mensaje del vídeo. "
        "Un vídeo calmado no necesita zoom agresivo; un vídeo informativo puede no necesitar B-roll; "
        "un vlog íntimo no necesita música de fondo. Respeta SIEMPRE el mensaje original. "
        "Devuelves SIEMPRE JSON válido."
    )

    user_prompt = f"""
Genera un plan de producción detallado para este vídeo.

TRANSCRIPCIÓN:
{transcription.get('text', '')[:3000]}

ANÁLISIS VISUAL:
{visual_analysis.get('analysis', '')[:1500]}

PREFERENCIAS DEL USUARIO:
{user_preferences or 'Ninguna específica'}

Analiza el vídeo COMPLETO y decide qué efectos aportan valor. NO apliques todo por defecto. JSON con esta estructura:

{{
  "summary": "resumen 1 frase",
  "tone": "uno de: energico | calmado | informativo | emotivo | divertido | profesional",
  "pace": "uno de: rapido | medio | lento",

  "decisions": {{
    "apply_jump_cuts": true,
    "apply_captions": true,
    "apply_color_grading": true,
    "apply_zoom_punch_in": true,
    "apply_text_overlays": true,
    "apply_broll": false,
    "apply_sfx": true,
    "apply_background_music": false,
    "apply_fade": true
  }},
  "decision_reasons": {{
    "apply_jump_cuts": "explica por qué SÍ o NO según el ritmo del speaker",
    "apply_color_grading": "explica por qué este estilo encaja con el tono",
    "apply_zoom_punch_in": "explica por qué SÍ o NO según el dinamismo",
    "apply_text_overlays": "explica por qué SÍ o NO",
    "apply_broll": "explica si el contenido se beneficiaría de imágenes externas",
    "apply_sfx": "explica si los SFX encajan con el tono",
    "apply_background_music": "explica por qué SÍ o NO (un vlog íntimo puede no necesitarla)",
    "apply_fade": "casi siempre SÍ"
  }},

  "color_grading": "uno de: cinematico | vibrante | minimalista | oscuro | neutral",

  "caption_style": {{
    "base_color": "#FFFFFF",
    "highlight_color": "#FFFF00",
    "font_size_pct": 7.5,
    "position": "uno de: top | center | bottom_third | bottom",
    "outline_thickness": 8,
    "font_weight": "bold | regular",
    "reason": "por qué este estilo encaja con el tono del vídeo"
  }},

  "caption_emphasis": [
    {{
      "timestamp": 5.0,
      "duration": 1.0,
      "color": "#FF3333",
      "size_pct": 11,
      "position": "center",
      "reason": "punto culminante del mensaje"
    }}
  ],

  "highlight_keywords": ["palabras", "CLAVE", "del", "texto"],

  "zoom_moments": [
    {{"timestamp": 1.5, "intensity": "subtle | medium | strong", "reason": "..."}}
  ],

  "text_overlays": [
    {{
      "timestamp": 5.2,
      "duration": 1.5,
      "text": "TEXTO 1-3 PALABRAS MAYÚSCULAS",
      "position": "top | center | bottom",
      "reason": "..."
    }}
  ],

  "broll": [
    {{
      "timestamp": 10.0,
      "duration": 3.0,
      "description": "...",
      "dalle_prompt": "prompt en inglés DALL-E 3",
      "reason": "..."
    }}
  ],

  "sfx_events": [
    {{
      "timestamp": 0.1,
      "type": "whoosh | pop | ding | impact",
      "reason": "..."
    }}
  ],

  "music": {{"mood": "chill | energico | epic | none", "intensity": "baja | media | alta"}}
}}

REGLAS DE ESTILO DE CAPTIONS (cada decisión basada en tono/contexto):
- `caption_style.base_color`: blanco para alto contraste o color de marca si encaja.
- `caption_style.highlight_color`: amarillo vivo (#FFFF00) clásico viral, o color de marca/tono.
- `caption_style.font_size_pct`: 6.5-9.0 (% altura). Mayor para vídeos energéticos, menor para informativos.
- `caption_style.position`: bottom_third (estándar), center solo si no tapa al sujeto, top para títulos.
- `caption_emphasis`: SOLO para 1-3 momentos clave del mensaje (climax, punchline, CTA).

REGLAS ESTRATÉGICAS:
1. `decisions.*` son OBLIGATORIAS — decide cada una basándote en el contenido real.
2. NO listes elementos en zoom_moments/text_overlays/broll/sfx_events si su `apply_*` es false.
3. `text_overlays[].text` SIEMPRE 1-3 palabras MAYÚSCULAS, NUNCA una descripción.
4. Si tono es CALMADO/ÍNTIMO → considera apply_zoom_punch_in=false, apply_sfx=false, apply_background_music=false.
5. Si tono es ENERGICO/DIVERTIDO → SFX y zoom encajan bien.
6. Si el vídeo es INFORMATIVO/TUTORIAL → text_overlays y B-roll suelen ayudar.
7. B-roll solo si NO se ve al sujeto y el tema se beneficia de imagen externa.
8. `highlight_keywords` deben aparecer en la transcripción real.
9. Cada decisión TIENE que estar justificada en `decision_reasons`.
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
