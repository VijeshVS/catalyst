.PHONY: help up down dev-api dev-web dev-video dev test test-sdk build-sdk

help:
	@echo "Catalyst — Feature Flag & Rollout Platform"
	@echo ""
	@echo "Commands:"
	@echo "  make up        - Start local PostgreSQL 16 and Redis 7 (Docker Compose)"
	@echo "  make down      - Stop local PostgreSQL and Redis"
	@echo "  make dev-api   - Run FastAPI backend with uv (port 8000)"
	@echo "  make dev-web   - Run React dashboard with Vite (port 5173)"
	@echo "  make dev-video - Run the Reelwise video recommendation example (port 8002)"
	@echo "  make test      - Run backend unit and integration tests (pytest)"
	@echo "  make test-sdk  - Run the Python SDK test suite"
	@echo "  make build-sdk - Build the catalyst-sdk wheel"

up:
	docker compose up -d

down:
	docker compose down

dev-api:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

dev-web:
	cd frontend && npm run dev

dev-video:
	cd app-examples/video-recommendations && uv run --with fastapi --with 'uvicorn[standard]' --with python-dotenv --with httpx uvicorn app:app --reload --port 8002

test:
	cd backend && uv run pytest

test-sdk:
	cd packages/catalyst-python-sdk && uv run --with pytest --with mmh3 pytest

build-sdk:
	cd packages/catalyst-python-sdk && uv build
