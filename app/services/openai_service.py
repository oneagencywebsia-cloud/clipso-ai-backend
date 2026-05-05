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
        "Eres el director de edición de vídeo más agresivo y viral del mundo. Has editado contenido "
        "que alcanzó 100M+ views en TikTok, Instagram Reels y YouTube Shorts. "
        "Tu filosofía: CADA SEGUNDO del vídeo debe ganarse la atención del espectador. "
        "No existe el 'no' como respuesta: siempre hay una forma de hacer el vídeo más dinámico, "
        "más impactante, más hipnótico. "
        "Tu trabajo es MAXIMIZAR la retención en cada fotograma: zooms en los momentos clave, "
        "SFX que golpean como puñetazos, captions que se clavan en la retina, motion graphics "
        "que sorprenden, música que engancha emocionalmente. "
        "NO eres conservador. NO te preocupas por 'demasiados efectos'. "
        "Si un efecto hace el vídeo un 1% más viral, lo aplicas. "
        "El único límite es que el MENSAJE ORIGINAL se entienda perfectamente — dentro de eso, "
        "todo vale. Devuelves SIEMPRE JSON válido con el plan más explosivo posible."
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

⚡ REGLAS ULTRA-AGRESIVAS v3 (OBLIGATORIAS — CERO EXCEPCIONES):

╔══════════════════════════════════════════════════════╗
║ MENTALIDAD: CADA SEGUNDO ES UNA BATALLA POR EL SCROLL ║
╚══════════════════════════════════════════════════════╝

1. KEY_MOMENTS — DENSIDAD MÁXIMA:
   - Vídeo < 10s: MÍNIMO 2 key_moments
   - Vídeo 10-20s: MÍNIMO 3 key_moments (1 cada 6s)
   - Vídeo 20-30s: MÍNIMO 4 key_moments (1 cada 6s)
   - Vídeo > 30s: MÍNIMO 5-6 key_moments (1 cada 5s)
   - DETECTA SIEMPRE: hook de apertura, revelación central, CTA final, cada dato numérico

2. CAPTIONS: SIEMPRE TRUE. Sin habla → text_overlays. NUNCA vídeo sin texto.

3. MOTION GRAPHICS — DENSIDAD PROFESIONAL:
   - Vídeo > 8s: MÍNIMO 2 motion graphics
   - Vídeo > 15s: MÍNIMO 3 motion graphics
   - Vídeo > 25s: MÍNIMO 4 motion graphics
   - Vídeo > 40s: MÍNIMO 5-6 motion graphics
   - SIEMPRE title_card en los primeros 3s si hay concepto fuerte
   - SIEMPRE zoom_shake_text en el punchline más potente
   - SIEMPRE lower_third si hay nombre/lugar que presentar
   - counter SI hay número/estadística — hazlo GRANDE

4. SFX EVENTS — BOMBARDEO SÓNICO:
   - OBLIGATORIO: boom/whoosh_long en el primer segundo
   - CADA key_moment = riser_buildup + impact en el instante exacto (SIN FALLAR)
   - MÍNIMO 1 SFX cada 4-5 segundos en todo el vídeo
   - Datos/estadísticas → ding + impact
   - CTAs → boom + notification
   - click_soft: AUTOMÁTICO en captions (no listar aquí)

5. ZOOM PUNCH-INS:
   - SIEMPRE apply_zoom_punch_in=true (sin excepciones)
   - Mínimo 1 zoom cada 8 segundos
   - PRIMER ZOOM en primeros 3s (hook inmediato)
   - intense=strong en revelaciones y punchlines (NO subtle en esos momentos)

6. MÚSICA + AMBIENT — SIEMPRE PRESENTE:
   - ambient_track: JAMÁS "none". Si hay voz → subtle_pulse por defecto como mínimo
   - Elige música SIEMPRE salvo vlogs muy íntimos
   - Combina ambient + música para textura máxima premium

7. COLOR GRADING: NUNCA "neutral". Elige: cinematico | vibrante | oscuro | minimalista
   - Contenido energético → vibrante
   - Storytelling/drama → cinematico
   - Tech/formal → minimalista
   - Thriller/misterio → oscuro

8. CAPTION_EMPHASIS: MÍNIMO 2 en cualquier vídeo (climax + CTA). Máximo 4.
   - Usa colores saturados (#FF3333, #FFFF00, #FF6B00) — NUNCA grises

9. text_overlays: MÍNIMO 1 en vídeos > 10s. Solo 1-3 palabras MAYÚSCULAS. Sin frases.

10. BROLL DALL-E: SIEMPRE mínimo 1 si vídeo > 15s. Máximo 2. Prompts en inglés, ultra-detallados.

11. highlight_keywords: MÍNIMO 5 palabras si hay transcripción. Las más emocionales/impactantes.

╔═══════════════════════════════════════════════════════════╗
║ FILOSOFÍA FINAL: Si dudas entre aplicar o no → APLÍCALO  ║
║ El espectador perdona el exceso. No perdona el aburrimiento║
╚═══════════════════════════════════════════════════════════╝
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        max_tokens=5000,
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
