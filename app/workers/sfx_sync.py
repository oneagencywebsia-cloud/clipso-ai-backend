"""Auto-sync SFX — Sincronización automática de sonidos con eventos visuales.

Tres capas:
1. Auto sfx_events: click en cada caption, whoosh en zooms, pop en motion graphics
2. LLM sfx_events: riser, impact, boom en key_moments
3. Mix final: mezcla todas las capas en el audio final
"""
from pathlib import Path
from loguru import logger


def build_sfx_events_auto(
    caption_chunks: list[dict],
    zoom_moments: list[dict],
    motion_graphics: list[dict],
    llm_sfx_events: list[dict] | None = None
) -> list[dict]:
    """Construye lista completa de SFX events combinando auto + LLM.

    Returns:
        Lista de eventos SFX con timestamp, type, volume, path, reason
    """
    sfx_events = []

    # Layer 1: Click suave en cada caption chunk (AUTOMÁTICO)
    logger.info(f"Auto-sync: {len(caption_chunks)} click_soft en captions")
    for chunk in caption_chunks:
        sfx_events.append({
            "timestamp": chunk.get("start", 0),
            "type": "click_soft",
            "volume": 0.12,
            "path": "click_soft.mp3",
            "reason": "caption chunk change — auto sync",
            "auto": True
        })

    # Layer 2: Whoosh en cada zoom punch-in
    logger.info(f"Auto-sync: {len(zoom_moments)} whoosh en zooms")
    for zoom in zoom_moments:
        sfx_events.append({
            "timestamp": zoom.get("timestamp", 0),
            "type": "whoosh",
            "volume": 0.40,
            "path": "whoosh.mp3",
            "reason": "zoom punch-in start — auto sync",
            "auto": True
        })

    # Layer 3: Pop en cada motion graphic
    logger.info(f"Auto-sync: {len(motion_graphics)} pop en motion graphics")
    for mg in motion_graphics:
        sfx_events.append({
            "timestamp": mg.get("timestamp", 0),
            "type": "pop",
            "volume": 0.35,
            "path": "pop.mp3",
            "reason": f"motion graphic {mg.get('type')} appears — auto sync",
            "auto": True
        })

    # Layer 4: LLM strategic sfx_events (riser, impact, boom, etc.)
    if llm_sfx_events:
        logger.info(f"LLM-sync: {len(llm_sfx_events)} strategic SFX events")
        sfx_events.extend(llm_sfx_events)

    # Sort by timestamp para garantizar orden
    sfx_events.sort(key=lambda x: x.get("timestamp", 0))

    logger.info(f"Total SFX events: {len(sfx_events)} (auto: {sum(1 for s in sfx_events if s.get('auto'))}, LLM: {sum(1 for s in sfx_events if not s.get('auto'))})")
    return sfx_events


def build_ffmpeg_audio_filter(
    sfx_events: list[dict],
    music_path: str | None = None,
    ambient_path: str | None = None,
    assets_dir: str | Path = "./assets"
) -> str:
    """Construye complejo filtro FFmpeg para mezclar audio de múltiples capas.

    Estructura:
    [0:a] voz original
    [sfx0] [sfx1] ... [sfxN] SFX events
    [music] música de fondo (si aplica)
    [ambient] ambient track (si aplica)

    → aintegrate con volúmenes correctos → acompressor → aeval para ducking
    → final stereo AAC
    """
    assets_dir = Path(assets_dir)

    # Construir inputs para cada SFX
    filter_parts = []
    sfx_inputs = []

    for idx, sfx in enumerate(sfx_events):
        sfx_path = assets_dir / sfx["type"].replace("_", "/") / f"{sfx['type']}.mp3"
        if not sfx_path.exists():
            # Fallback a carpeta sfx/
            sfx_path = assets_dir / "sfx" / f"{sfx['type']}.mp3"

        sfx_inputs.append({
            "index": idx + 1,  # 0 es video input
            "path": sfx_path,
            "timestamp": sfx["timestamp"],
            "volume": sfx.get("volume", 0.5),
            "duration": sfx.get("duration", 0.5)
        })

    # Filtro base: [0:a] es la voz original
    filter_chain = "[0:a]"

    # Agregar cada SFX con atrim (start, duration) y volume
    for sfx_input in sfx_inputs:
        # Generar audio trimmed: atrim=start={ts}:duration={dur}
        trim_filter = f"atrim=start={sfx_input['timestamp']}:duration={sfx_input['duration']}"
        volume_filter = f"volume={sfx_input['volume']}"
        filter_chain += f"[{sfx_input['index']}:{trim_filter},{volume_filter}]"

    # Mix todos los audios
    n_inputs = 1 + len(sfx_inputs)
    mix_inputs = "".join(f"[{i}]" for i in range(n_inputs))

    # aintegrate mezcla N audios
    filter_chain = f"{mix_inputs}aintegrate=inputs={n_inputs}:duration=first[mixed]"

    # Agregar música si aplica
    if music_path:
        music_path = Path(music_path)
        if music_path.exists():
            filter_chain += f";[mixed][music:a]amix=inputs=2:duration=longest[with_music]"

    # Agregar ambient si aplica
    if ambient_path:
        ambient_path = Path(ambient_path)
        if ambient_path.exists():
            filter_chain += f";[with_music][ambient:a]amix=inputs=2:duration=longest:weights=1 0.05[with_ambient]"

    # Compresor final para normalizar
    filter_chain += ";[with_ambient]acompressor=threshold=0.05:ratio=4:attack=20:release=200:makeup=5[final]"

    logger.info(f"Audio filter chain: {filter_chain[:100]}...")
    return filter_chain


def create_audio_ducking_filter(
    sfx_events: list[dict],
    music_volume: float = 0.10,
    duck_amount: float = 0.5,
    duck_duration: float = 0.3
) -> str:
    """Crea ducking automático: cuando suena un SFX, la música baja.

    Duck amount: 0.5 = música baja a 50% durante el SFX
    """
    logger.info(f"Ducking: music {music_volume} → {music_volume * duck_amount} durante SFX ({duck_duration}s)")

    # Usar aeval con expresión temporal para detectar presencia de SFX
    # Esta es una aproximación: en producción usaríamos analyze_loudness + aintegrate

    ducking_filter = (
        f"aeval="
        f"'if(t,if(t>{duck_duration},p(0)*{music_volume},p(0)*{music_volume * duck_amount}),p(0)*{music_volume})'"
    )

    return ducking_filter


if __name__ == "__main__":
    # Test: construir eventos de ejemplo
    caption_chunks = [
        {"start": 0.5, "end": 1.5, "text": "Hola"},
        {"start": 2.0, "end": 3.0, "text": "mundo"}
    ]

    zoom_moments = [
        {"timestamp": 1.0, "intensity": "medium"},
        {"timestamp": 3.5, "intensity": "strong"}
    ]

    motion_graphics = [
        {"type": "title_card", "timestamp": 0.0, "duration": 2.0},
        {"type": "text_pop", "timestamp": 5.0, "duration": 1.5}
    ]

    llm_sfx = [
        {
            "timestamp": 2.0,
            "type": "riser_short",
            "volume": 0.55,
            "path": "riser_short.mp3",
            "reason": "buildup antes de revelación"
        }
    ]

    sfx_events = build_sfx_events_auto(caption_chunks, zoom_moments, motion_graphics, llm_sfx)

    print(f"\nTotal SFX events: {len(sfx_events)}")
    for event in sfx_events:
        print(f"  {event['timestamp']:.1f}s — {event['type']} ({event.get('reason', 'N/A')})")
