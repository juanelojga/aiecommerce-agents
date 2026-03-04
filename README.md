# aiecommerce-agents

AI-powered e-commerce agent orchestration platform built with FastAPI, LangGraph, and async Python.

> [!NOTE]
> This repository is in early implementation stage. The PRD scope is larger than what is currently available in code.

## Overview

`aiecommerce-agents` is the orchestration layer for automating e-commerce listing workflows.
It is designed to consume an external catalog/API (`aiecommerce`) and coordinate agent-driven tasks such as assembly, publishing, and monitoring.

The full product vision and requirements are documented in [prd.md](prd.md).

## Current implementation status

Implemented now:

- FastAPI application bootstrap with CORS middleware
- Environment-driven settings via `pydantic-settings`
- Structured logging setup
- `GET /health` endpoint
- Async `AIEcommerceClient` service for authenticated outbound API calls
- Docker Compose development stack (`api`, `db`, `sentinel`)
- Basic async integration tests

Planned (from PRD, not fully implemented yet):

- Multi-agent LangGraph workflows for tower + bundle generation
- MercadoLibre publishing flows
- Sentinel stock/price automation lifecycle
- Local registry domain model and business workflows

## Tech stack

- Python 3.13+
- FastAPI + Uvicorn (ASGI)
- Pydantic v2 + `pydantic-settings`
- LangGraph / LangChain
- SQLAlchemy async
- PostgreSQL (Docker) / SQLite option for local
- Ruff + Mypy + Pytest
- Dependency/runtime manager: `uv`

## Project structure

```text
src/orchestrator/
	main.py                 # FastAPI app entrypoint
	api/routes/             # API routes (health currently)
	core/                   # Config, logging, security
	services/               # External service clients
	graph/                  # LangGraph state/nodes (scaffold)
	models/                 # Data model scaffold
	schemas/                # Pydantic schema scaffold

scripts/
	sentinel.py             # Background sentinel process

tests/
	test_main.py            # Health/CORS integration tests
```

## Quick start (local)

### 1) Prerequisites

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/)

### 2) Install dependencies

```bash
uv sync
```

### 3) Configure environment

```bash
cp .env.example .env
```

Fill in required keys in `.env` as needed (especially API/LLM credentials).

### 4) Run the API

```bash
uv run uvicorn orchestrator.main:app --reload
```

Health check:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{ "status": "ok" }
```

## Docker development

For full containerized workflow (`api` + `db` + `sentinel`):

```bash
cp .env.example .env
docker compose up --build
```

See [DOCKER.md](DOCKER.md) for complete Docker usage, troubleshooting, and port/database details.

## API endpoints (current)

- `GET /health` → returns service status

## Configuration

Main settings are loaded from environment variables in `src/orchestrator/core/config.py`:

- `APP_NAME`, `DEBUG`, `API_PORT`
- `DATABASE_URL`, `POSTGRES_*`
- `AIECOMMERCE_API_URL`, `AIECOMMERCE_API_KEY`
- `MERCADOLIBRE_*`
- `OPENAI_API_KEY`

Start from `.env.example` for defaults and placeholders.

## Quality gates

Before finishing any change, run all required checks:

```bash
uv run ruff check . --fix
uv run ruff format .
uv run mypy .
uv run pytest --cov=src/orchestrator --cov-report=term-missing
```

## Testing

### Local (without Docker)

1. Install dependencies:

```bash
uv sync
```

2. Run all tests:

```bash
uv run pytest
```

3. Run a single test file:

```bash
uv run pytest tests/test_main.py
```

4. Run tests with coverage:

```bash
uv run pytest --cov=src/orchestrator --cov-report=term-missing
```

### Docker (inside `api` container)

1. Start the Docker stack:

```bash
cp .env.example .env
docker compose up --build -d
```

2. Run all tests in the container:

```bash
docker compose exec api uv run pytest
```

3. Run a single test file in the container:

```bash
docker compose exec api uv run pytest tests/test_main.py
```

4. Run tests with coverage in the container:

```bash
docker compose exec api uv run pytest --cov=src/orchestrator --cov-report=term-missing
```

## Product requirements

Detailed functional and non-functional requirements, architecture goals, and roadmap are in [prd.md](prd.md).
