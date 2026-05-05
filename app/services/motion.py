"""Motion graphics — Kinetic Typography & Motion Graphics con física de resorte.

Implementación matemática de spring animations usando keyframes ASS \t().
No hay interpolación lineal: cada animación simula overshoot-settle de resorte real.

Modelo de resorte: x(t) = 1 - e^(-ζωt) * cos(ωt)
  donde ζ=damping ratio (0.4 = underdamped, produce bounce visible)
  Aproximado con 5-6 keyframes \t() para compatibilidad ASS.

Coordinate system: ASS PlayResX × PlayResY = video_width × video_height
"""
from pathlib import Path
from loguru import logger
import math


def _hex_to_ass(h: str) -> str:
    h = (h or "").lstrip("#").upper()
    if len(h) != 6:
        return "&H00FFFFFF&"
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}&"


def _fmt_t(s: float) -> str:
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s % 60
    return f"{h}:{m:02d}:{sec:05.2f}"


def _ass_header(video_width: int, video_height: int, styles: list[str]) -> str:
    style_lines = "\n".join(styles)
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style_lines}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _escape_ass_text(text: str) -> str:
    return text.replace("{", "(").replace("}", ")").replace(",", "")


# ─── SPRING PHYSICS ENGINE ────────────────────────────────────────────────────

def _spring_keyframes(
    duration_ms: int,
    target_scale: float = 100.0,
    overshoot: float = 1.22,
    damping: float = 0.4,
    num_bounces: int = 3
) -> str:
    """Genera keyframes \t() que simulan un resorte underdamped.

    Matemática: x_n = target * (1 + A * (-damping)^n)
    donde A controla la amplitud del overshoot inicial.

    Args:
        duration_ms: duración total de la animación en ms
        target_scale: escala final (normalmente 100)
        overshoot: multiplicador del primer pico (1.22 = 122% → rebota a ~88%)
        damping: ratio de amortiguación (0.4 = bounce pronunciado, 0.7 = suave)
        num_bounces: número de rebotes simulados

    Returns:
        String ASS con los keyframes \t() encadenados
    """
    t = target_scale

    # Keyframes del resorte: [peak, undershoot, small_peak, small_undershoot, settle]
    # Calculados con la serie de amortiguación exponencial
    peaks = []
    for i in range(num_bounces * 2 + 1):
        amplitude = overshoot ** 1 * ((-damping) ** i)
        scale_val = t * (1.0 + amplitude * (1.0 - damping ** i))
        scale_val = max(20.0, min(200.0, scale_val))
        peaks.append(round(scale_val, 1))

    # Distribuir keyframes en el tiempo (primer bounce usa 35% del tiempo)
    time_ratios = []
    remaining = 1.0
    for i in range(len(peaks)):
        ratio = remaining * (0.35 if i == 0 else 0.30)
        time_ratios.append(ratio)
        remaining -= ratio
    time_ratios[-1] += remaining  # rest to last

    keyframes = []
    current_time = 0
    for i, (scale, ratio) in enumerate(zip(peaks, time_ratios)):
        next_time = current_time + int(duration_ms * ratio)
        sx = int(scale)
        keyframes.append(f"\\t({current_time},{next_time},\\fscx{sx}\\fscy{sx})")
        current_time = next_time

    return "".join(keyframes)


def _spring_enter(duration_ms: int = 400, strength: str = "medium") -> str:
    """Animación de entrada con spring. strength: subtle|medium|strong."""
    configs = {
        "subtle":  {"overshoot": 1.08, "damping": 0.55, "bounces": 2, "init": 60},
        "medium":  {"overshoot": 1.18, "damping": 0.42, "bounces": 3, "init": 40},
        "strong":  {"overshoot": 1.28, "damping": 0.35, "bounces": 4, "init": 20},
    }
    cfg = configs.get(strength, configs["medium"])
    spring = _spring_keyframes(
        duration_ms, 100.0,
        overshoot=cfg["overshoot"],
        damping=cfg["damping"],
        num_bounces=cfg["bounces"]
    )
    return f"\\fscx{cfg['init']}\\fscy{cfg['init']}{spring}"


def _shake_keyframes(duration_ms: int, intensity: float = 3.0) -> str:
    """Shake horizontal simulando impacto. Decae exponencialmente."""
    offsets = [intensity, -intensity * 0.7, intensity * 0.5, -intensity * 0.35, intensity * 0.2, 0]
    interval = duration_ms // len(offsets)
    frames = []
    for i, offset in enumerate(offsets):
        t0 = i * interval
        t1 = t0 + interval
        px = int(offset)
        frames.append(f"\\t({t0},{t1},\\shad{abs(int(offset * 0.3))})")
    return "".join(frames)


def _rotation_for_importance(importance: float) -> float:
    """Rotación en grados según importance_score [0-1]. Rango: -2.5° a 2.5°."""
    # Palabras muy impactantes entran ligeramente rotadas y se enderezan
    if importance > 0.8:
        return -2.5 + (importance - 0.8) * 12.5  # -2.5° a 0° para [0.8, 1.0]
    return 0.0


# ─── RENDER ENGINE ───────────────────────────────────────────────────────────

def render_motion_graphics_ass(
    motion_graphics: list[dict],
    output_path: str | Path,
    video_width: int = 1080,
    video_height: int = 1920
) -> Path:
    """Genera un único archivo ASS con TODAS las motion graphics del video.

    Cada MG debe tener: type, timestamp, duration, params, [animation_style], [importance_score]
    """
    output_path = Path(output_path)

    styles = [
        f"Style: TitleCard,Impact,160,&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&HA0000000&,1,0,0,0,100,100,0,0,1,14,6,5,60,60,80,1",
        f"Style: TextPop,Impact,130,&H00FFFF00&,&H00FFFF00&,&H00000000&,&HA0000000&,1,0,0,0,100,100,0,0,1,12,4,5,60,60,60,1",
        f"Style: LowerThird,Arial,78,&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&HC8000000&,1,0,0,0,100,100,0,0,4,0,0,1,80,80,220,1",
        f"Style: Counter,Impact,220,&H0000FFFF&,&H0000FFFF&,&H00000000&,&HA0000000&,1,0,0,0,100,100,0,0,1,16,6,5,60,60,60,1",
        f"Style: CallOut,Impact,95,&H0000FFFF&,&H0000FFFF&,&H00000000&,&HA0000000&,1,0,0,0,100,100,0,0,1,9,4,5,60,60,60,1",
        f"Style: HighlightBox,Arial,40,&H0000FF00&,&H0000FF00&,&H0000FF00&,&H00000000&,1,0,0,0,100,100,0,0,1,6,0,7,0,0,0,1",
        f"Style: ImpactWord,Impact,150,&H00FF4444&,&H00FF4444&,&H00000000&,&HA0000000&,1,0,0,0,100,100,0,0,1,14,5,5,60,60,60,1",
    ]

    events = []

    for mg in motion_graphics:
        mg_type = (mg.get("type") or "").lower()
        ts = float(mg.get("timestamp", 0))
        dur = float(mg.get("duration", 2.0))
        params = mg.get("params", {})
        anim_style = mg.get("animation_style", "bounce")
        importance = float(mg.get("importance_score", 0.7))

        try:
            if mg_type == "title_card":
                events.extend(_render_title_card(ts, dur, params, video_width, video_height, anim_style, importance))
            elif mg_type == "text_pop":
                events.extend(_render_text_pop(ts, dur, params, video_width, video_height, anim_style, importance))
            elif mg_type == "lower_third":
                events.extend(_render_lower_third(ts, dur, params, video_width, video_height))
            elif mg_type == "counter":
                events.extend(_render_counter(ts, dur, params, video_width, video_height))
            elif mg_type == "call_out":
                events.extend(_render_call_out(ts, dur, params, video_width, video_height, anim_style))
            elif mg_type == "zoom_shake_text":
                events.extend(_render_zoom_shake_text(ts, dur, params, video_width, video_height, importance))
            elif mg_type == "highlight_box":
                events.extend(_render_highlight_box(ts, dur, params, video_width, video_height))
            elif mg_type == "arrow_pointer":
                events.extend(_render_arrow_pointer(ts, dur, params, video_width, video_height))
            elif mg_type == "progress_bar":
                events.extend(_render_progress_bar(ts, dur, params, video_width, video_height))
            elif mg_type == "glitch_transition":
                events.extend(_render_glitch_transition(ts, dur, params, video_width, video_height))
            else:
                logger.warning(f"Motion graphic tipo desconocido: {mg_type}")
        except Exception as e:
            logger.warning(f"Error renderizando MG {mg_type} en t={ts}: {e}")

    output_path.write_text(_ass_header(video_width, video_height, styles) + "\n".join(events) + "\n", encoding="utf-8")
    logger.info(f"Motion graphics ASS: {len(events)} eventos generados ({len(motion_graphics)} templates)")
    return output_path


# ─── TEMPLATES ────────────────────────────────────────────────────────────────

def _render_title_card(ts, dur, params, vw, vh, anim_style="bounce", importance=0.8):
    """Title card con spring physics. Rotation -2° → 0° en alta importancia."""
    text = _escape_ass_text(str(params.get("text", "TITLE")).upper())
    color = _hex_to_ass(params.get("color", "#FFFFFF"))
    size = int(vh * float(params.get("size_pct", 9)) / 100)

    strength = "strong" if importance > 0.85 else "medium" if importance > 0.6 else "subtle"
    spring = _spring_enter(400, strength)

    rotation = _rotation_for_importance(importance)
    rot_tag = f"\\frz{rotation:.1f}\\t(0,300,\\frz0)" if abs(rotation) > 0.1 else ""

    anim = f"\\fad(60,200){spring}{rot_tag}\\c{color}\\fs{size}"
    return [f"Dialogue: 1,{_fmt_t(ts)},{_fmt_t(ts+dur)},TitleCard,,0,0,0,,{{{anim}}}{text}"]


def _render_text_pop(ts, dur, params, vw, vh, anim_style="bounce", importance=0.7):
    """Text pop con spring physics + rotación en palabras de impacto."""
    text = _escape_ass_text(str(params.get("text", "POP")).upper())
    color = _hex_to_ass(params.get("color", "#FFFF00"))
    size = int(vh * float(params.get("size_pct", 6.5)) / 100)
    pos = params.get("position", "center")
    align = {"top": 8, "center": 5, "bottom": 2, "bottom_third": 2}.get(pos, 5)
    margin_v = int(vh * 0.28) if pos == "bottom_third" else 40

    if anim_style == "shake":
        spring = f"\\fscx100\\fscy100{_shake_keyframes(int(dur * 1000 * 0.6), intensity=8.0)}"
        color_tag = f"\\c{_hex_to_ass('#FF3333')}"
    elif anim_style == "highlight":
        spring = (
            f"\\fscx80\\fscy80\\t(0,200,\\fscx112\\fscy112)\\t(200,300,\\fscx100\\fscy100)"
            f"\\t(300,{int(dur*1000)//2},\\fscx105\\fscy105)"
            f"\\t({int(dur*1000)//2},{int(dur*1000)},\\fscx100\\fscy100)"
        )
        color_tag = f"\\c{color}"
    else:  # bounce (default)
        strength = "strong" if importance > 0.85 else "medium"
        spring = _spring_enter(350, strength)
        color_tag = f"\\c{color}"

    rotation = _rotation_for_importance(importance)
    rot_tag = f"\\frz{rotation:.1f}\\t(0,280,\\frz0)" if abs(rotation) > 0.1 else ""

    anim = f"\\fad(80,120){spring}{color_tag}{rot_tag}\\fs{size}\\an{align}"
    return [f"Dialogue: 1,{_fmt_t(ts)},{_fmt_t(ts+dur)},TextPop,,0,0,{margin_v},,{{{anim}}}{text}"]


def _render_lower_third(ts, dur, params, vw, vh):
    """Lower third con slide-in acelerado (ease-out cubico) + fade out suave."""
    title = _escape_ass_text(str(params.get("title", "")))
    subtitle = _escape_ass_text(str(params.get("subtitle", "")))
    text = f"{title}\\N{{\\fs52\\c&H00CCCCCC&}}{subtitle}" if subtitle else title

    # Slide-in con accel=0.5 (ease-out) — entra rápido, desacelera al final
    x_off = vw + 200
    move = f"\\move({x_off},{vh-280},80,{vh-280},0,320)"
    fade = f"\\fad(0,280)"

    return [f"Dialogue: 1,{_fmt_t(ts)},{_fmt_t(ts+dur)},LowerThird,,0,0,180,,{{{move}{fade}}}{text}"]


def _render_counter(ts, dur, params, vw, vh):
    """Counter animado con easing easeOutCubic (t^0.33 progression)."""
    start_val = int(params.get("start", 0))
    end_val = int(params.get("end", 100))
    suffix = str(params.get("suffix", ""))
    color = _hex_to_ass(params.get("color", "#FFFF00"))

    # easeOutCubic: más rápido al inicio, desacelera al final
    steps = 12
    step_dur = dur / steps
    events = []
    for i in range(steps + 1):
        t_norm = i / steps
        # easeOutCubic: 1 - (1 - t)^3
        eased = 1.0 - (1.0 - t_norm) ** 3
        val = int(start_val + (end_val - start_val) * eased)
        step_start = ts + i * step_dur
        step_end = ts + (i + 1) * step_dur if i < steps else ts + dur

        if i == 0:
            anim = f"\\fad(80,60)\\c{color}\\fscx80\\fscy80\\t(0,200,\\fscx100\\fscy100)"
        elif i == steps:
            # Final: spring punch
            anim = (
                f"\\c{color}"
                f"\\fscx100\\fscy100"
                f"\\t(0,120,\\fscx118\\fscy118)"
                f"\\t(120,200,\\fscx94\\fscy94)"
                f"\\t(200,280,\\fscx102\\fscy102)"
                f"\\t(280,340,\\fscx100\\fscy100)"
            )
        else:
            anim = f"\\c{color}"

        events.append(f"Dialogue: 1,{_fmt_t(step_start)},{_fmt_t(step_end)},Counter,,0,0,0,,{{{anim}}}{val}{suffix}")
    return events


def _render_call_out(ts, dur, params, vw, vh, anim_style="bounce"):
    """Flecha + texto con spring pop-in hacia la zona target."""
    text = _escape_ass_text(str(params.get("text", "")).upper())
    color = _hex_to_ass(params.get("color", "#FFFF00"))
    target_x = int(params.get("target_x", vw // 2))
    target_y = int(params.get("target_y", vh // 2))

    text_x = min(target_x + 220, vw - 200)
    text_y = max(target_y - 90, 80)

    spring = _spring_enter(320, "medium")
    anim = f"\\pos({text_x},{text_y})\\fad(100,150){spring}\\c{color}"
    arrow_anim = f"\\pos({target_x - 60},{target_y})\\fad(100,150)\\fscx80\\fscy80\\t(0,200,\\fscx100\\fscy100)\\c{color}"

    return [
        f"Dialogue: 1,{_fmt_t(ts)},{_fmt_t(ts+dur)},CallOut,,0,0,0,,{{{arrow_anim}}}→",
        f"Dialogue: 1,{_fmt_t(ts)},{_fmt_t(ts+dur)},CallOut,,0,0,0,,{{{anim}}}{text}",
    ]


def _render_zoom_shake_text(ts, dur, params, vw, vh, importance=0.9):
    """Punchline text — spring fuerte + shake + rotación de impacto.

    La animación más agresiva del sistema: simula el golpe físico de un punchline.
    Overshoot 135%, undershoot 82%, settle suave.
    """
    text = _escape_ass_text(str(params.get("text", "")).upper())
    color = _hex_to_ass(params.get("color", "#FF3333"))
    size = int(vh * float(params.get("size_pct", 10)) / 100)

    # Spring extra fuerte para punchlines (overshoot 1.35, damping 0.30)
    dur_ms = min(int(dur * 1000), 600)
    spring = _spring_keyframes(dur_ms, 100.0, overshoot=1.35, damping=0.30, num_bounces=4)

    # Rotación aleatoria-determinista basada en importance: -2.5° o +2.5°
    rot_init = -2.5 if importance > 0.85 else 2.0
    rotation = f"\\frz{rot_init}\\t(0,200,\\frz0)"

    anim = (
        f"\\fad(40,180)"
        f"\\fscx20\\fscy20"
        f"{spring}"
        f"{rotation}"
        f"\\c{color}\\fs{size}"
    )
    return [f"Dialogue: 1,{_fmt_t(ts)},{_fmt_t(ts+dur)},ImpactWord,,0,0,0,,{{{anim}}}{text}"]


def _render_highlight_box(ts, dur, params, vw, vh):
    """Rectángulo de highlight con pulso de opacidad."""
    x = int(params.get("x", vw // 4))
    y = int(params.get("y", vh // 4))
    w = int(params.get("w", vw // 2))
    h = int(params.get("h", vh // 3))
    color = _hex_to_ass(params.get("color", "#00FF00"))

    half_ms = int(dur * 500)
    full_ms = int(dur * 1000)
    anim = f"\\fad(100,100)\\c{color}\\alpha&H60&\\t(0,{half_ms},\\alpha&H00&)\\t({half_ms},{full_ms},\\alpha&H80&)"

    rect = f"{{\\p1}}{{{anim}}}m {x} {y} l {x+w} {y} l {x+w} {y+h} l {x} {y+h}{{\\p0}}"
    return [f"Dialogue: 1,{_fmt_t(ts)},{_fmt_t(ts+dur)},HighlightBox,,0,0,0,,{rect}"]


def _render_arrow_pointer(ts, dur, params, vw, vh):
    """Flecha animada con bounce hacia el target."""
    target_x = int(params.get("target_x", vw // 2))
    target_y = int(params.get("target_y", vh // 2))
    color = _hex_to_ass(params.get("color", "#FFFF00"))

    spring = _spring_enter(280, "medium")
    anim = f"\\fad(80,100)\\pos({target_x - 70},{target_y}){spring}\\c{color}"
    return [f"Dialogue: 1,{_fmt_t(ts)},{_fmt_t(ts+dur)},CallOut,,0,0,0,,{{{anim}}}→"]


def _render_progress_bar(ts, dur, params, vw, vh):
    """Barra de progreso con fill animado (easeOutCubic)."""
    end_pct = float(params.get("end_pct", 100))
    color = _hex_to_ass(params.get("color", "#00FFFF"))
    at_top = params.get("position", "top") == "top"

    bar_y = 40 if at_top else vh - 40
    bar_x = int(vw * 0.08)
    max_w = int(vw * 0.84)
    end_w = int(max_w * end_pct / 100)
    scale_x = int(end_pct)

    anim = f"\\fad(60,80)\\c{color}\\fscx1\\fscy100\\t(0,{int(dur*1000)},\\fscx{scale_x})"
    rect = f"{{\\p1}}{{{anim}}}m {bar_x} {bar_y} l {bar_x + max_w} {bar_y} l {bar_x + max_w} {bar_y + 8} l {bar_x} {bar_y + 8}{{\\p0}}"
    return [f"Dialogue: 1,{_fmt_t(ts)},{_fmt_t(ts+dur)},HighlightBox,,0,0,0,,{rect}"]


def _render_glitch_transition(ts, dur, params, vw, vh):
    """Glitch RGB-split con desplazamiento de canal alternado.

    Simula corrupción digital — 8 frames con offset X/Y alternados.
    """
    intensity = float(params.get("intensity", 0.5))
    offset = max(3, int(12 * intensity))

    events = []
    frames = 8
    frame_dur = dur / frames

    colors = ["&H00400000&", "&H00004000&", "&H00000040&"]  # R, G, B channels
    for i in range(frames):
        frame_start = ts + i * frame_dur
        frame_end = ts + (i + 1) * frame_dur
        ox = offset if i % 2 == 0 else -offset
        oy = (offset // 2) if i % 3 == 0 else -(offset // 2)
        color_idx = i % 3

        anim = f"\\pos({vw//2 + ox},{vh//2 + oy})\\c{colors[color_idx]}\\alpha&H40&\\fs{int(vh * 0.12)}"
        events.append(f"Dialogue: 1,{_fmt_t(frame_start)},{_fmt_t(frame_end)},ImpactWord,,0,0,0,,{{{anim}}}▓")

    return events
