.PHONY: up down dev dev-web worker test lint eval eval-phase2 api-types

up:
	docker compose up -d --wait

down:
	docker compose down

# 8000 is occupied by another local app ("Re: Call")
dev:
	uv run uvicorn app.main:create_app --factory --reload --port 8100

dev-web:
	cd web && corepack pnpm dev

worker:
	uv run celery -A app.worker:celery_app worker --loglevel=info --pool=solo

test:
	uv run pytest

lint:
	uv run ruff check . && uv run ruff format --check .

eval:
	uv run python -m scripts.eval_phase1

# Phase 2 exit check: full kit (tailor + cover letter + all-format renders) per
# corpus pair, with letter excerpts for manual fabrication review. Set LIMIT=N
# to bound cost while smoke-testing (e.g. make eval-phase2 LIMIT=2).
eval-phase2:
	uv run python -m scripts.eval_phase1 --phase2 $(if $(LIMIT),--limit $(LIMIT),)

api-types:
	cd web && corepack pnpm exec openapi-typescript http://localhost:8100/openapi.json -o src/lib/api-types.ts
