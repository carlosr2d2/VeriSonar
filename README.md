# VeriSonar

Plataforma latinoamericana de análisis de voz y pistas de confiabilidad, inspirada en productos tipo DecepTech. Fase 1 opera **100% offline** (STT local + léxico ES-LATAM + acústica). Fase 2 habilita streaming en tiempo real, Kubernetes y clientes Windows/móvil.

VeriSonar **no afirma que una persona mienta**. Combina transcripción, marcadores lingüísticos regionales y rasgos acústicos para producir un índice de confiabilidad y un informe auditable.

## Arquitectura

```mermaid
flowchart LR
  UI[Next.js / Electron / RN] --> API[FastAPI]
  API --> PG[(PostgreSQL)]
  API --> Redis[(Redis)]
  Redis --> Worker[Celery workers]
  Worker --> Models[Vosk / Whisper local]
  Worker --> PG
  Worker --> PDF[Reportes PDF/JSON]
  API --> Prom[Prometheus]
  Prom --> Graf[Grafana]
```

| Servicio | Puerto | Rol |
|---|---|---|
| Frontend | 3000 | Laboratorio web |
| API | 8000 | FastAPI `/health`, `/analyze`, OpenAPI |
| Flower | 5555 | Colas Celery |
| Prometheus | 9090 | Métricas |
| Grafana | 3001 | Tablero (admin / verisonar) |
| Postgres | 5432 | Datos |
| Redis | 6379 | Broker Celery |

## Arranque

```bash
copy .env.example .env
docker compose up -d --build
```

Cuentas semilla (2 administradores y 8 analistas):

| Rol | Nombre | Correo | Clave |
|---|---|---|---|
| Administrador | Administrador VeriSonar | `admin@verisonar.local` | `VeriSonar.Admin1` |
| Administrador | Carlos Herrera | `carlos.herrera@verisonar.local` | `VeriSonar.Admin2` |
| Analista | Ana Reyes | `ana.reyes@verisonar.local` | `Analista.Reyes1` |
| Analista | Luis Gómez | `luis.gomez@verisonar.local` | `Analista.Gomez1` |
| Analista | María Soto | `maria.soto@verisonar.local` | `Analista.Soto1` |
| Analista | Diego Pérez | `diego.perez@verisonar.local` | `Analista.Perez1` |
| Analista | Camila Rojas | `camila.rojas@verisonar.local` | `Analista.Rojas1` |
| Analista | Jorge Núñez | `jorge.nunez@verisonar.local` | `Analista.Nunez1` |
| Analista | Valentina Díaz | `valentina.diaz@verisonar.local` | `Analista.Diaz1` |
| Analista | Andrés Castro | `andres.castro@verisonar.local` | `Analista.Castro1` |

Modelos STT (una vez, con red; después quedan en el volumen):

```bash
docker compose run --rm backend python scripts/download_models.py /data/models
```

Sin modelos, el pipeline igual puntúa acústica y deja la transcripción vacía.

## Hitos

1. **Backend FastAPI** — `/health`, `POST /analyze`, SQLAlchemy + Alembic, tablas `users`, `sessions`, `audio_records`, `reports` (+ `audit_logs`).
2. **Voz offline** — faster-whisper `large-v3` (prioridad; mejor en español y llamadas AMR/8 kHz) y Vosk español de respaldo; NLP léxico latinoamericano; BERT/RoBERTa opcional si hay pesos en `/data/models/nlp`.
3. **Asíncrono** — Celery + Redis, colas `audio`, `reports`, `maintenance`, workers contenedorizados.
4. **Frontend Next.js** — carga de audio, tablero de confiabilidad y estado Celery.
5. **Docker Compose** — API, web, Postgres, Redis, workers, Flower, Prometheus, Grafana.
6. **Reportes y auditoría** — PDF/JSON, logs JSON estructurados, métricas Prometheus.
7. **Windows y móvil** — `desktop/` Electron, contrato `/api/mobile/v1` y tokens push FCM.
8. **Online (fase 2)** — WebSockets `/ws/analyze/{session_id}`, overlay `docker-compose.online.yml`, manifiestos `k8s/`, HPA y balanceo.

## API útil

- `GET /health`
- `POST /api/v1/auth/login`
- `POST /api/v1/analyze` (multipart)
- `GET /api/v1/analyze/{audio_id}`
- `GET /api/v1/reports/{id}`
- `GET /metrics`
- Prefijo móvil: `/api/mobile/v1/...`

## Desarrollo local del backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set DATABASE_URL=postgresql+psycopg://verisonar:verisonar@localhost:5432/verisonar
alembic upgrade head
uvicorn app.main:app --reload
```

Pruebas del motor lingüístico:

```bash
cd backend
pytest -q
```

## Idiomas

El laboratorio está diseñado para **español latinoamericano** (muletillas MX, CO, AR, CL, PE, VE, UY). El campo `language=en` está cableado para la fase posterior de análisis en inglés.
