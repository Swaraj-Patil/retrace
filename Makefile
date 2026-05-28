.PHONY: help db-up db-down db-logs migrate-pg migrate-ch migrate seed verify reset

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
	uv run python scripts/seed.py

verify:
	uv run python scripts/verify.py

reset:
	docker compose down -v
	docker compose up -d postgres clickhouse
