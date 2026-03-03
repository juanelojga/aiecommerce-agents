# Project Guidelines — aiecommerce-agents

## Code Style

- **Language:** Python 3.13+ with full type annotations on all function signatures and return types.
- **Formatter/Linter:** Use `ruff` for formatting and linting. Follow the config in `pyproject.toml`.
- **Imports:** Group as stdlib → third-party → local, one import per line. Use absolute imports.
- **Naming:** `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.
- **Docstrings:** Use Google-style docstrings on all public classes and functions.
- **Models:** Use Pydantic `BaseModel` for all data structures (request/response schemas, domain entities).

## Architecture

- **Framework:** FastAPI with uvicorn (ASGI).
- **Layout:** Flat module layout (no `src/` directory). Organize by domain:
  - `main.py` — FastAPI app entry point, router includes.
  - `routers/` — API route handlers grouped by domain.
  - `services/` — Business logic layer (one service per domain concern).
  - `models/` — Pydantic schemas (request, response, domain).
  - `agents/` — AI agent definitions and orchestration.
  - `tests/` — Mirrors the source tree (`tests/test_services/`, `tests/test_routers/`, etc.).
- **Dependency Injection:** Use FastAPI's `Depends()` for injecting services and configuration — never instantiate services directly inside route handlers.
- **SOLID Principles:**
  - **S** — Each module/class has a single responsibility. Routers handle HTTP concerns only; services own business logic; models define data shapes.
  - **O** — Extend behavior via new classes/functions rather than modifying existing ones. Use abstract base classes (`abc.ABC`) for contracts that may have multiple implementations.
  - **L** — Subtypes must be substitutable for their base types. Ensure derived classes honor parent interfaces.
  - **I** — Keep interfaces small and focused. Prefer multiple specific protocols (`typing.Protocol`) over one large interface.
  - **D** — Depend on abstractions. Services receive dependencies (DB clients, API clients) via constructor injection or FastAPI `Depends()`, not via global imports.
- **DRY:** Extract shared logic into utility functions or base classes. If a pattern appears more than twice, refactor it.

## Build and Test

```bash
# Install dependencies
uv sync

# Add a dependency
uv add <package>

# Run the application
uv run fastapi dev main.py

# Run tests (with coverage)
uv run pytest --cov=. --cov-report=term-missing

# Lint and format
uv run ruff check . --fix
uv run ruff format .
```

## Testing (TDD Workflow)

- **Test-Driven Development is mandatory.** Write a failing test before writing any production code.
- **Cycle:** Red → Green → Refactor. Commit at each green step.
- **Framework:** `pytest` with `pytest-asyncio` for async tests and `httpx` for FastAPI test client.
- **Structure:** Place tests under `tests/` mirroring the source layout. Name files `test_<module>.py`.
- **Fixtures:** Use `conftest.py` for shared fixtures (test client, mock services, DB sessions).
- **Coverage:** Maintain ≥ 80% line coverage. CI must fail below this threshold.
- **Mocking:** Use `unittest.mock.patch` or `pytest-mock` to isolate units. Mock external services at the boundary (API clients, DB calls), never mock internal logic.
- **Test categories:**
  - **Unit tests** — Test services and utilities in isolation.
  - **Integration tests** — Test routes via `TestClient` / `httpx.AsyncClient` with `app` from `main.py`.
  - Mark slow or external-dependent tests with `@pytest.mark.slow`.

## Project Conventions

- **Error handling:** Define custom exception classes in `exceptions.py`. Register FastAPI exception handlers in `main.py` to return consistent JSON error responses (`{"detail": "..."}` with appropriate HTTP status codes).
- **Configuration:** Use `pydantic-settings` for environment-based config. Load from `.env` files via `BaseSettings`. Never hard-code secrets or URLs.
- **Async-first:** Prefer `async def` route handlers and service methods. Use `httpx.AsyncClient` for outbound HTTP calls.
- **Logging:** Use Python's `logging` module (never `print()`). Configure structured JSON logging for production.
- **Commit messages:** Use Conventional Commits (`feat:`, `fix:`, `test:`, `refactor:`, `docs:`).

## Integration Points

- **AI/LLM services:** Wrap all LLM calls behind an abstract interface (`Protocol` or `ABC`) so the provider can be swapped without changing business logic.
- **E-commerce APIs:** Isolate third-party API clients in dedicated modules under `clients/`. Each client should have its own Pydantic models for request/response mapping.
- **Database (future):** Use an async ORM or driver. Keep repository pattern — data access behind an abstract interface.

## Security

- **Secrets:** Never commit `.env` files or API keys. Use `.env.example` with placeholder values.
- **CORS:** Configure explicitly in `main.py` — restrict `allow_origins` to known domains.
- **Input validation:** Rely on Pydantic models for all request validation. Never trust raw input.
- **Auth:** When implemented, use FastAPI's security utilities (`OAuth2PasswordBearer`, `HTTPBearer`). Protect routes via dependency injection.
