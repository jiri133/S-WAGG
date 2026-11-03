.PHONY: setup dev backend frontend test lint fmt up down

setup:            ## Install all dependencies + create .env files
	cd backend && uv sync && cp -n .env.example .env || true
	cd frontend && npm install && cp -n .env.example .env || true

backend:          ## Run FastAPI with reload on :8000
	cd backend && uv run fastapi dev app/main.py

frontend:         ## Run Vite on :5173
	cd frontend && npm run dev

dev:              ## Run both (Ctrl+C stops both)
	$(MAKE) -j2 backend frontend

test:
	cd backend && uv run pytest -q
	cd frontend && npm run build

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint

fmt:
	cd backend && uv run ruff check --fix . && uv run ruff format .

up:               ## Everything via Docker
	docker compose up --build

down:
	docker compose down
