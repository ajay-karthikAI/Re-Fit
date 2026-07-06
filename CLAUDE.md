# refit

AI resume tailoring app — FastAPI backend.

## Product invariant

**Never fabricate resume content.** The app tailors, rephrases, and reorders what
the user actually did; it must never invent experience, skills, titles, dates,
metrics, or accomplishments that are not present in the user's source material.
This applies to all AI prompts, services, and tests. Treat any code path that
could add unsourced content to a resume as a bug.

**Never fabricate prose content.** Cover letters and follow-up emails may only
reference experience present in the user's profile. They may only state facts
about the company that appear verbatim or near-verbatim in the job target's
`raw_description`. Do not invent company praise, mutual connections, personal
backstory, or enthusiasm narratives. Phrases like "your award-winning platform"
are bugs unless the job target itself says that. `tests/test_fabrication.py`
must include prose fabrication cases and must stay green.

## Domain concepts

- An **ApplicationKit** is the bundle for one job target: tailored resume version,
  cover letter, and follow-up email.
- The ApplicationKit, not the resume alone, is the unit users generate and the
  tracker displays.

## Tooling

- Python 3.12, managed with **uv** (`uv init`, `uv add`, `uv run`). No pip, no poetry.
- **Ruff** for lint and format (`uv run ruff check`, `uv run ruff format`).
- Type hints are mandatory on all function signatures.

## Stack

- **FastAPI** for the API.
- **SQLAlchemy 2.0** in async mode with **asyncpg** as the driver.
- **Alembic** for database migrations.
- **Pydantic v2** everywhere.
- Postgres 16 and Redis 7 for local dev run via `docker-compose`. The app itself
  runs on the host with uv — do **not** dockerize the app.
- Postgres uses the `pgvector/pgvector:pg16` image (the stock `postgres:16`
  image does not ship the `vector` extension).

## Project layout

- `app/schemas/` — Pydantic models (request/response and internal schemas)
- `app/models/` — SQLAlchemy models
- `app/routers/` — API routes (thin; no business logic)
- `app/services/` — business logic
- `web/` — Phase 2 frontend, Next.js 14 App Router + TypeScript + Tailwind
- `tests/` — pytest tests

## Frontend

- The Phase 2 frontend lives in `web/` at the repo root.
- Use Next.js 14 App Router, TypeScript, and Tailwind.
- The frontend never calls the LLM or storage directly. FastAPI is the only
  backend boundary.
- API types are generated from the FastAPI OpenAPI schema with
  `openapi-typescript`; regenerate them with `make api-types`.

## Database conventions

- All IDs are **UUIDv4**, server-generated.
- Every table gets `created_at` and `updated_at` columns: `timestamptz` with
  server-side defaults.

## Configuration

- Config is loaded via **pydantic-settings** from a `.env` file.
- `.env.example` is committed; `.env` is gitignored.
- Required variables:
  - `DATABASE_URL`
  - `REDIS_URL`
  - `S3_BUCKET`
  - `S3_ENDPOINT_URL`
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - `ANTHROPIC_API_KEY`

## LLM usage

- All LLM calls go through **one module**: `app/services/llm.py`, using the
  Anthropic SDK with structured outputs (tool-use or response_format) validated
  against Pydantic schemas from `app/schemas/`. **No raw `json.loads` on model
  text anywhere else in the codebase.**
- Every LLM-calling function takes an optional model override and returns both
  the parsed object and usage metadata (input/output tokens). Log usage.
- Retry policy: max 2 retries on validation failure, re-prompting with the
  validation error included. After that, raise a typed exception — **never
  return partially-valid data**.
- **PRODUCT INVARIANT (repeated on purpose):** the tailoring engine must never
  fabricate experience, skills, employers, dates, metrics, company facts, mutual
  connections, or prose backstory. Any pipeline change touching tailoring, cover
  letters, or follow-up emails must keep `tests/test_fabrication.py` green.

## Rendering

- Resumes render through Jinja2 -> WeasyPrint for PDF and python-docx for DOCX.
- Rendered prose documents, including cover letters, use the same render
  pipeline: Jinja2 -> WeasyPrint for PDF and python-docx for DOCX.
- Follow-up emails are copy-paste artifacts; they are not rendered to PDF.

## Testing

- **pytest** + **pytest-asyncio**, tests live in `tests/`.
- Tests run against a real Postgres test database (`refit_test`) — never SQLite.
- **Never mock the database.**
- Test corpus lives in `tests/corpus/`: real-world resume files (PDF/DOCX) in
  `resumes/` and job descriptions (txt) in `jds/`. Corpus files are fixtures —
  **never edit them to make tests pass**.

## Phase 1 exit ritual

Before tagging Phase 1 complete:

1. Drop at least 10 real resumes into `tests/corpus/resumes/` and at least 5
   real job descriptions into `tests/corpus/jds/`.
2. Replace the synthetic matrix in `tests/corpus/pairs.yaml` with the real
   resume/JD pairs to evaluate.
3. Run `docker compose up -d --wait` and `uv run alembic upgrade head`.
4. Run `make eval`.
5. Manually inspect every accepted rewrite diff in the generated
   `eval_reports/{timestamp}.md` report for fabrication or unsupported claims.
6. Only after the report passes and the diffs are clean, tag `phase-1`.
