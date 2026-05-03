# CLIPSO.AI — Backend API

API REST que orquesta toda la lógica de CLIPSO.AI:
- 📤 Upload de vídeos a Cloudflare R2 (presigned URLs)
- 🎬 Pipeline IA con OpenAI (Whisper + GPT-4 Vision + DALL-E 3)
- ⚙️ Edición con FFmpeg
- 📊 Persistencia en Supabase
- 🔄 Cola de procesamiento con Redis Queue

**Stack:** FastAPI · Python 3.11 · boto3 · OpenAI · ffmpeg-python · supabase-py · RQ

---

## 🏗️ Arquitectura

```
Frontend (app.clipso.ai)
        ↓
   Backend API (api.clipso.ai)  ← FastAPI
        ↓
   ┌────┴────┐
   ↓         ↓
Redis    Supabase
  ↓
Worker (RQ)
  ↓
┌──────────┬──────────┬──────────┐
↓          ↓          ↓          ↓
R2     Whisper   GPT-4V    FFmpeg
```

---

## 📂 Estructura

```
backend/
├── app/
│   ├── main.py                  # FastAPI app
│   ├── core/
│   │   ├── config.py            # Settings (env vars)
│   │   └── security.py          # Supabase JWT auth
│   ├── routers/
│   │   ├── upload.py            # POST /v1/upload/presigned
│   │   ├── projects.py          # CRUD proyectos
│   │   └── jobs.py              # POST /v1/jobs, GET status, feedback
│   ├── services/
│   │   ├── r2.py                # Cloudflare R2 (boto3)
│   │   ├── openai_service.py    # Whisper, GPT-4 Vision, DALL-E
│   │   ├── video.py             # FFmpeg (extract, subs, render)
│   │   └── db.py                # Cliente Supabase
│   ├── schemas/
│   │   └── models.py            # Pydantic schemas
│   └── workers/
│       ├── queue.py             # RQ enqueue
│       └── pipeline.py          # Pipeline completo
├── supabase_schema.sql          # SQL para crear tablas
├── Dockerfile                   # API container
├── Dockerfile.worker            # Worker container
├── docker-compose.yml           # Local dev (api + worker + redis)
└── requirements.txt
```

---

## 🚀 Desarrollo local

### 1. Setup

```bash
cd backend
cp .env.example .env
# Edita .env con tus credenciales
```

### 2. Crear tablas en Supabase

```bash
# Copia el contenido de supabase_schema.sql en Supabase SQL Editor y ejecuta
```

### 3. Arrancar todo con Docker

```bash
docker compose up --build
```

- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- Redis: localhost:6379
- Worker: corre en background

### 4. (Alternativa) Sin Docker

```bash
pip install -r requirements.txt

# Terminal 1 — API
uvicorn app.main:app --reload

# Terminal 2 — Worker
rq worker clipso-pipeline --url redis://localhost:6379

# Terminal 3 — Redis (si no está corriendo)
redis-server
```

---

## 📡 Endpoints

### Health
- `GET /` — Info básica
- `GET /health` — Health check

### Upload
- `POST /v1/upload/presigned` — Genera URL pre-firmada para subir vídeo a R2

### Projects
- `POST /v1/projects` — Crear proyecto
- `GET /v1/projects` — Listar proyectos del usuario
- `GET /v1/projects/{id}` — Obtener proyecto

### Jobs
- `POST /v1/jobs` — Crear job (encola procesamiento)
- `GET /v1/jobs` — Listar jobs del usuario
- `GET /v1/jobs/{id}` — Estado del job
- `GET /v1/jobs/{id}/download` — URL pre-firmada para descarga
- `POST /v1/jobs/{id}/feedback` — Re-editar con instrucciones

**Auth:** Todos los endpoints (excepto `/health`) requieren `Authorization: Bearer <jwt-supabase>`

---

## 🔄 Pipeline de procesamiento

```
1. Cliente sube vídeo a R2 (presigned URL)
2. POST /v1/jobs → encola job en Redis
3. Worker recoge job:
   ├─ 5%   → descarga input desde R2
   ├─ 15%  → concatena (si hay varios)
   ├─ 30%  → extrae audio + Whisper transcribe
   ├─ 55%  → extrae frames + GPT-4 Vision analiza
   ├─ 80%  → GPT-4 genera Production Plan (JSON)
   ├─ 92%  → FFmpeg quema subtítulos
   ├─ 96%  → render a resolución objetivo
   └─ 100% → upload resultado a R2
4. Cliente: GET /v1/jobs/{id} hasta status=completed
5. Cliente: GET /v1/jobs/{id}/download → URL para descargar
```

---

## 🐳 Deploy en EasyPanel

EasyPanel detecta `docker-compose.yml` automáticamente.

### O bien, 3 apps separadas:

1. **api** — Build: Dockerfile · Port 8000 · Domain: `api.clipso.ai`
2. **worker** — Build: Dockerfile.worker · Sin puerto público
3. **redis** — Image: `redis:7-alpine` · Sin puerto público

### Variables de entorno (mismas para api y worker):

Todas las del `.env.example` con sus valores reales.

---

## 🔐 Seguridad

- ✅ JWT Supabase verificado en cada request
- ✅ Presigned URLs con TTL de 1 hora
- ✅ Validación de tamaño y tipo de archivo
- ✅ User isolation (cada usuario solo ve sus jobs/projects)
- ✅ CORS configurado solo para dominios autorizados
- ⚠️ JWT secret en producción es OBLIGATORIO

---

## 📊 Monitoreo

```bash
# Logs en tiempo real
docker compose logs -f api worker

# Stats de cola Redis
redis-cli LLEN rq:queue:clipso-pipeline
```

---

## 📝 Licencia

© CLIPSO.AI 2026 · Todos los derechos reservados.
