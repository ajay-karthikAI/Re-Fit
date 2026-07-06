# Re-Fit Project Context

This file is a handoff brief for Claude Code or any coding agent picking up the
project. Read `CLAUDE.md` first; it is the source of truth for invariants and
engineering rules.

## Current Objective

Re-Fit is an AI-assisted resume and application-kit app. The backend is a
FastAPI service that parses resumes, extracts job requirements, scores/tailors
resumes, verifies against fabrication, renders documents, generates cover
letters/follow-ups, and tracks application kits. Phase 2 has begun with a
Next.js frontend scaffold under `web/`.

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
scripts/        Eval and preview scripts
templates/      Resume/prose Jinja templates
tests/          Unit, integration, render, fabrication tests
web/            Phase 2 Next.js frontend scaffold
```

## Backend Stack

- Python 3.12 with `uv`
- FastAPI
- SQLAlchemy 2.0 async + asyncpg
- Alembic
- Postgres 16 with pgvector
- Redis + Celery
- MinIO/S3-compatible document storage
- Anthropic SDK through `app/services/llm.py` only
- Pydantic v2
- Ruff + pytest

Backend app runs on the host, not in Docker. Docker Compose is only for
Postgres, Redis, and MinIO.

## Frontend Stack

- `web/`
- Next.js 14 App Router
- TypeScript strict
- Tailwind
- React Query
- `openapi-typescript` generated API types
- `openapi-fetch` typed client
- pnpm via Corepack

The frontend must call FastAPI only. It must never call the LLM provider or
object storage directly.

Current frontend scaffold includes:

- Dark default shell
- Sidebar/topbar navigation
- Empty routes: `/dashboard`, `/job-targets`, `/versions`, `/profile`
- Dashboard health panel using `/health`
- Dev user picker using `GET /users`
- Dev auth context stored in `localStorage`
- API base URL from `NEXT_PUBLIC_API_BASE_URL`, defaulting to
  `http://localhost:8100`

## Important Recent Work

The working tree contains substantial uncommitted Phase 2 work. Do not revert
or overwrite it casually.

Recent backend features present in the tree:

- Resume template registry and four template families:
  `classic`, `compact`, `modern`, `mono`
- ResumeVersion `template_id` / `template_variables`
- Version-history backend:
  - `GET /profiles/{id}/versions`
  - `GET /versions/{id}/diff`
  - `GET /versions/{a}/compare/{b}`
  - soft-delete `DELETE /versions/{id}`
  - `score_cache` on ResumeVersion
- Pure resume diffing in `app/services/diffing.py`
- Cover letter generation/rendering
- Follow-up generation
- Kit composite endpoint
- Frontend scaffold in `web/`
- CORS configured for local frontend origins
- `GET /users` dev-auth list endpoint

Because the worktree is dirty, always inspect files before editing. Preserve
unrelated changes.

## Key Commands

Start dependencies:

```bash
make up
```

Run migrations:

```bash
uv run alembic upgrade head
```

Run FastAPI:

```bash
make dev
```

Run Celery:

```bash
make worker
```

Run frontend:

```bash
cd web
corepack pnpm install
cd ..
make dev-web
```

Generate frontend API types from a running backend:

```bash
make api-types
```

Run tests and checks:

```bash
uv run ruff check .
uv run pytest
cd web && corepack pnpm run typecheck
cd web && corepack pnpm run build
```

Note: `uv run ruff format --check .` currently reports two older Alembic files
that Ruff would reformat. This predates the frontend handoff; do not reformat
unrelated migrations unless the user asks for formatting cleanup.

## Local Ports

- FastAPI: `http://localhost:8100`
- OpenAPI: `http://localhost:8100/openapi.json`
- Docs: `http://localhost:8100/docs`
- Next.js default: `http://localhost:3000`

In the last session, port `3000` was occupied by another unrelated Next app, so
Next automatically used `http://localhost:3001`. CORS currently allows both
3000 and 3001 local origins.

## Frontend Files To Know

```text
web/package.json
web/pnpm-lock.yaml
web/src/app/layout.tsx
web/src/app/globals.css
web/src/app/dashboard/page.tsx
web/src/app/job-targets/page.tsx
web/src/app/versions/page.tsx
web/src/app/profile/page.tsx
web/src/components/providers/app-providers.tsx
web/src/components/providers/dev-user-provider.tsx
web/src/components/shell/app-shell.tsx
web/src/components/shell/user-picker.tsx
web/src/components/dashboard/health-panel.tsx
web/src/lib/api.ts
web/src/lib/api-types.ts
```

`web/src/lib/api-types.ts` is generated. Do not hand-edit it except as a
temporary bootstrap placeholder; regenerate with `make api-types`.

## Backend Files To Know

```text
app/main.py
app/config.py
app/routers/users.py
app/services/users.py
app/services/claims.py
app/services/tailor.py
app/services/cover_letter.py
app/services/followup.py
app/services/kit.py
app/services/render.py
app/services/score.py
app/services/templates.py
app/services/versions.py
app/services/diffing.py
app/services/score_cache.py
```

Keep routers thin. Add business logic in `app/services/`.

## Verification Snapshot

Most recent verification from the frontend scaffold session:

- `uv run ruff check .` passed
- `uv run pytest` passed: 66 passed, 5 warnings
- `corepack pnpm run typecheck` passed
- `corepack pnpm run build` passed
- `make api-types` passed against live FastAPI
- `/health` returned `{"status":"ok","postgres":"ok","redis":"ok"}`
- `/users` returned seeded dev users including `demo@refit.local`

## Current Dev Auth

Auth is intentionally a development stub.

- `GET /users` lists users for the frontend picker.
- The selected user id is stored in browser `localStorage`.
- Code is marked with `// DEV AUTH: replace in Phase 3.`
- `UserCreate.email` still validates as `EmailStr`.
- `UserRead.email` is a plain string because an existing dev row uses
  `demo@refit.local`, which Pydantic rejects as an `EmailStr` response.

## Next Likely Work

The frontend scaffold is intentionally screen-light. Good next steps:

1. Build the Job Targets list/create screen using React Query and generated API
   types.
2. Build the Versions history screen using the version-history endpoints.
3. Build the Profile upload/profile review screen.
4. Add reusable UI primitives only as screens demand them.
5. Keep the visual direction restrained: dark, typographic, no gradients, no
   glassmorphism, no decorative filler.

## Safety Notes

- Never edit corpus files just to make tests pass.
- Never mock the database in tests; tests use real Postgres `refit_test`.
- Do not add raw LLM JSON parsing outside `app/services/llm.py`.
- Do not introduce frontend calls to storage, Anthropic, or any backend-internal
  service.
- Use generated OpenAPI types for frontend API work.
- If changing prompts or verification logic, add/extend fabrication tests first.
