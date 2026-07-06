# Re-Fit Project Context

This file is a handoff brief for any coding agent (Codex, Claude Code, etc.)
picking up the project. Read `CLAUDE.md` first; it is the source of truth for
invariants and engineering rules. This file describes current state and where to
go next.

## Current Objective

Re-Fit is an AI-assisted resume and application-kit app. The backend is a
FastAPI service that parses resumes, extracts job requirements, scores/tailors
resumes, verifies against fabrication, renders documents, generates cover
letters/follow-ups, and tracks application kits. The frontend is a Next.js 14
app under `web/`.

**Phase 2 is complete** (generate flow, version/profile screens, dashboard
tracker, and the Phase 2 exit eval). It is committed locally and tagged
`phase-2`. **Nothing has been pushed to any remote** — the commit and tag exist
only in the local `refit` git repo. Phase 3 has not started.

The product invariant is non-negotiable:

- Never fabricate resume content.
- Never fabricate prose content.
- Candidate facts must come from the profile/resume.
- Company facts must come from the job target raw description.
- Keep `tests/test_fabrication.py` green for any change touching tailoring,
  cover letters, follow-ups, claims, prompts, or prose generation.

## Repo Shape

```text
app/
  models/       SQLAlchemy async models
  routers/      FastAPI route handlers, thin by design
  schemas/      Pydantic v2 request/response/domain models
  services/     Business logic
alembic/        Migrations
scripts/        Eval, seed, and preview scripts
templates/      Resume/prose Jinja templates (classic, compact, modern, mono)
tests/          Unit, integration, render, fabrication tests
web/            Next.js 14 frontend (App Router, TS, Tailwind)
```

## Git State (read before you commit)

- Repo root for git is `refit/` (the parent `Resume Builder/` is NOT a git repo).
- Branch: `main`. Latest commit: `c5bcbaf` ("Close Phase 2 …").
- Tag: `phase-2` points at `c5bcbaf`. There was no `phase-1` tag (the eval
  corpus is still synthetic — see "Known gaps").
- No git remote is configured / nothing is pushed. If the user wants this on
  GitHub, they must add a remote and push (`git push` + `git push --tags`).
- The Phase 2 commit is large because it folded in previously-uncommitted work
  (templates, kit, followups, versions, diffing, and the whole `web/` tree).

## Backend Stack

- Python 3.12 with `uv`
- FastAPI, SQLAlchemy 2.0 async + asyncpg, Alembic
- Postgres 16 with pgvector, Redis + Celery
- MinIO/S3-compatible document storage
- OpenAI SDK through `app/services/llm.py` only (no raw `json.loads` on model
  text anywhere else)
- Pydantic v2, Ruff + pytest

Backend runs on the host, not in Docker. Docker Compose is only for Postgres,
Redis, and MinIO.

## Frontend Stack

- `web/` — Next.js 14 App Router, TypeScript strict, Tailwind
- React Query for all server state and mutations (optimistic updates + toasts)
- `openapi-typescript` generated types (`web/src/lib/api-types.ts`), consumed via
  `openapi-fetch` in `web/src/lib/api.ts`
- pnpm via Corepack
- Testing: **Vitest + Testing Library** (component/unit) and **Playwright** (e2e)

The frontend calls FastAPI only. It never calls the LLM provider or object
storage directly. `web/src/lib/api-types.ts` is generated — regenerate with
`make api-types` (needs a running backend), do not hand-edit.

## What Phase 2 Added

### Backend

- `GET /users/{user_id}/job-targets` — lightweight list (no raw_description
  body; includes `has_requirements`, `has_kit`).
- `GET /job-targets/{job_target_id}` — full detail incl. `extracted_requirements`.
- `POST /job-targets/{id}/kit` (existing) — `KitRequest` now accepts a
  `template` in addition to `tone` + `force`. Kit generation re-renders when the
  template changes.
- `GET /applications/{id}/kit` — kit detail for the dashboard row expansion
  (resume version, cover letter with claim summary, follow-ups, presigned URLs).
- `GET /users/{id}/applications` — extended with kit availability
  (`ats_score`, `resume_pdf_ready`, `has_cover_letter`, `followup_count`,
  `last_activity_at`).
- **Kit generation is synchronous**: `create_or_get_kit` runs tailor + score +
  cover letter + render inline and returns the full `KitResult`. Pipeline runs
  (`/pipeline/runs`) are for the upload→parse→tailor flow only, NOT kit gen. The
  frontend "progress stepper" is a client-side staged indicator over that single
  request, not a real poll.
- `scripts/eval_phase1.py` gained a `--phase2` mode (+ `--limit N`). See
  "Key Commands".

### Frontend routes (all in `web/src/app/`)

- `/dashboard` — application tracker. Table (company/role, status pipeline,
  applied date, ATS badge, kit indicators, last activity), status filter chips,
  row expansion into the kit view. Deep-link `?application=<id>` auto-expands.
- `/job-targets` — list + "New job target" form.
- `/job-targets/[id]` — detail: requirements chips (weight + JD-evidence
  tooltip), JD text, and the **Generate kit** flow (tone + template pickers →
  staged progress → kit view with before→after score count-up → "Track
  application" which creates a draft Application and deep-links to its dashboard
  row).
- `/versions` — history list (score badges, job-target context).
- `/versions/[id]` — enriched diff (before/after bullet pairs grouped by role,
  requirement-targeted tags, unchanged count collapsed) + compare picker.
- `/profile` — editable structured resume form (contact, experience with bullet
  textareas, skills groups) + upload→parse bootstrap. PUT maps 422 field errors
  to inputs.

Shared UI: `web/src/components/ui/toast.tsx`, `.../ui/markdown.tsx`,
`.../kit/score-countup.tsx`. Pure domain logic (status/follow-up gating,
date/score formatting) is in `web/src/lib/applications.ts`.

## Key Commands

Dependencies / migrations / servers:

```bash
make up                       # docker: postgres, redis, minio
uv run alembic upgrade head
make dev                      # FastAPI on :8100
make worker                   # Celery
make dev-web                  # Next.js (defaults to :3000)
make api-types                # regen web/src/lib/api-types.ts (backend must be up)
```

Seeds (both idempotent, no LLM calls; need Postgres + MinIO up):

```bash
uv run python -m scripts.seed             # minimal demo (user + one applied app)
uv run python -m scripts.seed_dashboard   # full demo kit for the dashboard
```

Backend checks:

```bash
uv run ruff check .
uv run pytest
```

Phase 2 eval (real LLM — costs OpenAI credits; bound it with LIMIT):

```bash
make eval-phase2            # full corpus (10 synthetic pairs)
make eval-phase2 LIMIT=2    # bounded smoke; report still asserts cleanliness
```

Frontend tests:

```bash
cd web && corepack pnpm run typecheck
cd web && corepack pnpm exec vitest run          # component/unit
cd web && corepack pnpm exec playwright test     # e2e (see ports below)
```

## Local Ports

- FastAPI: `http://localhost:8100` (OpenAPI at `/openapi.json`, docs at `/docs`)
- Next dev (`make dev-web`): `http://localhost:3000`
- **Playwright e2e dev server: `http://localhost:3200`** — chosen because
  3000/3001/3100 are all occupied by other local apps on this machine. Port 3200
  (and 127.0.0.1:3200) is in the backend CORS allowlist (`app/config.py`).
  `web/playwright.config.ts` uses `reuseExistingServer: false` deliberately so it
  never latches onto an unrelated app already on a port.

## Testing Notes / Gotchas

- Tests run against real Postgres `refit_test`. Never SQLite, never mock the DB.
- Real-LLM tests: `test_jd_extraction`, `test_parse_integration` (and the eval /
  Playwright `phase2` spec) hit the live OpenAI API. Everything else mocks the
  LLM via monkeypatch.
- **As of the Phase 2 close, `uv run pytest` showed 7 failures from live-provider
  billing/credit exhaustion** — the eval + e2e runs exhausted the account's
  credits. These were the 7 real-LLM tests; the other 64 passed. Add live OpenAI
  credits and re-run to confirm green. This is a billing state, not a regression.
- Vitest gotcha: `web/vitest.setup.ts` registers `afterEach(cleanup)` explicitly
  because auto-cleanup only runs with `globals: true` (which we don't set).
- The `openapi-fetch` client in `web/src/lib/api.ts` passes
  `fetch: (...args) => globalThis.fetch(...args)` so tests can stub the global
  fetch (openapi-fetch otherwise binds fetch at client-creation time).
- Playwright `web/e2e/global-setup.ts` reseeds via `scripts.seed_dashboard`
  before the run.
- User emails ending in `.local` are rejected by `EmailStr` at the API boundary
  (`POST /users`), even though the seed uses `demo@refit.local` (the seed calls
  the service directly, bypassing the schema). Use `@example.com` in e2e/API
  tests.

## Verification Snapshot (Phase 2 close)

- `uv run ruff check .` — clean.
- `uv run pytest` — 64 passed, 7 failed (all live-provider credit exhaustion; see
  above).
- `make eval-phase2 LIMIT=1` — exit 0; cover letter 289 words (in 250–350
  range), 0 claim violations, all 4 templates round-trip pdf+docx. Report in
  `eval_reports/phase2_*.md` (dir is gitignored).
- `cd web && pnpm run typecheck` — clean.
- Vitest — 15 passed (status control optimistic flip + rollback, follow-up
  gating, applications domain logic).
- Playwright `dashboard.spec.ts` — green. `phase2.spec.ts` (upload → job target
  → kit → track → dashboard, real LLM) — green.
- Screenshots (gitignored, regenerate by re-running the specs):
  `web/e2e/artifacts/dashboard-expanded.png`, `.../kit-generated.png`.

## Current Dev Auth (still a stub — Phase 3 target)

- `GET /users` lists users for the frontend picker; selected id in `localStorage`
  (`refit.devUserId`). Marked `// DEV AUTH: replace in Phase 3.`
- `UserCreate.email` validates as `EmailStr`; `UserRead.email` is a plain string
  because the seeded `demo@refit.local` row is not a valid `EmailStr`.

## Known Gaps / Next Likely Work (Phase 3+)

1. **Real auth** replacing the dev-user stub (the biggest Phase 3 item).
2. **Real eval corpus**: `tests/corpus` still has only 2 synthetic resumes × 5
   JDs. CLAUDE.md's Phase 1 exit ritual (≥10 real resumes, ≥5 real JDs) was never
   satisfied, which is why there's no `phase-1` tag. A meaningful eval needs real
   corpus; update `tests/corpus/pairs.yaml`.
3. Async kit generation with a real progress poll (currently synchronous; the UI
   stepper is cosmetic).
4. Profile form covers contact/experience/skills; education and projects are
   preserved on save but not editable in the UI yet.
5. Version detail shows changed bullets only; unchanged bullets are a collapsed
   count (the enriched diff payload doesn't carry unchanged bullet text).

## Safety Notes

- Never edit corpus files just to make tests pass.
- Never mock the database in tests; tests use real Postgres `refit_test`.
- Do not add raw LLM JSON parsing outside `app/services/llm.py`.
- Do not introduce frontend calls to storage, OpenAI, or any backend-internal
  service. Use generated OpenAPI types for frontend API work.
- If changing prompts or verification logic, add/extend fabrication tests first.
- Keep routers thin; business logic in `app/services/`.
