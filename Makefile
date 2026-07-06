.PHONY: up down dev worker test lint eval

up:
	docker compose up -d --wait

down:
	docker compose down

# 8000 is occupied by another local app ("Re: Call")
dev:
	uv run uvicorn app.main:create_app --factory --reload --port 8100

worker:
	uv run celery -A app.worker:celery_app worker --loglevel=info --pool=solo

test:
	uv run pytest

lint:
	uv run ruff check . && uv run ruff format --check .

eval:
	uv run python -m scripts.eval_phase1
