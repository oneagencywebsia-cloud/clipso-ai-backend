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

    duration = transcription.get('duration') or 0
    user_prompt = f"""
Genera un plan de edición VIRAL para este vídeo. Tu objetivo: que el espectador no pueda parar de mirar.

TRANSCRIPCIÓN ({duration:.1f}s):
{transcription.get('text', '')[:3000]}

ANÁLISIS VISUAL:
{visual_analysis.get('analysis', '')[:1500]}

PREFERENCIAS DEL USUARIO:
{user_preferences or 'Ninguna específica'}

CATÁLOGO DE RECURSOS DISPONIBLES (úsalos):

📝 ESTILOS DE CAPTIONS (elige UNO según tono):
  - "tiktok_yellow": blanco + amarillo, Impact, viral clásico
  - "mrbeast_bold": blanco + rojo, Arial Black, contenido dinámico
  - "minimal_clean": blanco + cyan, Arial fino, profesional/calmado
  - "neon_cyber": cyan + magenta, Impact, tech/gaming
  - "comic_pop": blanco + dorado, outline rojo, comedia/divertido
  - "elegant_serif": grisáceo + oro, Georgia, lujo/elegante
  - "energetic_orange": blanco + naranja, fitness/motivación

🎵 SFX DISPONIBLES (úsalos en sfx_events):
  - "whoosh", "whoosh_long" → transiciones, zooms
  - "click_soft" → automático en cada caption (no listar)
  - "pop" → text overlays, motion graphics aparecen
  - "ding" → checkpoint, completado
  - "riser_short" (2s buildup), "riser_long" (4s) → ANTES de momentos clave
  - "impact_low" → punchline pesado / beat drop
  - "impact_high" → énfasis fuerte
  - "swoosh" → transiciones suaves
  - "boom" → apertura dramática
  - "notification" → estilo iOS/social

🎬 MOTION GRAPHICS DISPONIBLES (úsalos en motion_graphics):
  - "title_card": texto grande centrado con scale-in (intro o cambio de tema)
  - "text_pop": texto que rebota en posición específica (énfasis)
  - "lower_third": barra inferior con título+subtítulo (presentación de persona/lugar)
  - "counter": número animado de A→B (estadísticas)
  - "call_out": flecha + texto apuntando a algo (tutoriales)
  - "zoom_shake_text": texto con scale-shake intenso (PUNCHLINE)

🎼 MÚSICA POR MOOD:
  - "chill_lofi", "epic_cinematic", "upbeat_energetic", "corporate_clean", "tech_modern", "none"

🌫️ AMBIENT VIRAL (siempre se aplica subtle):
  - Auto-seleccionado según tono: tiktok_ambient_beat | cinematic_drone | asmr_room_tone | synth_pad_ethereal | subtle_pulse

JSON con esta estructura:

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
    "preset": "uno de los 7 estilos disponibles",
    "reason": "por qué este preset encaja con el tono del vídeo"
  }},

  "motion_graphics": [
    {{
      "type": "title_card | text_pop | lower_third | counter | call_out | zoom_shake_text",
      "timestamp": 3.0,
      "duration": 2.0,
      "params": {{"text": "TEXTO CORTO", "color": "#FFFF00", "size_pct": 8}},
      "sfx_sync": "pop | impact_high | impact_low | ding",
      "reason": "..."
    }}
  ],

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
      "type": "whoosh | whoosh_long | pop | ding | riser_short | riser_long | impact_low | impact_high | swoosh | boom | notification",
      "volume": 0.5,
      "reason": "..."
    }}
  ],

  "music": {{"track": "chill_lofi | epic_cinematic | upbeat_energetic | corporate_clean | tech_modern | none", "volume": 0.10}},

  "ambient_track": "tiktok_ambient_beat | cinematic_drone | asmr_room_tone | synth_pad_ethereal | subtle_pulse | none"
}}

REGLAS ESTRATÉGICAS (OBLIGATORIAS):

1. CAPTIONS: SIEMPRE apply_captions=true si hay habla. Elige preset según tono.

2. MOTION GRAPHICS — sé GENEROSO:
   - Vídeo > 10s: MÍNIMO 1 motion graphic
   - Vídeo > 20s: MÍNIMO 2 motion graphics
   - Vídeo > 30s: MÍNIMO 3 motion graphics + considerar 1 B-roll
   - Cada motion graphic DEBE tener sfx_sync para sonido sincronizado
   - title_card al inicio si hay un concepto fuerte
   - zoom_shake_text en punchlines/revelaciones
   - call_out para tutoriales
   - counter cuando se mencionan números/estadísticas

3. SFX EVENTS — SIEMPRE incluye:
   - 1 sfx al inicio (whoosh/boom según tono)
   - 1 riser + 1 impact en CADA momento clave del mensaje (revelación, dato, CTA)
   - Mínimo 1 cada 8 segundos
   - El click_soft en captions es AUTOMÁTICO (no lo listes)

4. ZOOM PUNCH-INS:
   - SIEMPRE apply_zoom_punch_in=true salvo en vídeos muy calmados
   - Mínimo 1 zoom cada 10 segundos
   - intensity: subtle (default), medium (énfasis), strong (revelación)

5. MÚSICA + AMBIENT:
   - ambient_track: SIEMPRE elige uno (no "none") — da textura premium imperceptible
   - music.track: solo si encaja con el tono
   - Vlog íntimo → ambient_track="asmr_room_tone", music="none"
   - Tutorial → ambient_track="subtle_pulse", music="corporate_clean"
   - Comedy/hype → ambient_track="tiktok_ambient_beat", music="upbeat_energetic"
   - Storytelling → ambient_track="cinematic_drone", music="epic_cinematic"

6. CAPTION_EMPHASIS: usa para 1-3 momentos clave (climax, punchline, CTA).

7. text_overlays: 1-3 palabras MAYÚSCULAS, NUNCA descripciones.

8. highlight_keywords: deben aparecer en la transcripción.

9. NO seas conservador. SIEMPRE inclínate por aplicar el efecto si aporta dinamismo.
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        max_tokens=4000,
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
