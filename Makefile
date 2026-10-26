.PHONY: up down logs test lint fmt migrate revision demo psql

up:  ## sobe a stack de desenvolvimento (com reload)
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api

test:  ## precisa do postgres de pé (make up)
	uv run pytest --cov

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

fmt:
	uv run ruff check --fix .
	uv run ruff format .

migrate:
	docker compose run --rm migrate

revision:  ## make revision m="adiciona coluna x"
	DATABASE_URL=postgresql+psycopg://pelada:pelada@localhost:5433/pelada uv run alembic revision --autogenerate -m "$(m)"

demo:
	uv run python scripts/demo.py

psql:
	docker compose exec db psql -U pelada -d pelada
