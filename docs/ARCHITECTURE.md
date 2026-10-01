# Architecture

The platform has two independently run applications. The web app provides the research UI and forwards pipeline requests to the Python API. The API queues work in Redis; an RQ worker runs the long-lived pipeline. Postgres stores source documents, atoms, buckets, articles, and job-selection signals.

## Request flow

1. The user searches, selects source URLs, and requests synthesis in `apps/web`.
2. The web server sends the selected URLs and topic to `apps/pipeline` over HTTP.
3. The API records selection events and enqueues a job in Redis.
4. The worker crawls the URLs, parses content into blocks, loads documents into Postgres, classifies sections, buckets atoms, and synthesizes an article.
5. The web app polls the API for job status and fetches the completed article.

## Process boundaries

- Web development server: port 3000; run with `apps/web` as the working directory.
- Pipeline API: `127.0.0.1:8000`.
- RQ worker: a separate process, also launched with `apps/pipeline` as the working directory.
- Database and service credentials: local-only `apps/pipeline/.env`, based on `.env.example`.

## Data boundaries

Pipeline files under `extracted/`, `data/`, `jobs/`, and `test_run/` are generated local data and are excluded from Git. SQLite databases used by legacy inspection and test scripts are also local-only. The running API and worker use the configured Postgres and Redis services.
