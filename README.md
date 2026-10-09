# Research Platform

Turns user-selected URLs into one synthesized article.

## Structure

- `apps/web` — Node/Express + React UI
- `apps/pipeline` — Python pipeline (crawl → parse → load → outline → synthesize)
- `docs/` — architecture and integration notes

## Running locally

Use three terminals.

### Python API

```powershell
cd apps/pipeline
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

### Worker

```powershell
cd apps/pipeline
python worker.py
```

### UI

```powershell
cd apps/web
npm run dev
```

Open http://localhost:3000.

Synthesis requires the Python API and worker to be running. If the API is
unavailable, the UI reports the connection error; it does not generate a
simulated article.

## Prerequisites

- Python 3.11+
- Node 20+
- Postgres (Neon), configured with `DATABASE_URL` and `DATABASE_URL_SIGNAL`
- Redis (Upstash), configured with `REDIS_URL`
- Together API key, configured with `TOGETHER_API_KEY`
- TypeSafe API key, configured with `TYPESAFE_API_KEY`

Copy `apps/pipeline/.env.example` to `apps/pipeline/.env` and fill in the values.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
