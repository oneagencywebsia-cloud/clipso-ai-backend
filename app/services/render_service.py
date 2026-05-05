"""render_service.py — Renderizado final vía Remotion SSR (Node.js subprocess)."""
from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from pathlib import Path

from loguru import logger

from app.services.db import db

# ── Configuración ─────────────────────────────────────────────────────────────

# Ruta al repo del app (donde vive remotion_render.ts).
# En producción, montar el volumen del app en este path o configurar la env var.
_APP_DIR = Path(os.getenv("REMOTION_APP_DIR", "/app-remotion"))

# Comando para ejecutar el script. tsx maneja TypeScript sin compilar.
_NODE_CMD = ["npx", "tsx", str(_APP_DIR / "remotion_render.ts")]

# Regex para parsear líneas PROGRESS:<n> del stdout del script Node
_RE_PROGRESS = re.compile(r"^PROGRESS:(\d+)$")
_RE_DONE     = re.compile(r"^DONE:(.+)$")
_RE_ERROR    = re.compile(r"^ERROR:(.+)$")


# ══════════════════════════════════════════════════════════════════════════════

async def render_final_video(
    timeline_json: dict,
    output_path: str,
    job_id: str | None = None,
    progress_offset: int = 70,
    progress_weight: float = 0.28,
) -> str:
    """
    Renderiza el video final usando Remotion SSR.

    Guarda el timeline_json en un archivo temporal, lanza el script Node.js
    `remotion_render.ts` como subprocess y lee su stdout en tiempo real.
    Si el proceso emite PROGRESS:<n>, actualiza Supabase (si job_id dado).
    Si el proceso emite ERROR:<msg> o sale con código != 0, lanza RuntimeError.

    Args:
        timeline_json:   DirectorTimeline serializado (dict).
        output_path:     Ruta absoluta del .mp4 de salida.
        job_id:          UUID del job para update_job_status(). None = sin updates.
        progress_offset: % de progreso base desde el que se empieza a reportar.
                         Ajusta según en qué paso del pipeline se llama (default 70).
        progress_weight: Fracción del rango [0, 100] que ocupa este paso.
                         0.28 → ocupa 28 puntos de progreso (70→98).

    Returns:
        output_path resuelto como string absoluto.

    Raises:
        RuntimeError: si Node.js falla o el archivo de salida no se crea.
    """
    output_path = str(Path(output_path).resolve())

    # ── 1. Serializar el timeline a disco ──────────────────────────────────────
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".timeline.json", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(timeline_json, tmp, ensure_ascii=False)
        tmp_json_path = tmp.name

    logger.info(
        f"render_final_video | job={job_id} | "
        f"json={tmp_json_path} | out={output_path}"
    )

    try:
        # ── 2. Lanzar Node.js como subprocess ─────────────────────────────────
        proc = await asyncio.create_subprocess_exec(
            *_NODE_CMD,
            tmp_json_path,
            output_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(_APP_DIR),
        )

        error_lines: list[str] = []
        last_reported_progress = -1

        # ── 3. Leer stdout en tiempo real ─────────────────────────────────────
        assert proc.stdout is not None
        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").rstrip()
            if not line:
                continue

            if m := _RE_PROGRESS.match(line):
                node_pct = int(m.group(1))           # 0-100 desde Node
                # Mapear al rango del pipeline: offset + node_pct × weight
                pipeline_pct = int(progress_offset + node_pct * progress_weight)
                pipeline_pct = min(pipeline_pct, 98)  # nunca 100 hasta DONE

                if pipeline_pct > last_reported_progress:
                    last_reported_progress = pipeline_pct
                    logger.debug(f"Render progress: node={node_pct}% → pipeline={pipeline_pct}%")
                    if job_id:
                        db.update_job_status(job_id, "rendering", pipeline_pct)

            elif m := _RE_ERROR.match(line):
                error_lines.append(m.group(1))
                logger.error(f"Node ERROR: {m.group(1)}")

            elif _RE_DONE.match(line):
                logger.info(f"Node DONE: {line}")

            else:
                logger.debug(f"node stdout: {line}")

        # ── 4. Leer stderr (no bloquea — ya terminó el stdout) ────────────────
        assert proc.stderr is not None
        stderr_raw = await proc.stderr.read()
        stderr_text = stderr_raw.decode("utf-8", errors="replace").strip()
        if stderr_text:
            logger.warning(f"Node stderr:\n{stderr_text}")

        # ── 5. Esperar exit code ───────────────────────────────────────────────
        return_code = await proc.wait()

        if return_code != 0:
            error_summary = " | ".join(error_lines) or stderr_text or f"exit code {return_code}"
            raise RuntimeError(f"remotion_render.ts falló: {error_summary}")

        # ── 6. Verificar que el archivo de salida existe ───────────────────────
        if not Path(output_path).is_file():
            raise RuntimeError(
                f"remotion_render.ts terminó con exit 0 pero no creó {output_path}"
            )

        logger.success(f"Render completado: {output_path} ({Path(output_path).stat().st_size // 1024} KB)")
        return output_path

    finally:
        # Limpiar temporal sin importar si hubo error
        try:
            Path(tmp_json_path).unlink(missing_ok=True)
        except Exception:
            pass
