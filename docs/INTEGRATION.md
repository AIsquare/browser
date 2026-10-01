# Integration

The web app communicates with the Python pipeline API over HTTP. Keep both applications running locally while using the research workflow.

## Job lifecycle

- `POST /jobs` submits selected URLs and an optional search topic.
- `GET /jobs/{job_id}` returns queued/running progress, or the completed article ID.
- `GET /articles/{article_id}` returns the synthesized article.
- The API enqueues work in Redis; `worker.py` consumes it and runs the pipeline.

## Configuration

Set `DATABASE_URL`, `DATABASE_URL_SIGNAL`, `REDIS_URL`, `TOGETHER_API_KEY`, and `TYPESAFE_API_KEY` in `apps/pipeline/.env`. Optional synthesis settings include `TOGETHER_MODEL`, `TYPESAFE_MODEL`, `SYNTH_TEMPERATURE`, `SYNTH_TOPIC`, and `SYNTH_DRY_RUN`.

Never commit `.env`; use `.env.example` as the placeholder template. Start the API and worker from `apps/pipeline`, and the web dev server from `apps/web` so relative file paths resolve as expected.
