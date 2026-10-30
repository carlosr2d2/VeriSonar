.PHONY: env up down logs models test

env:
	@if not exist .env copy .env.example .env

up: env
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f backend celery-worker frontend

models:
	docker compose run --rm backend python scripts/download_models.py /data/models

test:
	docker compose run --rm backend pytest -q
