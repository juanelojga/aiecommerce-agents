# Docker Development Environment

This document covers how to run the **aiecommerce-agents** project using Docker
Compose for local development. The setup includes three services: the FastAPI
application server, a background sentinel process, and a PostgreSQL database.

---

## Prerequisites

| Requirement       | Minimum version |
| ----------------- | --------------- |
| Docker Engine     | 24.0+           |
| Docker Compose V2 | 2.20+           |

Verify with:

```bash
docker --version
docker compose version
```

---

## Quick start

```bash
# 1. Copy the example environment file
cp .env.example .env

# 2. (Optional) Edit .env to change ports or credentials — see "Port
#    configuration" below if you have conflicts with other local projects.

# 3. Build and start all services
docker compose up --build

# 4. Verify the API is running
curl http://localhost:8000/health
# → {"status":"ok"}
```

To run in the background:

```bash
docker compose up --build -d
```

To stop all services:

```bash
docker compose down
```

---

## Services overview

| Service      | Description                              | Default host port | Internal port | Image / Build        |
| ------------ | ---------------------------------------- | ----------------- | ------------- | -------------------- |
| **api**      | FastAPI server with uvicorn (hot-reload) | `8000`            | `8000`        | `./Dockerfile` (dev) |
| **sentinel** | Background stock & price monitoring loop | — (no port)       | —             | `./Dockerfile` (dev) |
| **db**       | PostgreSQL 16 database (Local Registry)  | `5432`            | `5432`        | `postgres:16-alpine` |

---

## Port configuration

If you already have another project using port `8000` or `5432`, change the
**host** ports in your `.env` file:

```dotenv
# Map the FastAPI server to host port 9000 instead of 8000
API_PORT=9000

# Map PostgreSQL to host port 5433 instead of 5432
POSTGRES_PORT=5433
```

Then restart:

```bash
docker compose down && docker compose up --build
```

The API will now be available at `http://localhost:9000` and PostgreSQL at
`localhost:5433`.

> **Note:** Only the host-side port changes. Containers always communicate
> internally on their default ports (`8000` and `5432`).

---

## Database

### Default credentials

These credentials are created automatically on the first start and are intended
for **local development only**. Never use them in production.

| User            | Password            | Access level                      | Purpose                       |
| --------------- | ------------------- | --------------------------------- | ----------------------------- |
| `orchestrator`  | `orchestrator`      | Superuser (owns the database)     | Migrations, schema management |
| `app_user`      | `app_password`      | Full read-write on `orchestrator` | Application runtime           |
| `readonly_user` | `readonly_password` | Read-only on `orchestrator`       | Debugging, inspection         |

The superuser credentials are configurable via `.env`:

```dotenv
POSTGRES_USER=orchestrator
POSTGRES_PASSWORD=orchestrator
POSTGRES_DB=orchestrator
```

### Connecting from your host machine

```bash
# Using the superuser
psql -h localhost -p ${POSTGRES_PORT:-5432} -U orchestrator -d orchestrator

# Using the read-only user
psql -h localhost -p ${POSTGRES_PORT:-5432} -U readonly_user -d orchestrator
```

### Connecting from inside a container

```bash
# Interactive shell on the db container
docker compose exec db psql -U orchestrator -d orchestrator

# Or from the api container (using the service hostname "db")
docker compose exec api python -c "
import asyncio, sqlalchemy
async def check():
    engine = sqlalchemy.ext.asyncio.create_async_engine(
        'postgresql+asyncpg://orchestrator:orchestrator@db:5432/orchestrator'
    )
    async with engine.connect() as conn:
        result = await conn.execute(sqlalchemy.text('SELECT 1'))
        print(result.scalar())
asyncio.run(check())
"
```

### Resetting the database

To destroy all data and start fresh:

```bash
docker compose down -v   # -v removes named volumes (pgdata)
docker compose up --build
```

The `init-db.sql` script will re-run and recreate the development users.

---

## Development workflow

### Hot-reload

The `api` service mounts `./src` into the container and runs uvicorn with
`--reload --reload-dir /app/src`. Any change you make to files under `src/` on
your host machine will trigger an automatic server restart inside the container.

### Running tests

```bash
docker compose exec api uv run pytest
```

With coverage:

```bash
docker compose exec api uv run pytest --cov=src/orchestrator --cov-report=term-missing
```

### Linting and formatting

```bash
docker compose exec api uv run ruff check . --fix
docker compose exec api uv run ruff format .
```

### Type checking

```bash
docker compose exec api uv run mypy .
```

### Running all quality gates

```bash
docker compose exec api sh -c "\
  uv run ruff check . --fix && \
  uv run ruff format . && \
  uv run mypy . && \
  uv run pytest --cov=src/orchestrator --cov-report=term-missing"
```

### Opening a shell inside the API container

```bash
docker compose exec api bash
```

---

## Sentinel service

The sentinel runs as a separate container using the same image as the API
server but with a different entrypoint (`scripts/sentinel.py`). It monitors
stock levels and pricing on a 2-hour cycle.

### Viewing sentinel logs

```bash
docker compose logs sentinel        # all logs
docker compose logs -f sentinel     # follow / stream
docker compose logs --tail=50 sentinel  # last 50 lines
```

### Restarting the sentinel independently

```bash
docker compose restart sentinel
```

---

## Volume management

| Volume      | Path inside container       | Purpose                       |
| ----------- | --------------------------- | ----------------------------- |
| `pgdata`    | `/var/lib/postgresql/data`  | PostgreSQL data persistence   |
| `./src`     | `/app/src` (bind mount)     | Source code — hot-reload      |
| `./tests`   | `/app/tests` (bind mount)   | Tests — run inside container  |
| `./scripts` | `/app/scripts` (bind mount) | Scripts — sentinel hot-reload |

To inspect Docker volumes:

```bash
docker volume ls | grep aiecommerce
```

---

## Rebuilding

After changing `pyproject.toml` (adding/removing dependencies):

```bash
docker compose up --build
```

If you only changed source code, no rebuild is needed — hot-reload handles it.

---

## Troubleshooting

### Port already in use

```
Error: Bind for 0.0.0.0:8000 failed: port is already allocated
```

Another process is using that port. Either stop it or change the port in `.env`:

```dotenv
API_PORT=9000
```

### Database connection refused

If the `api` or `sentinel` service fails with "connection refused to db:5432":

1. Check that the `db` service is healthy: `docker compose ps`
2. View db logs: `docker compose logs db`
3. If the volume is corrupted, reset: `docker compose down -v && docker compose up --build`

### Permission errors on bind mounts

On Linux, if you see permission errors, ensure your user owns the project files:

```bash
sudo chown -R $(id -u):$(id -g) .
```

### Stale containers or images

```bash
docker compose down --rmi local   # remove images built by compose
docker compose up --build         # rebuild from scratch
```

### Init script not running

The `docker/init-db.sql` script only runs when the `pgdata` volume is **empty**
(first-time container creation). If you need to re-run it:

```bash
docker compose down -v
docker compose up --build
```

---

## Environment variable reference

| Variable                     | Default                                | Used by        | Description                            |
| ---------------------------- | -------------------------------------- | -------------- | -------------------------------------- |
| `APP_NAME`                   | `aiecommerce-agents`                   | api, sentinel  | Application display name               |
| `DEBUG`                      | `false`                                | api, sentinel  | Enable debug mode / verbose logging    |
| `API_PORT`                   | `8000`                                 | docker-compose | Host port for the FastAPI server       |
| `POSTGRES_PORT`              | `5432`                                 | docker-compose | Host port for PostgreSQL               |
| `POSTGRES_USER`              | `orchestrator`                         | db             | PostgreSQL superuser name              |
| `POSTGRES_PASSWORD`          | `orchestrator`                         | db             | PostgreSQL superuser password          |
| `POSTGRES_DB`                | `orchestrator`                         | db             | PostgreSQL database name               |
| `DATABASE_URL`               | `postgresql+asyncpg://...@db:5432/...` | api, sentinel  | SQLAlchemy async connection string     |
| `AIECOMMERCE_API_URL`        | `https://api.aiecommerce.example.com`  | api, sentinel  | Base URL for the aiecommerce REST API  |
| `AIECOMMERCE_API_KEY`        | _(empty)_                              | api, sentinel  | Bearer token for aiecommerce API       |
| `MERCADOLIBRE_CLIENT_ID`     | _(empty)_                              | api            | MercadoLibre OAuth2 client ID          |
| `MERCADOLIBRE_CLIENT_SECRET` | _(empty)_                              | api            | MercadoLibre OAuth2 client secret      |
| `MERCADOLIBRE_REDIRECT_URI`  | `https://localhost:8000/auth/callback` | api            | MercadoLibre OAuth2 redirect URI       |
| `OPENAI_API_KEY`             | _(empty)_                              | api, sentinel  | OpenAI API key for LangChain/LangGraph |
