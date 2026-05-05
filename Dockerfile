# syntax=docker/dockerfile:1.6
# Imagen compartida por los servicios `api` y `worker`.
# El CMD se sobreescribe en docker-compose según el rol.

# ── Stage 1: Dependencias Python (cacheable) ──────────────────────────────────
FROM python:3.11-slim AS py-deps

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install -r requirements.txt

# ── Stage 2: Runtime híbrido Python + Node 20 + FFmpeg ───────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Sistema: FFmpeg + curl + Node 20 LTS (necesario para npx tsx remotion_render.ts)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
        ca-certificates \
        gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
       | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
       > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && npm install -g tsx \
    && apt-get purge -y --auto-remove gnupg \
    && rm -rf /var/lib/apt/lists/* /tmp/* /root/.npm

# Copiar paquetes Python ya instalados desde el stage anterior
COPY --from=py-deps /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=py-deps /usr/local/bin            /usr/local/bin

WORKDIR /app

# Código fuente
COPY app    ./app
COPY assets ./assets

# El repo del app (Remotion) se monta en runtime vía volumen:
#   /app-remotion → bind mount del repo clipso-app (read-only)
ENV REMOTION_APP_DIR=/app-remotion

EXPOSE 8000

# Comando por defecto: API — sobreescrito a "celery" en el servicio worker
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
