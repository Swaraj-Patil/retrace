.PHONY: help db-up db-down db-logs migrate-pg migrate-ch migrate seed verify reset api-dev web-dev dev

help:
	@echo "Targets:"
	@echo "  db-up        Start Postgres and ClickHouse via Docker Compose"
	@echo "  db-down      Stop and remove containers (volumes preserved)"
	@echo "  db-logs      Tail database container logs"
	@echo "  migrate-pg   Run Postgres (Alembic) migrations"
	@echo "  migrate-ch   Run ClickHouse SQL migrations"
	@echo "  migrate      Run both migrations"
	@echo "  seed         Insert demo data and print API key"
	@echo "  verify       Print row counts for all tables"
	@echo "  reset        Drop volumes and start fresh (destructive)"
	@echo "  api-dev      Run the API in reload mode on :8000"
	@echo "  web-dev      Run the web app in dev mode on :3000"
	@echo "  dev          Run api + web together via Turbo"

db-up:
	docker compose up -d postgres clickhouse

db-down:
	docker compose down

db-logs:
	docker compose logs -f postgres clickhouse

migrate-pg:
	cd apps/api && uv run alembic upgrade head

migrate-ch:
	cd apps/api && uv run python -m api.clickhouse.migrate

migrate: migrate-pg migrate-ch

seed:
	PYTHONPATH=apps/api uv run python scripts/seed.py

verify:
	PYTHONPATH=apps/api uv run python scripts/verify.py

reset:
	docker compose down -v
	docker compose up -d postgres clickhouse

api-dev:
	cd apps/api && uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

web-dev:
	cd apps/web && pnpm dev

dev:
	pnpm run dev
