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
  - "highlight_box": rectángulo pulsante para destacar elementos
  - "arrow_pointer": flecha animada apuntando a ubicación
  - "progress_bar": barra de progreso animada (para tutoriales/procesos)
  - "glitch_transition": efecto glitch RGB-split (transiciones)

🎼 MÚSICA POR MOOD:
  - "chill_lofi", "epic_cinematic", "upbeat_energetic", "corporate_clean", "tech_modern", "none"

🌫️ AMBIENT VIRAL (siempre se aplica subtle):
  - Auto-seleccionado según tono: tiktok_ambient_beat | cinematic_drone | asmr_room_tone | synth_pad_ethereal | subtle_pulse

JSON con esta estructura:

{{
  "summary": "resumen 1 frase",
  "video_type": "talking-head | tutorial | vlog | demo | comedy | story",
  "tone": "uno de: energico | calmado | informativo | emotivo | divertido | profesional",
  "pace": "uno de: rapido | medio | lento",

  "key_moments": [
    {{
      "timestamp": 5.2,
      "type": "revelacion | punchline | enfasis | cta | hook | transicion",
      "lead_time": 2.0,
      "sfx_buildup": "riser_short | riser_long",
      "sfx_impact": "impact_high | impact_low | boom | ding",
      "visual": "zoom_punch | motion_graphic | caption_emphasis",
      "text": "TEXTO CORTO OPCIONAL",
      "reason": "por qué este es un momento clave"
    }}
  ],

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

REGLAS ESTRATÉGICAS v2 (OBLIGATORIAS — SIN EXCEPCIONES):

1. KEY_MOMENTS — MINIMO GARANTIZADO:
   - Vídeo < 10s: MÍNIMO 1 key_moment
   - Vídeo 10-20s: MÍNIMO 2 key_moments (1 cada 8s)
   - Vídeo 20-30s: MÍNIMO 3 key_moments (1 cada 8s)
   - Vídeo > 30s: MÍNIMO 4-5 key_moments (1 cada 8s, detecta revelaciones, datos, CTAs)

2. CAPTIONS: apply_captions SIEMPRE TRUE si hay habla.

3. MOTION GRAPHICS — AGRESIVO:
   - Vídeo > 10s: MÍNIMO 1 motion graphic
   - Vídeo > 20s: MÍNIMO 2 motion graphics
   - Vídeo > 30s: MÍNIMO 3-4 motion graphics
   - TIPOS: title_card (inicio), zoom_shake_text (punchlines), counter (números), lower_third (presentaciones)
   - CADA motion graphic debe tener parámetros exactos (no genéricos)

4. SFX EVENTS — INYECCIÓN MASIVA:
   - SIEMPRE 1 sfx explosivo al inicio (boom | whoosh_long)
   - CADA key_moment: 1 riser (buildup) + 1 impact exacto en el momento
   - Mínimo 1 SFX cada 5-8 segundos
   - El click_soft en captions es AUTOMÁTICO (suena SIEMPRE, no lo listes en sfx_events)

5. ZOOM PUNCH-INS (apply_zoom_punch_in):
   - SIEMPRE true excepto vlogs muy íntimos
   - Mínimo 1 cada 10 segundos en videos dinámicos
   - intensity: subtle (por defecto), medium (énfasis), strong (revelación/punchline)

6. MÚSICA + AMBIENT — TEXTURE OBLIGATORIA:
   - ambient_track: NUNCA "none" — SIEMPRE elige uno según tono
   - Vlog íntimo → asmr_room_tone + music none
   - Tutorial → subtle_pulse + music corporate_clean
   - Comedy/hype → tiktok_ambient_beat + music upbeat_energetic
   - Storytelling → cinematic_drone + music epic_cinematic

7. COLOR GRADING: cinematic | vibrante | minimalista (elige según mood, NO neutro)

8. CAPTION_EMPHASIS: 1-3 momentos clave máximo (climax, dato importante, CTA)

9. text_overlays: 1-3 palabras MAYÚSCULAS solamente (NO descripciones)

10. BROLL DALL-E: máximo 2 imágenes (si video > 20s, mínimo 1)

11. ABSOLUTA PRIORIDAD: NO seas conservador. Si un efecto aporta dinamismo, aplícalo.
    El default es SIEMPRE "sí" a menos que afecte negativamente el mensaje principal.
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
