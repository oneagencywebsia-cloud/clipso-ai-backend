"""Motion graphics — Templates reutilizables generados como ASS overlays.

Cada template genera un archivo .ass que puede combinarse con el filter ass
en un solo encode para máximo rendimiento.

Coordinate system: ASS PlayResX × PlayResY = video_width × video_height
"""
from pathlib import Path
from loguru import logger


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


def render_motion_graphics_ass(
    motion_graphics: list[dict],
    output_path: str | Path,
    video_width: int = 1080,
    video_height: int = 1920
) -> Path:
    """Genera un único archivo ASS con TODAS las motion graphics del video.

    Cada motion graphic en `motion_graphics` debe tener:
        - type: title_card | text_pop | lower_third | counter | highlight_box | zoom_shake_text | call_out | arrow_pointer | progress_bar | glitch_transition
        - timestamp: float
        - duration: float
        - params: dict con parámetros específicos del template

    Templates soportados (todos generan layer 1, encima de los captions layer 0):
    """
    output_path = Path(output_path)

    styles = [
        # title_card: texto grande centrado con scale-in
        f"Style: TitleCard,Impact,160,&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&H80000000&,1,0,0,0,100,100,0,0,1,12,4,5,40,40,40,1",
        # text_pop: texto pop-up con bounce
        f"Style: TextPop,Impact,120,&H0000FFFF&,&H0000FFFF&,&H00000000&,&H80000000&,1,0,0,0,100,100,0,0,1,10,3,5,40,40,40,1",
        # lower_third: barra inferior (left aligned)
        f"Style: LowerThird,Arial,72,&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&HC0000000&,1,0,0,0,100,100,0,0,4,0,0,1,80,80,200,1",
        # counter: número grande
        f"Style: Counter,Impact,200,&H0000FFFF&,&H0000FFFF&,&H00000000&,&H80000000&,1,0,0,0,100,100,0,0,1,14,5,5,40,40,40,1",
        # call_out: texto con flecha
        f"Style: CallOut,Impact,90,&H0000FFFF&,&H0000FFFF&,&H00000000&,&H80000000&,1,0,0,0,100,100,0,0,1,8,3,5,40,40,40,1",
        # highlight_box: borde de rectángulo (drawing)
        f"Style: HighlightBox,Arial,40,&H0000FF00&,&H0000FF00&,&H0000FF00&,&H00000000&,1,0,0,0,100,100,0,0,1,6,0,7,0,0,0,1",
    ]

    events = []

    for mg in motion_graphics:
        mg_type = (mg.get("type") or "").lower()
        ts = float(mg.get("timestamp", 0))
        dur = float(mg.get("duration", 2.0))
        params = mg.get("params", {})

        try:
            if mg_type == "title_card":
                events.extend(_render_title_card(ts, dur, params, video_width, video_height))
            elif mg_type == "text_pop":
                events.extend(_render_text_pop(ts, dur, params, video_width, video_height))
            elif mg_type == "lower_third":
                events.extend(_render_lower_third(ts, dur, params, video_width, video_height))
            elif mg_type == "counter":
                events.extend(_render_counter(ts, dur, params, video_width, video_height))
            elif mg_type == "call_out":
                events.extend(_render_call_out(ts, dur, params, video_width, video_height))
            elif mg_type == "zoom_shake_text":
                events.extend(_render_zoom_shake_text(ts, dur, params, video_width, video_height))
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
            logger.warning(f"Error renderizando MG {mg_type}: {e}")

    output_path.write_text(_ass_header(video_width, video_height, styles) + "\n".join(events) + "\n", encoding="utf-8")
    logger.info(f"Motion graphics ASS: {len(events)} eventos generados")
    return output_path


def _render_title_card(ts, dur, params, vw, vh):
    """Texto grande centrado con fade + scale-in."""
    text = _escape_ass_text(str(params.get("text", "TITLE")).upper())
    color = _hex_to_ass(params.get("color", "#FFFFFF"))
    size = int(vh * float(params.get("size_pct", 9)) / 100)
    anim = (
        f"\\fad(200,200)"
        f"\\fscx70\\fscy70"
        f"\\t(0,300,\\fscx105\\fscy105)"
        f"\\t(300,400,\\fscx100\\fscy100)"
        f"\\c{color}\\fs{size}"
    )
    return [f"Dialogue: 1,{_fmt_t(ts)},{_fmt_t(ts+dur)},TitleCard,,0,0,0,,{{{anim}}}{text}"]


def _render_text_pop(ts, dur, params, vw, vh):
    """Texto que aparece con bounce en una posición."""
    text = _escape_ass_text(str(params.get("text", "POP")).upper())
    color = _hex_to_ass(params.get("color", "#FFFF00"))
    size = int(vh * float(params.get("size_pct", 6.5)) / 100)
    pos = params.get("position", "center")
    align = {"top": 8, "center": 5, "bottom": 2, "bottom_third": 2}.get(pos, 5)
    margin_v = int(vh * 0.30) if pos == "bottom_third" else 40

    anim = (
        f"\\fad(120,120)"
        f"\\fscx60\\fscy60"
        f"\\t(0,200,\\fscx115\\fscy115)"
        f"\\t(200,280,\\fscx100\\fscy100)"
        f"\\c{color}\\fs{size}\\an{align}"
    )
    return [f"Dialogue: 1,{_fmt_t(ts)},{_fmt_t(ts+dur)},TextPop,,0,0,{margin_v},,{{{anim}}}{text}"]


def _render_lower_third(ts, dur, params, vw, vh):
    """Barra inferior con título + subtítulo, slide-in desde izquierda."""
    title = _escape_ass_text(str(params.get("title", "")))
    subtitle = _escape_ass_text(str(params.get("subtitle", "")))

    text = f"{title}\\N{{\\fs48\\c&H00CCCCCC&}}{subtitle}" if subtitle else title

    # Slide-in: empieza fuera de pantalla (x=-vw) y va a marginL
    move = f"\\move(-{vw//2},{vh-300},80,{vh-300},0,300)"
    fade = f"\\fad(0,300)"

    return [f"Dialogue: 1,{_fmt_t(ts)},{_fmt_t(ts+dur)},LowerThird,,0,0,200,,{{{move}{fade}}}{text}"]


def _render_counter(ts, dur, params, vw, vh):
    """Número grande con contador animado de start a end."""
    start_val = int(params.get("start", 0))
    end_val = int(params.get("end", 100))
    suffix = str(params.get("suffix", ""))
    color = _hex_to_ass(params.get("color", "#FFFF00"))

    # Generar 10 keyframes del counter
    events = []
    steps = 10
    step_dur = dur / steps
    for i in range(steps + 1):
        progress = i / steps
        val = int(start_val + (end_val - start_val) * progress)
        text_step = f"{val}{suffix}"
        step_start = ts + i * step_dur
        step_end = ts + (i + 1) * step_dur if i < steps else ts + dur

        anim = f"\\fad(80,80)\\c{color}" if i == 0 else f"\\c{color}"
        if i == steps:
            # último: zoom-shake
            anim = f"\\c{color}\\fscx100\\fscy100\\t(0,150,\\fscx115\\fscy115)\\t(150,250,\\fscx100\\fscy100)"

        events.append(
            f"Dialogue: 1,{_fmt_t(step_start)},{_fmt_t(step_end)},Counter,,0,0,0,,{{{anim}}}{text_step}"
        )
    return events


def _render_call_out(ts, dur, params, vw, vh):
    """Flecha + texto apuntando a una zona del frame."""
    text = _escape_ass_text(str(params.get("text", "")).upper())
    color = _hex_to_ass(params.get("color", "#FFFF00"))
    target_x = int(params.get("target_x", vw // 2))
    target_y = int(params.get("target_y", vh // 2))

    # Posicionar texto cerca del target (offset 200px)
    text_x = target_x + 250
    text_y = target_y - 100

    anim = (
        f"\\pos({text_x},{text_y})"
        f"\\fad(150,150)"
        f"\\fscx70\\fscy70"
        f"\\t(0,250,\\fscx100\\fscy100)"
        f"\\c{color}"
    )
    arrow = f"  →"  # flecha simple unicode
    return [f"Dialogue: 1,{_fmt_t(ts)},{_fmt_t(ts+dur)},CallOut,,0,0,0,,{{{anim}}}{arrow} {text}"]


def _render_zoom_shake_text(ts, dur, params, vw, vh):
    """Texto que entra con zoom-shake intenso para punchlines."""
    text = _escape_ass_text(str(params.get("text", "")).upper())
    color = _hex_to_ass(params.get("color", "#FF3333"))
    size = int(vh * float(params.get("size_pct", 10)) / 100)

    # Multi-stage shake animation
    anim = (
        f"\\fad(60,150)"
        f"\\fscx50\\fscy50"
        f"\\t(0,150,\\fscx130\\fscy130)"
        f"\\t(150,200,\\fscx95\\fscy95)"
        f"\\t(200,260,\\fscx105\\fscy105)"
        f"\\t(260,320,\\fscx100\\fscy100)"
        f"\\c{color}\\fs{size}"
    )
    return [f"Dialogue: 1,{_fmt_t(ts)},{_fmt_t(ts+dur)},TextPop,,0,0,0,,{{{anim}}}{text}"]


def _render_highlight_box(ts, dur, params, vw, vh):
    """Rectángulo con borde pulsante para destacar elementos."""
    x = int(params.get("x", vw // 4))
    y = int(params.get("y", vh // 4))
    w = int(params.get("w", vw // 2))
    h = int(params.get("h", vh // 3))
    color = _hex_to_ass(params.get("color", "#00FF00"))

    anim = (
        f"\\fad(100,100)"
        f"\\c{color}"
        f"\\t(0,{int(dur*1000)//2},\\alpha&H00&)"
        f"\\t({int(dur*1000)//2},{int(dur*1000)},\\alpha&H80&)"
    )

    rect = f"{{\\p1}}{{{anim}}}m {x} {y} l {x+w} {y} l {x+w} {y+h} l {x} {y+h}{{\\p0}}"
    return [f"Dialogue: 1,{_fmt_t(ts)},{_fmt_t(ts+dur)},HighlightBox,,0,0,0,,{rect}"]


def _render_arrow_pointer(ts, dur, params, vw, vh):
    """Flecha animada apuntando a una ubicación específica."""
    target_x = int(params.get("target_x", vw // 2))
    target_y = int(params.get("target_y", vh // 2))
    color = _hex_to_ass(params.get("color", "#FFFF00"))

    arrow_x = target_x - 80
    arrow_y = target_y

    anim = (
        f"\\fad(100,100)"
        f"\\pos({arrow_x},{arrow_y})"
        f"\\c{color}"
        f"\\t(0,{int(dur*1000)},\\fscx100\\fscy100)"
    )
    return [f"Dialogue: 1,{_fmt_t(ts)},{_fmt_t(ts+dur)},CallOut,,0,0,0,,{{{anim}}}→"]


def _render_progress_bar(ts, dur, params, vw, vh):
    """Barra de progreso animada."""
    start_pct = float(params.get("start_pct", 0))
    end_pct = float(params.get("end_pct", 100))
    color = _hex_to_ass(params.get("color", "#00FFFF"))

    bar_y = int(params.get("position", "top") == "top" and 50 or vh - 50)
    bar_x_start = int(vw * 0.1)
    bar_width = int(vw * 0.8)

    start_width = int(bar_width * start_pct / 100)
    end_width = int(bar_width * end_pct / 100)

    anim = (
        f"\\fad(80,80)"
        f"\\c{color}"
        f"\\t(0,{int(dur*1000)},\\fscx{int(100 + (end_pct - start_pct))})"
    )

    bar_rect = f"{{\\p1}}{{{anim}}}m {bar_x_start} {bar_y} l {bar_x_start + end_width} {bar_y}{{\\p0}}"
    return [f"Dialogue: 1,{_fmt_t(ts)},{_fmt_t(ts+dur)},HighlightBox,,0,0,0,,{bar_rect}"]


def _render_glitch_transition(ts, dur, params, vw, vh):
    """Efecto glitch RGB-split para transiciones."""
    intensity = float(params.get("intensity", 0.5))
    color_r = _hex_to_ass(params.get("color_r", "#FF0000"))
    color_g = _hex_to_ass(params.get("color_g", "#00FF00"))
    color_b = _hex_to_ass(params.get("color_b", "#0000FF"))

    offset = int(5 * intensity)

    events = []
    keyframes = 6
    frame_dur = dur / keyframes

    for i in range(keyframes):
        frame_start = ts + i * frame_dur
        frame_end = ts + (i + 1) * frame_dur

        offset_x = offset if i % 2 == 0 else -offset
        offset_y = offset if i % 3 == 0 else -offset

        anim = (
            f"\\pos({vw//2 + offset_x},{vh//2 + offset_y})"
            f"\\alpha&H00&"
            f"\\fad(0,0)"
        )

        events.append(f"Dialogue: 1,{_fmt_t(frame_start)},{_fmt_t(frame_end)},TextPop,,0,0,0,,{{{anim}}}GLITCH")

    return events
