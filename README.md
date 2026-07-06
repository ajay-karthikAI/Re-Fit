# Re-Fit

AI-assisted resume and application-kit backend built around one hard rule: never
fabricate candidate experience.

Re-Fit parses resumes, extracts job requirements, embeds and scores resume
content, safely tailors weak resume bullets, renders ATS-friendly documents, and
generates evidence-checked cover letters. The current repository is a FastAPI
backend; the Next.js frontend is planned for Phase 2 under `web/`.

## What It Does

- Parses uploaded PDF/DOCX resumes into a structured canonical profile.
- Extracts weighted job requirements from raw job descriptions.
- Scores resumes against a target job with deterministic ATS-style subscores.
- Tailors existing resume bullets using LLM rewrites plus deterministic claim
  verification.
- Renders resumes and cover letters to PDF/DOCX.
- Runs the full parse -> tailor -> score -> render pipeline through Celery.
- Produces Phase 1 eval reports across corpus resume/JD pairs.

## Fabrication Invariant

Re-Fit may rephrase, reorder emphasis, and surface relevance that is already
present. It must not invent employers, titles, dates, tools, metrics, team
sizes, outcomes, company praise, mutual connections, or personal backstory.

The invariant is enforced in code by `app/services/claims.py` and protected by
`tests/test_fabrication.py`.

## Stack

- Python 3.12
- FastAPI
- SQLAlchemy 2.0 async + asyncpg
- Alembic
- Postgres 16 with pgvector
- Redis + Celery
- MinIO/S3-compatible document storage
- Anthropic SDK for structured LLM calls
- Jinja2 + WeasyPrint for PDF rendering
- python-docx for DOCX rendering
- pytest, pytest-asyncio, Ruff
- uv for dependency management

## Quick Start

```bash
git clone https://github.com/ajay-karthikAI/Re-Fit.git
cd Re-Fit
cp .env.example .env
uv sync
docker compose up -d --wait
uv run alembic upgrade head
make dev
```



Config is loaded from `.env` via `pydantic-settings`.

```dotenv
DATABASE_URL=postgresql+asyncpg://refit:refit@localhost:5434/refit
REDIS_URL=redis://localhost:6379/0
S3_BUCKET=refit-dev
S3_ENDPOINT_URL=http://localhost:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
ANTHROPIC_API_KEY=changeme
```

Local MinIO creates the target bucket on first storage use. Set a real
`ANTHROPIC_API_KEY` for LLM-backed extraction, tailoring, cover letters, and the
full eval harness.

## Common Commands

```bash
make up        # Start Postgres, Redis, and MinIO
make down      # Stop local services
make dev       # Start FastAPI on port 8100
make worker    # Start the Celery worker
make test      # Run pytest
make lint      # Run Ruff lint + format check
make eval      # Run the Phase 1 corpus eval harness
```

## API Surface

Primary routes:

- `POST /users`
- `PUT /users/{user_id}/profile`
- `GET /users/{user_id}/profile`
- `POST /users/{user_id}/uploads`
- `POST /uploads/{upload_id}/parse`
- `POST /users/{user_id}/job-targets`
- `POST /job-targets/{job_target_id}/extract`
- `POST /profiles/{profile_id}/versions`
- `POST /profiles/{profile_id}/tailor`
- `GET /versions/{version_id}/score`
- `POST /versions/{version_id}/render`
- `POST /pipeline/runs`
- `GET /pipeline/runs/{run_id}`
- `POST /job-targets/{job_target_id}/cover-letter`
- `POST /cover-letters/{cover_letter_id}/render`
- `POST /users/{user_id}/applications`
- `GET /users/{user_id}/applications`
- `PATCH /applications/{application_id}`

The OpenAPI schema is available from the running app at `/openapi.json`.

## Pipeline

`app/services/pipeline.py` orchestrates the Phase 1 flow:

1. Parse an uploaded resume.
2. Extract job requirements if they are not cached.
3. Generate embeddings.
4. Tailor the resume.
5. Score before and after versions.
6. Render the tailored PDF.
7. Persist a `PipelineRun` with status, stage, timings, scores, version ID, and
   download URL.

The API enqueues this work through Celery:

```http
POST /pipeline/runs
```

The task wrapper lives in `app/worker.py`; the service internals stay
synchronous/awaitable and testable.

## Testing

Run all tests:

```bash
make test
```

The tests use a real Postgres test database (`refit_test`) created by
`docker/postgres-init/01-create-test-db.sql`. They do not use SQLite and should
not mock the database layer.

The corpus fixtures live under `tests/corpus/`. Synthetic resumes and job
descriptions are placeholders until real sanitized files are added.

## Eval Harness

Run:

```bash
make eval
```

The harness reads `tests/corpus/pairs.yaml`, runs each resume/JD pair through the
full pipeline, and writes a markdown report to `eval_reports/{timestamp}.md`.

The script fails if:

- any accepted rewrite violates claim verification,
- any score delta is negative,
- any pipeline stage errors.

Phase 1 exit ritual:

1. Add at least 10 sanitized real resumes to `tests/corpus/resumes/`.
2. Add at least 5 sanitized real JDs to `tests/corpus/jds/`.
3. Replace the synthetic pairs in `tests/corpus/pairs.yaml`.
4. Run `make eval`.
5. Manually inspect every accepted rewrite diff for fabrication.
6. Tag `phase-1` only after the report and diffs are clean.

## Project Layout

```text
app/
  models/       SQLAlchemy models
  routers/      FastAPI routes
  schemas/      Pydantic request, response, and domain schemas
  services/     Business logic
alembic/        Database migrations
docker/         Local database init scripts
scripts/        Corpus generation, seed, and eval helpers
templates/      Resume and prose document templates
tests/          Unit, integration, render, and fabrication tests
```

## Document Rendering

The classic resume template lives in `templates/resume/classic/`.

- PDF: Jinja2 -> HTML -> WeasyPrint
- DOCX: python-docx with native Word headings
- Resumes and cover letters can render to PDF/DOCX
- Follow-up emails are copy-paste artifacts and are not rendered to PDF

## Frontend Status

The frontend is not committed yet. Phase 2 calls for a Next.js 14 App Router app
with TypeScript and Tailwind under `web/`. The frontend must call FastAPI only;
it should never call the LLM provider or object storage directly.

