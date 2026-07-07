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

**The fabrication boundary extends to ATS short-answer form responses.**
Short answers like "why this company" or "why this role" follow the same
evidence-pack + `verify_prose` discipline as cover letters — grounded only in
the user's profile and the job target's `raw_description`. But some form
fields are **facts only the user knows** — salary expectation, work
authorization, sponsorship needs, notice period — not facts the LLM can
derive from evidence. For these, the system must never guess a
plausible-sounding default. A missing `AnswerProfile` field renders as an
explicit "add this" prompt to the user, never a filled-in guess.

## Domain concepts

- An **ApplicationKit** is the bundle for one job target: tailored resume version,
  cover letter, and follow-up email.
- The ApplicationKit, not the resume alone, is the unit users generate and the
  tracker displays.
- An **AnswerProfile** holds durable, user-owned facts that are not part of the
  resume but are needed on every application form: work authorization status,
  sponsorship needs, salary expectation/range, willingness to relocate, notice
  period, pronouns, veteran/disability/EEO self-ID preferences, and a default
  referral source. It is stored once per user and reused across every kit —
  this is the single biggest time-save in the assisted-apply flow. Never make
  the user retype it.
- Common ATS form schemas (Greenhouse, Lever, Ashby field taxonomies) are a
  known, finite set — encode them directly as reference data rather than
  re-deriving field structure per job application.

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
- The assisted-apply kit UI is copy-heavy (one-click-copy fields for answer
  profile values and short answers): use the Clipboard API via a small shared
  `useCopyField` hook, and always show a toast confirmation per field — never
  a silent copy.

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
  - `OPENAI_API_KEY`

## LLM usage

- All LLM calls go through **one module**: `app/services/llm.py`, using the
  OpenAI SDK with structured outputs validated
  against Pydantic schemas from `app/schemas/`. **No raw `json.loads` on model
  text anywhere else in the codebase.** The single credential is
  `OPENAI_API_KEY`; a key that is empty or starts with `change` (the
  `.env.example` placeholder) is treated as "no real key" by
  `llm.is_placeholder_key`. Embeddings are a **local** model
  (`sentence-transformers`, `app/services/embeddings.py`) with **no** API key or
  network dependency — do not conflate the two.
- Every LLM-calling function takes an optional model override and returns both
  the parsed object and usage metadata (input/output tokens). Log usage.
- Retry policy: max 2 retries on validation failure, re-prompting with the
  validation error included. After that, raise a typed exception — **never
  return partially-valid data**.
- **Heuristic fallback is explicit and opt-in, never silent.** JD extraction
  (`jd.extract_requirements`) has a deterministic keyword approximation
  (`jd.extract_requirements_heuristic`) for key-less environments. It is used
  **only** when a caller passes `heuristic_fallback=True` **and** the key is
  placeholder-shaped. With a placeholder key and no opt-in, it raises
  `MissingLLMCredentialsError` — it never degrades silently, and a real-key
  failure (timeout/rate-limit/validation) always takes the normal
  retry-then-typed-error path. Heuristic output is tagged
  `JobRequirements.source == "heuristic"` with `[heuristic]`-prefixed evidence.
  The opt-in decision belongs to a **script/task caller** (e.g. the eval scripts'
  `--allow-heuristic`), never to a service like `matching.py`. Eval scripts
  refuse to run on a placeholder key without `--allow-heuristic` and stamp
  "HEURISTIC MODE" into the report header.
- **PRODUCT INVARIANT (repeated on purpose):** the tailoring engine must never
  fabricate experience, skills, employers, dates, metrics, company facts, mutual
  connections, or prose backstory. Any pipeline change touching tailoring, cover
  letters, or follow-up emails must keep `tests/test_fabrication.py` green.

## Rendering

- Resumes render through Jinja2 -> WeasyPrint for PDF and python-docx for DOCX.
- Rendered prose documents, including cover letters, use the same render
  pipeline: Jinja2 -> WeasyPrint for PDF and python-docx for DOCX.
- Follow-up emails are copy-paste artifacts; they are not rendered to PDF.

## Phase 4: job aggregation — SCOPE LOCK

This phase has a documented tendency to balloon into "search every job on the
internet." The boundary below is written **before any code exists** and is
binding. Treat scope expansion here the way you treat fabrication: not a
default extension of the pattern, but a deliberate decision to revisit.

### Sources — capped allow-list

Only these sources may be ingested. This list is the whole of Phase 4's source
surface:

1. **Greenhouse Job Board API** — `boards-api.greenhouse.io`. Public, no auth.
   Per-board listing only.
2. **Lever Postings API** — `api.lever.co/v0/postings/{site}`. Public, no auth.
   Per-site listing only.
3. **Company career RSS/Atom feeds** — a **user-curated** list of feed URLs.
   Feeds are registered explicitly; they are **not** discovered or crawled.
4. **Ashby** — **stretch goal ONLY**, and only once Greenhouse + Lever are
   stable in production. Do **not** start Ashby in this phase unless a request
   explicitly asks for it. Absent that, Ashby is out of this phase.

### Out of scope — permanently, not "later"

LinkedIn, Indeed, ZipRecruiter, or **any** source that requires login,
scraping, or ToS-gray-area access are **out of scope permanently**. This is a
product-level boundary carrying the **same weight as the no-fabrication rule**.
A future request to add a scraped or login-gated source is a decision to
revisit this boundary deliberately — never a default extension of the
Greenhouse/Lever ingestion pattern.

### Ingestion is per-company, not global search

Users (or the system, from a seed list — see `WATCHED_BOARDS.md`) register
specific companies/boards to watch as **SourceBoards**. There is no
"search all jobs everywhere" surface, and there is no cross-company search
call, because Greenhouse and Lever expose **no cross-company search API** —
only per-board / per-site listing. This constraint is the design, not a
limitation to engineer around.

### SourceBoard health — degrade, never fail loud-forever or silent

A SourceBoard can go stale: board deleted, company acquired, API 404s
repeatedly. Ingestion must:

- Track per-board health and **degrade a repeatedly-failing board to
  `unhealthy`**, then **stop hammering it** (back off / skip on schedule).
- **Never fail loudly forever** — one dead board must not break the run or
  spam errors every cycle.
- **Never fail silently** — an `unhealthy` board must be visible in state so
  the user can see it needs attention and re-verify or remove it.

### Match scoring — reuse Phase 1 scorer as-is

Match scoring for aggregated jobs **reuses `app/services/embeddings.py` and
`app/services/score.py` from Phase 1 as-is**. No new scoring logic in this
phase — aggregated jobs are simply **new inputs to the same scorer**. If
scoring seems to need changes, that is a signal to stop and reconsider, not to
fork the scorer.

- **Posting visibility for a saved_search is always scoped to the user's own
  source_boards plus system/seed boards (`user_id IS NULL`) — this is an
  invariant, not a filter to be optionally applied.** It is enforced at both
  scoring and read time via `matching.visible_board_condition`
  (`score_posting_for_search`/`refresh_matches_for_search`, `list_matches`, and
  `digest.build_digest` all AND it in). Because the read-time join is against
  boards *currently* owned/system, unwatching (deleting) a source_board
  immediately drops its postings from matches and digests with no cleanup job.

### Digest generation and delivery are separate concerns

`app/services/digest.py` **generates** digests (computes new matches, persists a
`digests` row) and knows nothing about **delivery**. There is intentionally no
email/push/in-app sending in the digest logic — `send_daily_digest_task` only
generates and persists. Delivery is a downstream concern layered on the
persisted `digests` rows, so channels (email, push, in-app only, Slack, …) can
be added or swapped without touching generation. Do not reach into digest
generation to send anything; add a delivery layer that reads `digests` instead.
The `digests.*` naming keeps "send" as a scheduling label, not an instruction to
transmit from within this module.

### Recurring jobs (Celery beat, `app/worker.py`)

Ingestion runs every 6h; rescoring runs 1h after each ingestion (so it scores
what was just written, reusing the per-posting skip logic); freshness cleanup
and the digest run daily. Board fetches are **concurrency-capped and staggered**
(`ingest_concurrency`, `ingest_stagger_seconds`) — never fan out to every board
at once; we are a guest on these public APIs.

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
