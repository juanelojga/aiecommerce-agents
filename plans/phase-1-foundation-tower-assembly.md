# Phase 1: Foundation & Tower Assembly (MVP)

## 1. Feature Goal and Success Criteria

### Goal

Establish the foundational data layer (Local Registry), extend the aiecommerce API client with inventory and specs fetching, implement the Inventory Architect agent (Agent 1) with full component compatibility validation and uniqueness engine, wire it into a LangGraph workflow, and expose tower management via admin API endpoints.

### Success Criteria

- The system can fetch filtered component inventory from the aiecommerce API.
- The system can fetch deep technical specs for individual components.
- SQLAlchemy models for `published_towers`, `published_bundles`, and `component_audit` are created with async session management.
- The Inventory Architect agent can select components for Home, Business, and Gaming tiers.
- Every generated build passes technical compatibility validation (socket, DDR, PSU wattage, form factor).
- The SHA-256 uniqueness engine prevents duplicate builds.
- PSU and cooling fans are auto-added when required.
- Components with the oldest `last_bundled_date` are prioritized.
- Towers are stored in the Local Registry and exposed via REST API.
- Manual assembly runs can be triggered via API.
- All quality gates pass (ruff, mypy, pytest ≥ 80% coverage).

### Definition of Done

The system can fetch inventory, assemble valid unique towers for all 3 tiers, store them in the Local Registry, and expose them via API — with zero manual intervention after triggering a run.

---

## 2. Context and References

### PRD Sections

- `prd.md` — FR-1.1 through FR-1.7: Tower Assembly (Inventory Architect)
- `prd.md` — FR-6.1 through FR-6.2: Local Registry
- `prd.md` — FR-7.1, FR-7.2, FR-7.4, FR-7.6: API Endpoints (towers + trigger)
- `prd.md` — Phase 1 deliverables (lines 344–362)
- `prd.md` — Section 9: Integration Points (aiecommerce API endpoints consumed)
- `prd.md` — Section 12: Testing and Validation Strategy

### Architecture Rules

- `.github/copilot-instructions.md` — Source layout, SOLID, DRY, TDD, quality gates

### aiecommerce API Endpoints Consumed (Phase 1)

- `GET /api/v1/agent/inventory/` — Filtered active inventory with stock > 0
- `GET /api/v1/agent/product/{id}/specs/` — Deep technical specs for compatibility checking

---

## 3. Codebase Analysis

### What Already Exists

| File                                       | Status   | Notes                                              |
| ------------------------------------------ | -------- | -------------------------------------------------- |
| `src/orchestrator/main.py`                 | Existing | FastAPI app with CORS, health route included       |
| `src/orchestrator/core/config.py`          | Existing | `Settings` with DB, aiecommerce, ML, OpenAI config |
| `src/orchestrator/core/logging.py`         | Existing | Structured logging setup                           |
| `src/orchestrator/api/routes/health.py`    | Existing | `GET /health` endpoint                             |
| `src/orchestrator/services/aiecommerce.py` | Existing | `AIEcommerceClient` with generic `get()` method    |
| `src/orchestrator/models/base.py`          | Existing | `Base(DeclarativeBase)` — empty declarative base   |
| `src/orchestrator/schemas/common.py`       | Existing | `HealthResponse`, `ErrorResponse`                  |
| `src/orchestrator/graph/state.py`          | Existing | `GraphState` with `messages` + `context`           |
| `scripts/sentinel.py`                      | Existing | Skeleton sentinel loop                             |
| `tests/conftest.py`                        | Existing | Shared test fixtures                               |
| `tests/test_main.py`                       | Existing | Health/CORS integration tests                      |

### What Needs to Be Created

| File                                                      | Purpose                                         |
| --------------------------------------------------------- | ----------------------------------------------- |
| `src/orchestrator/core/database.py`                       | Async SQLAlchemy engine + session factory       |
| `src/orchestrator/core/exceptions.py`                     | Custom exception classes                        |
| `src/orchestrator/core/security.py`                       | API key auth dependency                         |
| `src/orchestrator/models/tower.py`                        | `PublishedTower` SQLAlchemy model               |
| `src/orchestrator/models/bundle.py`                       | `PublishedBundle` SQLAlchemy model              |
| `src/orchestrator/models/component_audit.py`              | `ComponentAudit` SQLAlchemy model               |
| `src/orchestrator/schemas/inventory.py`                   | Pydantic schemas for aiecommerce inventory data |
| `src/orchestrator/schemas/tower.py`                       | Tower request/response Pydantic schemas         |
| `src/orchestrator/services/tower_repository.py`           | Repository for tower CRUD (async, SQLAlchemy)   |
| `src/orchestrator/services/component_audit_repository.py` | Repository for component audit CRUD             |
| `src/orchestrator/services/compatibility.py`              | Compatibility validation engine                 |
| `src/orchestrator/services/uniqueness.py`                 | SHA-256 hash uniqueness engine                  |
| `src/orchestrator/graph/nodes/__init__.py`                | Package init                                    |
| `src/orchestrator/graph/nodes/inventory_architect.py`     | Agent 1 LangGraph node                          |
| `src/orchestrator/graph/workflow.py`                      | LangGraph workflow definition                   |
| `src/orchestrator/api/routes/towers.py`                   | Tower listing API routes                        |
| `src/orchestrator/api/routes/triggers.py`                 | Manual run trigger API route                    |
| `tests/test_models/test_tower.py`                         | Tower model tests                               |
| `tests/test_models/test_bundle.py`                        | Bundle model tests                              |
| `tests/test_models/test_component_audit.py`               | Component audit model tests                     |
| `tests/test_services/test_aiecommerce.py`                 | Extended aiecommerce client tests               |
| `tests/test_services/test_tower_repository.py`            | Tower repository tests                          |
| `tests/test_services/test_compatibility.py`               | Compatibility engine tests                      |
| `tests/test_services/test_uniqueness.py`                  | Uniqueness engine tests                         |
| `tests/test_graph/test_inventory_architect.py`            | Inventory Architect node tests                  |
| `tests/test_graph/test_workflow.py`                       | Workflow integration tests                      |
| `tests/test_api/test_towers.py`                           | Tower API route tests                           |
| `tests/test_api/test_triggers.py`                         | Trigger API route tests                         |

### What Needs to Be Modified

| File                                       | Changes                                                   |
| ------------------------------------------ | --------------------------------------------------------- |
| `src/orchestrator/main.py`                 | Add lifespan for DB init, include tower + trigger routers |
| `src/orchestrator/core/config.py`          | Add `ASSEMBLY_MARGIN_PCT`, `API_KEY` settings             |
| `src/orchestrator/services/aiecommerce.py` | Add `get_inventory()`, `get_product_specs()` methods      |
| `src/orchestrator/graph/state.py`          | Extend `GraphState` with tower assembly fields            |
| `src/orchestrator/models/__init__.py`      | Re-export all models                                      |
| `tests/conftest.py`                        | Add DB session fixtures, mock service fixtures            |

### Existing Patterns to Follow

- **Service pattern:** `AIEcommerceClient` in `src/orchestrator/services/aiecommerce.py` — constructor takes `Settings`, uses `httpx.AsyncClient` internally.
- **Schema pattern:** `HealthResponse` / `ErrorResponse` in `src/orchestrator/schemas/common.py` — simple Pydantic `BaseModel` subclasses with docstrings.
- **Route pattern:** `src/orchestrator/api/routes/health.py` — `APIRouter` with route functions, included in `main.py`.
- **Config pattern:** `Settings(BaseSettings)` in `src/orchestrator/core/config.py` — env-based settings with `SettingsConfigDict`.
- **Test pattern:** `tests/test_main.py` — uses `httpx.AsyncClient` with `ASGITransport` wrapping the FastAPI `app`.

### Dependencies

All required packages are already in `pyproject.toml`:

- `sqlalchemy[asyncio]`, `aiosqlite`, `asyncpg` — database
- `langgraph`, `langchain`, `langchain-openai` — agent orchestration
- `httpx` — HTTP client
- `pydantic-settings` — configuration
- `fastapi[standard]` — web framework

No new dependencies needed for Phase 1.

---

## 4. Architecture Decision

### Chosen Approach

**Repository Pattern with Service Layer + LangGraph Node**

- **Data layer:** SQLAlchemy models with an async session factory injected via FastAPI `Depends()`. Repository classes encapsulate all database queries.
- **Service layer:** The compatibility engine and uniqueness engine are pure service classes — no DB dependency, easily testable. The aiecommerce client is extended with typed methods.
- **Agent layer:** The Inventory Architect is a LangGraph node function that receives `GraphState`, calls services, and returns state updates. It uses LLM tool-calling for component reasoning but validates all outputs with hard-coded compatibility rules.
- **API layer:** FastAPI routes use `Depends()` to inject repositories and services. Routes handle HTTP concerns only; business logic lives in services/graph nodes.

### Alternatives Considered

1. **Direct SQL queries (no ORM):** Rejected — violates project convention of SQLAlchemy + repository pattern; loses type safety.
2. **Synchronous database access:** Rejected — project mandates async-first (`asyncio_mode = "auto"` in pytest config).
3. **LLM-only component selection (no hard rules):** Rejected — FR-1.3 requires deterministic compatibility validation. LLM hallucination risk is too high (see PRD Risk section).
4. **Monolithic service class:** Rejected — violates SRP. Separation into compatibility, uniqueness, and repository services follows SOLID.

### Key Tradeoffs

- **Strict validation over flexibility:** All component compatibility is enforced via deterministic rules, not LLM judgment. This ensures zero invalid builds but may miss creative combinations.
- **PostgreSQL in Docker, SQLite for tests:** Production uses PostgreSQL (already configured in `docker-compose.yml`), tests use in-memory SQLite for speed. This matches the existing setup.

---

## 5. Task Breakdown

### Task 1: Configure async database session management

**Description:** Create the async SQLAlchemy engine, session factory, and a FastAPI dependency for injecting `AsyncSession` into route handlers and services. Add a lifespan handler to `main.py` that creates all tables on startup.

**Files to create:**

- `src/orchestrator/core/database.py` — async engine, `async_session_factory`, `get_db_session` dependency

**Files to modify:**

- `src/orchestrator/main.py` — add lifespan context manager for DB table creation

**Signatures:**

```python
# src/orchestrator/core/database.py
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    ...

async def create_tables() -> None:
    """Create all tables defined by the ORM models."""
    ...
```

**Dependencies:** None (first task)

**Test file:** `tests/test_core/test_database.py`

**Test cases:**
| Test Function | Verifies |
|--------------|----------|
| `test_get_db_session_yields_session` | Session dependency yields a valid `AsyncSession` |
| `test_create_tables_creates_schema` | Tables are created in an in-memory DB |

**Acceptance criteria:**

- [ ] `get_db_session` yields a valid `AsyncSession` and closes it after use
- [ ] `create_tables` creates all ORM-defined tables
- [ ] Lifespan in `main.py` calls `create_tables` on startup
- [ ] All quality gates pass

**Complexity:** S

---

### Task 2: Define Local Registry SQLAlchemy models

**Description:** Create SQLAlchemy ORM models for `published_towers`, `published_bundles`, and `component_audit` tables as specified in FR-6.1. These models inherit from the existing `Base` in `models/base.py`.

**Files to create:**

- `src/orchestrator/models/tower.py` — `PublishedTower` model
- `src/orchestrator/models/bundle.py` — `PublishedBundle` model
- `src/orchestrator/models/component_audit.py` — `ComponentAudit` model

**Files to modify:**

- `src/orchestrator/models/__init__.py` — re-export all models so `Base.metadata` discovers them

**Signatures:**

```python
# src/orchestrator/models/tower.py
import enum
from datetime import datetime
from sqlalchemy import DateTime, Enum, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column
from orchestrator.models.base import Base

class TowerCategory(str, enum.Enum):
    HOME = "Home"
    BUSINESS = "Business"
    GAMING = "Gaming"

class TowerStatus(str, enum.Enum):
    ACTIVE = "Active"
    PAUSED = "Paused"

class PublishedTower(Base):
    """A published PC tower build stored in the Local Registry."""
    __tablename__ = "published_towers"

    bundle_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    ml_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category: Mapped[TowerCategory] = mapped_column(Enum(TowerCategory))
    status: Mapped[TowerStatus] = mapped_column(Enum(TowerStatus), default=TowerStatus.ACTIVE)
    component_skus: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

# src/orchestrator/models/bundle.py
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column
from orchestrator.models.base import Base

class PublishedBundle(Base):
    """A published PC bundle (tower + peripherals) in the Local Registry."""
    __tablename__ = "published_bundles"

    bundle_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tower_hash: Mapped[str] = mapped_column(String(64), ForeignKey("published_towers.bundle_hash"))
    peripheral_skus: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    ml_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

# src/orchestrator/models/component_audit.py
from datetime import datetime
from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from orchestrator.models.base import Base

class ComponentAudit(Base):
    """Tracks component usage across builds for catalog rotation."""
    __tablename__ = "component_audit"

    sku: Mapped[str] = mapped_column(String(100), primary_key=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    last_bundled_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bundle_count: Mapped[int] = mapped_column(Integer, default=0)
    stock_level: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

**Dependencies:** Task 1

**Test file:** `tests/test_models/test_tower.py`, `tests/test_models/test_bundle.py`, `tests/test_models/test_component_audit.py`

**Test cases:**
| Test Function | Verifies |
|--------------|----------|
| `test_published_tower_create` | Tower can be persisted and read back |
| `test_published_tower_category_enum` | Category field accepts only valid enum values |
| `test_published_tower_status_default` | Default status is `ACTIVE` |
| `test_published_bundle_create` | Bundle can be persisted with FK to tower |
| `test_published_bundle_peripheral_skus_json` | JSON peripheral_skus stores and retrieves correctly |
| `test_component_audit_create` | ComponentAudit can be persisted with default values |
| `test_component_audit_bundle_count_default` | Default bundle_count is 0 |

**Acceptance criteria:**

- [ ] All three models are defined with columns matching FR-6.1
- [ ] `PublishedTower` uses `bundle_hash` (SHA-256, 64 chars) as PK
- [ ] `PublishedBundle` has FK to `published_towers.bundle_hash`
- [ ] `ComponentAudit` tracks `last_bundled_date` and `bundle_count`
- [ ] Models are importable from `orchestrator.models`
- [ ] All quality gates pass

**Complexity:** S

---

### Task 3: Create custom exception classes

**Description:** Define project-wide custom exceptions for use across services, graph nodes, and API routes. Register FastAPI exception handlers in `main.py` to return consistent JSON error responses.

**Files to create:**

- `src/orchestrator/core/exceptions.py` — custom exception hierarchy

**Files to modify:**

- `src/orchestrator/main.py` — register exception handlers

**Signatures:**

```python
# src/orchestrator/core/exceptions.py
class OrchestratorError(Exception):
    """Base exception for all orchestrator errors."""
    ...

class APIClientError(OrchestratorError):
    """Error communicating with an external API."""
    ...

class InventoryError(OrchestratorError):
    """Error fetching or processing inventory data."""
    ...

class CompatibilityError(OrchestratorError):
    """Components failed compatibility validation."""
    ...

class UniquenessError(OrchestratorError):
    """Could not generate a unique build combination."""
    ...

class TowerNotFoundError(OrchestratorError):
    """Requested tower does not exist in the registry."""
    ...
```

**Dependencies:** None

**Test file:** `tests/test_core/test_exceptions.py`

**Test cases:**
| Test Function | Verifies |
|--------------|----------|
| `test_orchestrator_error_is_base` | All custom exceptions inherit from `OrchestratorError` |
| `test_exception_handler_returns_json` | FastAPI exception handler returns `{"detail": "..."}` with correct status |

**Acceptance criteria:**

- [ ] Exception hierarchy defined with meaningful subclasses
- [ ] FastAPI exception handlers registered for custom exceptions
- [ ] Error responses follow `{"detail": "..."}` format
- [ ] All quality gates pass

**Complexity:** S

---

### Task 4: Implement API key authentication dependency

**Description:** Create a FastAPI security dependency that validates API key from request headers for protected endpoints (run triggers). This satisfies the security requirement for trigger endpoints.

**Files to create:**

- `src/orchestrator/core/security.py` — `verify_api_key` dependency

**Files to modify:**

- `src/orchestrator/core/config.py` — add `API_KEY` setting

**Signatures:**

```python
# src/orchestrator/core/security.py
from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Depends(api_key_header)) -> str:
    """Validate the API key from the request header.

    Raises:
        HTTPException: 401 if the key is missing or invalid.
    """
    ...
```

**Dependencies:** None

**Test file:** `tests/test_core/test_security.py`

**Test cases:**
| Test Function | Verifies |
|--------------|----------|
| `test_verify_api_key_valid` | Valid key passes through |
| `test_verify_api_key_invalid` | Invalid key raises 401 |
| `test_verify_api_key_missing` | Missing header raises 401/403 |

**Acceptance criteria:**

- [ ] `verify_api_key` validates against `settings.API_KEY`
- [ ] Invalid or missing keys return HTTP 401
- [ ] `API_KEY` is configurable via environment variable
- [ ] All quality gates pass

**Complexity:** S

---

### Task 5: Define inventory Pydantic schemas

**Description:** Create Pydantic schemas representing the data structures returned by the aiecommerce API (inventory items, product specs) and internal component representations used by the Inventory Architect.

**Files to create:**

- `src/orchestrator/schemas/inventory.py` — inventory and component schemas

**Signatures:**

```python
# src/orchestrator/schemas/inventory.py
import enum
from pydantic import BaseModel, Field

class ComponentCategory(str, enum.Enum):
    CPU = "cpu"
    MOTHERBOARD = "motherboard"
    RAM = "ram"
    GPU = "gpu"
    SSD = "ssd"
    PSU = "psu"
    CASE = "case"
    FAN = "fan"

class InventoryItem(BaseModel):
    """A single component from the aiecommerce inventory."""
    id: int
    sku: str
    name: str
    category: ComponentCategory
    price: float
    available_quantity: int
    is_active: bool
    last_bundled_date: str | None = None

class ProductSpecs(BaseModel):
    """Deep technical specifications for a component."""
    id: int
    sku: str
    socket: str | None = None
    ddr_generation: str | None = None
    form_factor: str | None = None
    wattage: int | None = None
    tdp: int | None = None
    ssd_interface: str | None = None
    has_integrated_psu: bool = False
    included_fans: int = 0
    ram_speed: int | None = None
    extra_specs: dict[str, object] = Field(default_factory=dict)

class InventoryResponse(BaseModel):
    """Response from the aiecommerce inventory endpoint."""
    count: int
    results: list[InventoryItem]

class ComponentSelection(BaseModel):
    """A selected component for a tower build."""
    sku: str
    name: str
    category: ComponentCategory
    price: float
    specs: ProductSpecs

class TowerBuild(BaseModel):
    """A complete tower build with all components."""
    tier: str  # Home, Business, Gaming
    cpu: ComponentSelection
    motherboard: ComponentSelection
    ram: ComponentSelection
    gpu: ComponentSelection | None = None
    ssd: ComponentSelection
    psu: ComponentSelection
    case: ComponentSelection
    fans: list[ComponentSelection] = Field(default_factory=list)
    bundle_hash: str = ""
    total_price: float = 0.0
```

**Dependencies:** None

**Test file:** `tests/test_schemas/test_inventory.py`

**Test cases:**
| Test Function | Verifies |
|--------------|----------|
| `test_inventory_item_valid` | Valid data creates InventoryItem |
| `test_inventory_item_missing_required` | Missing fields raise ValidationError |
| `test_product_specs_optional_fields` | Optional specs default correctly |
| `test_component_selection_round_trip` | Serialization/deserialization works |
| `test_tower_build_hash_default` | Default bundle_hash is empty string |
| `test_component_category_enum_values` | All expected categories exist |

**Acceptance criteria:**

- [ ] `InventoryItem` maps to aiecommerce API `GET /api/v1/agent/inventory/` response items
- [ ] `ProductSpecs` maps to aiecommerce API `GET /api/v1/agent/product/{id}/specs/` response
- [ ] `TowerBuild` represents a complete, validated build
- [ ] All schemas have Google-style docstrings
- [ ] All quality gates pass

**Complexity:** S

---

### Task 6: Define tower API Pydantic schemas

**Description:** Create Pydantic schemas for the tower REST API request/response payloads, including list responses, detail responses, and run trigger responses.

**Files to create:**

- `src/orchestrator/schemas/tower.py` — tower API schemas

**Signatures:**

```python
# src/orchestrator/schemas/tower.py
from datetime import datetime
from pydantic import BaseModel, Field

class TowerSummary(BaseModel):
    """Summary of a published tower for list endpoints."""
    bundle_hash: str
    category: str
    status: str
    ml_id: str | None
    total_price: float
    created_at: datetime

class TowerDetail(BaseModel):
    """Detailed tower info including all component SKUs."""
    bundle_hash: str
    category: str
    status: str
    ml_id: str | None
    component_skus: dict[str, object]
    total_price: float
    created_at: datetime
    updated_at: datetime

class TowerListResponse(BaseModel):
    """Paginated list of published towers."""
    count: int
    towers: list[TowerSummary]

class RunTriggerRequest(BaseModel):
    """Request body for manually triggering an assembly run."""
    tiers: list[str] = Field(default_factory=lambda: ["Home", "Business", "Gaming"])

class RunTriggerResponse(BaseModel):
    """Response from a manual assembly run trigger."""
    status: str
    towers_created: int
    tower_hashes: list[str]
    errors: list[str] = Field(default_factory=list)
```

**Dependencies:** None

**Test file:** `tests/test_schemas/test_tower_schema.py`

**Test cases:**
| Test Function | Verifies |
|--------------|----------|
| `test_tower_summary_valid` | Valid data creates TowerSummary |
| `test_tower_detail_valid` | Valid data creates TowerDetail |
| `test_run_trigger_request_defaults` | Default tiers include all three |
| `test_run_trigger_response_valid` | Valid response schema serialization |

**Acceptance criteria:**

- [ ] `TowerSummary` provides concise listing info for `GET /api/v1/towers/`
- [ ] `TowerDetail` provides full info for `GET /api/v1/towers/{bundle_hash}/`
- [ ] `RunTriggerResponse` reports results of triggered runs
- [ ] All quality gates pass

**Complexity:** S

---

### Task 7: Extend aiecommerce API client with inventory methods

**Description:** Add typed methods to `AIEcommerceClient` for fetching inventory (filtered by category, active, in-stock) and product specs. Implement retry logic with exponential backoff as required by the NFRs.

**Files to modify:**

- `src/orchestrator/services/aiecommerce.py` — add `get_inventory()`, `get_product_specs()`, retry logic

**Signatures:**

```python
# Extensions to AIEcommerceClient

async def get_inventory(
    self,
    category: str | None = None,
    active_only: bool = True,
    in_stock_only: bool = True,
) -> InventoryResponse:
    """Fetch filtered inventory from the aiecommerce API.

    Args:
        category: Filter by component category (cpu, motherboard, etc.).
        active_only: Only return active items.
        in_stock_only: Only return items with available_quantity > 0.

    Returns:
        Parsed inventory response with typed items.

    Raises:
        APIClientError: If the API call fails after retries.
    """
    ...

async def get_product_specs(self, product_id: int) -> ProductSpecs:
    """Fetch deep technical specifications for a product.

    Args:
        product_id: The product ID in the aiecommerce system.

    Returns:
        Parsed product specifications.

    Raises:
        APIClientError: If the API call fails after retries.
    """
    ...
```

**Dependencies:** Task 3 (exceptions), Task 5 (schemas)

**Test file:** `tests/test_services/test_aiecommerce.py`

**Test cases:**
| Test Function | Verifies |
|--------------|----------|
| `test_get_inventory_success` | Returns typed `InventoryResponse` |
| `test_get_inventory_with_category_filter` | Passes category query param |
| `test_get_inventory_api_error_raises` | API errors wrapped in `APIClientError` |
| `test_get_inventory_retry_on_failure` | Retries with backoff on transient errors |
| `test_get_product_specs_success` | Returns typed `ProductSpecs` |
| `test_get_product_specs_not_found` | 404 raises `APIClientError` |

**Acceptance criteria:**

- [ ] `get_inventory()` returns `InventoryResponse` with typed `InventoryItem` list
- [ ] Category, active, and stock filters are passed as query parameters
- [ ] `get_product_specs()` returns `ProductSpecs` for a given product ID
- [ ] Retry logic: max 3 retries, exponential backoff with base delay 5 seconds
- [ ] Errors are wrapped in `APIClientError`
- [ ] All quality gates pass

**Complexity:** M

---

### Task 8: Tower repository (database CRUD)

**Description:** Create a repository class for `PublishedTower` CRUD operations using async SQLAlchemy sessions. Follows the repository pattern for data access abstraction.

**Files to create:**

- `src/orchestrator/services/tower_repository.py` — `TowerRepository` class

**Signatures:**

```python
# src/orchestrator/services/tower_repository.py
from sqlalchemy.ext.asyncio import AsyncSession
from orchestrator.models.tower import PublishedTower, TowerCategory, TowerStatus

class TowerRepository:
    """Repository for PublishedTower CRUD operations."""

    def __init__(self, session: AsyncSession) -> None: ...

    async def get_by_hash(self, bundle_hash: str) -> PublishedTower | None:
        """Retrieve a tower by its bundle hash."""
        ...

    async def list_all(
        self,
        category: TowerCategory | None = None,
        status: TowerStatus | None = None,
    ) -> list[PublishedTower]:
        """List towers with optional category/status filters."""
        ...

    async def create(self, tower: PublishedTower) -> PublishedTower:
        """Persist a new tower to the registry."""
        ...

    async def update_status(self, bundle_hash: str, status: TowerStatus) -> PublishedTower | None:
        """Update the status of a tower (e.g., Active → Paused)."""
        ...

    async def hash_exists(self, bundle_hash: str) -> bool:
        """Check if a bundle hash already exists in the registry."""
        ...
```

**Dependencies:** Task 1 (database), Task 2 (models)

**Test file:** `tests/test_services/test_tower_repository.py`

**Test cases:**
| Test Function | Verifies |
|--------------|----------|
| `test_create_tower` | Tower is persisted and retrievable |
| `test_get_by_hash_found` | Returns tower for existing hash |
| `test_get_by_hash_not_found` | Returns None for missing hash |
| `test_list_all_no_filter` | Returns all towers |
| `test_list_all_filter_category` | Filters by category correctly |
| `test_list_all_filter_status` | Filters by status correctly |
| `test_update_status` | Status is updated in DB |
| `test_hash_exists_true` | Returns True for existing hash |
| `test_hash_exists_false` | Returns False for missing hash |

**Acceptance criteria:**

- [ ] All CRUD operations work with async SQLAlchemy session
- [ ] `hash_exists()` enables uniqueness check without loading full model
- [ ] Filtering by category and status is supported
- [ ] Repository follows DI pattern (session injected via constructor)
- [ ] All quality gates pass

**Complexity:** M

---

### Task 9: Component audit repository

**Description:** Create a repository for `ComponentAudit` CRUD operations — tracking each component's `last_bundled_date` and `bundle_count` to support catalog rotation (FR-1.7) and uniqueness retry (FR-6.2).

**Files to create:**

- `src/orchestrator/services/component_audit_repository.py` — `ComponentAuditRepository` class

**Signatures:**

```python
# src/orchestrator/services/component_audit_repository.py
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from orchestrator.models.component_audit import ComponentAudit

class ComponentAuditRepository:
    """Repository for ComponentAudit CRUD operations."""

    def __init__(self, session: AsyncSession) -> None: ...

    async def get_by_sku(self, sku: str) -> ComponentAudit | None:
        """Retrieve audit record for a component SKU."""
        ...

    async def upsert(self, sku: str, category: str, stock_level: int) -> ComponentAudit:
        """Create or update a component audit entry."""
        ...

    async def record_bundle_usage(self, skus: list[str]) -> None:
        """Update last_bundled_date and increment bundle_count for each SKU."""
        ...

    async def get_least_recently_bundled(
        self, category: str, limit: int = 10,
    ) -> list[ComponentAudit]:
        """Get components ordered by oldest last_bundled_date for rotation."""
        ...
```

**Dependencies:** Task 1 (database), Task 2 (models)

**Test file:** `tests/test_services/test_component_audit_repository.py`

**Test cases:**
| Test Function | Verifies |
|--------------|----------|
| `test_upsert_creates_new` | Creates new audit record |
| `test_upsert_updates_existing` | Updates stock_level for existing SKU |
| `test_record_bundle_usage` | Increments bundle_count, sets last_bundled_date |
| `test_get_least_recently_bundled` | Returns components ordered by oldest date first |
| `test_get_least_recently_bundled_null_dates_first` | Components never bundled appear first |

**Acceptance criteria:**

- [ ] `record_bundle_usage()` atomically updates multiple SKUs
- [ ] `get_least_recently_bundled()` returns oldest-first ordering (null dates first)
- [ ] Upsert handles both create and update
- [ ] All quality gates pass

**Complexity:** M

---

### Task 10: Compatibility validation engine

**Description:** Implement deterministic compatibility validation rules for PC component builds. This is a pure service (no DB, no HTTP) that validates builds against hard-coded technical rules per FR-1.3.

**Files to create:**

- `src/orchestrator/services/compatibility.py` — `CompatibilityEngine` class

**Signatures:**

```python
# src/orchestrator/services/compatibility.py
from orchestrator.core.exceptions import CompatibilityError
from orchestrator.schemas.inventory import ComponentSelection, TowerBuild

class CompatibilityEngine:
    """Validates technical compatibility of PC component selections.

    Rules enforced (FR-1.3):
    - CPU socket matches motherboard socket
    - RAM DDR generation matches motherboard support
    - SSD form factor is supported by motherboard/case
    - PSU wattage covers estimated total TDP with headroom
    - Case form factor accommodates the motherboard
    """

    def validate_build(self, build: TowerBuild) -> list[str]:
        """Validate all compatibility rules for a build.

        Args:
            build: The tower build to validate.

        Returns:
            List of validation error messages (empty if valid).
        """
        ...

    def validate_socket(self, cpu: ComponentSelection, motherboard: ComponentSelection) -> str | None:
        """Check CPU socket ↔ motherboard socket compatibility."""
        ...

    def validate_ram(self, ram: ComponentSelection, motherboard: ComponentSelection) -> str | None:
        """Check RAM DDR generation ↔ motherboard support."""
        ...

    def validate_ssd(self, ssd: ComponentSelection, motherboard: ComponentSelection) -> str | None:
        """Check SSD interface ↔ motherboard/case support."""
        ...

    def validate_psu(self, psu: ComponentSelection, build: TowerBuild) -> str | None:
        """Check PSU wattage covers total estimated TDP."""
        ...

    def validate_form_factor(self, case: ComponentSelection, motherboard: ComponentSelection) -> str | None:
        """Check case form factor ↔ motherboard form factor."""
        ...

    def assert_valid(self, build: TowerBuild) -> None:
        """Validate and raise CompatibilityError if any rule fails."""
        ...
```

**Dependencies:** Task 3 (exceptions), Task 5 (schemas)

**Test file:** `tests/test_services/test_compatibility.py`

**Test cases:**
| Test Function | Verifies |
|--------------|----------|
| `test_valid_build_passes` | Fully compatible build returns no errors |
| `test_socket_mismatch` | Mismatched CPU/MB socket detected |
| `test_ram_ddr_mismatch` | DDR4 RAM on DDR5-only board detected |
| `test_ssd_interface_mismatch` | M.2 SSD on board without M.2 slot detected |
| `test_psu_wattage_insufficient` | PSU below total TDP detected |
| `test_psu_wattage_sufficient_with_headroom` | PSU with ≥20% headroom passes |
| `test_form_factor_mismatch` | ATX board in ITX case detected |
| `test_form_factor_atx_in_atx` | ATX board in ATX case passes |
| `test_form_factor_matx_in_atx` | mATX board in ATX case passes (downsizing OK) |
| `test_assert_valid_raises_on_failure` | `assert_valid` raises `CompatibilityError` |
| `test_validate_build_multiple_errors` | Multiple errors collected in single pass |

**Acceptance criteria:**

- [ ] All five compatibility rules from FR-1.3 are implemented
- [ ] Form factor compatibility supports downsizing (mATX in ATX case = OK)
- [ ] PSU validation includes 20% headroom margin
- [ ] `assert_valid()` raises `CompatibilityError` with all error details
- [ ] Engine is a pure class with no external dependencies (easily testable)
- [ ] All quality gates pass

**Complexity:** M

---

### Task 11: SHA-256 uniqueness engine

**Description:** Implement the uniqueness engine that computes a SHA-256 hash of core component SKU sets, checks the Local Registry for duplicates, and supports component swapping when duplicates are detected (FR-1.6).

**Files to create:**

- `src/orchestrator/services/uniqueness.py` — `UniquenessEngine` class

**Signatures:**

```python
# src/orchestrator/services/uniqueness.py
from orchestrator.schemas.inventory import TowerBuild
from orchestrator.services.tower_repository import TowerRepository

class UniquenessEngine:
    """Ensures every build has a unique component combination.

    Computes SHA-256 hash of sorted core SKU set (CPU, MB, RAM, SSD, PSU, Case)
    and verifies against the Local Registry.
    """

    def __init__(self, tower_repository: TowerRepository) -> None: ...

    def compute_hash(self, build: TowerBuild) -> str:
        """Compute SHA-256 hash from core component SKUs.

        Args:
            build: The tower build whose core SKUs to hash.

        Returns:
            64-character hex digest of the sorted SKU set.
        """
        ...

    async def is_unique(self, build: TowerBuild) -> bool:
        """Check if the build hash is unique in the registry."""
        ...

    async def ensure_unique(
        self,
        build: TowerBuild,
        alternatives: dict[str, list["ComponentSelection"]],
        max_attempts: int = 10,
    ) -> TowerBuild:
        """Ensure build uniqueness, swapping secondary components if needed.

        Args:
            build: The initial build to check.
            alternatives: Mapping of category → alternative components for swapping.
            max_attempts: Max swap attempts before raising UniquenessError.

        Returns:
            A unique build (may have swapped components).

        Raises:
            UniquenessError: If no unique combination found after max_attempts.
        """
        ...
```

**Dependencies:** Task 3 (exceptions), Task 5 (schemas), Task 8 (tower repository)

**Test file:** `tests/test_services/test_uniqueness.py`

**Test cases:**
| Test Function | Verifies |
|--------------|----------|
| `test_compute_hash_deterministic` | Same SKUs always produce same hash |
| `test_compute_hash_order_independent` | Hash is sorted — order doesn't matter |
| `test_compute_hash_64_chars` | Hash is exactly 64 hex characters |
| `test_is_unique_true` | Returns True for new hash |
| `test_is_unique_false` | Returns False for existing hash |
| `test_ensure_unique_already_unique` | Returns build unchanged if already unique |
| `test_ensure_unique_swaps_component` | Swaps secondary component to achieve uniqueness |
| `test_ensure_unique_exhausted_raises` | Raises `UniquenessError` after max attempts |

**Acceptance criteria:**

- [ ] Hash is computed from sorted core SKU set: CPU, MB, RAM, SSD, PSU, Case
- [ ] GPU is excluded from hash (same tower + different GPU = different listing)
- [ ] `ensure_unique()` tries swapping SSD → RAM → PSU in order
- [ ] `UniquenessError` raised when all alternatives exhausted
- [ ] All quality gates pass

**Complexity:** M

---

### Task 12: Extend LangGraph state for tower assembly

**Description:** Extend the existing `GraphState` to include fields needed by the Inventory Architect agent — inventory data, selected components, build results, and error tracking.

**Files to modify:**

- `src/orchestrator/graph/state.py` — extend `GraphState` with tower assembly fields

**Signatures:**

```python
# Extended GraphState
class GraphState(BaseModel):
    """Shared state passed through LangGraph nodes."""

    messages: Annotated[list[dict[str, str]], add_messages] = Field(default_factory=list)
    context: dict[str, object] = Field(default_factory=dict)

    # Phase 1: Tower Assembly
    requested_tiers: list[str] = Field(default_factory=list)
    inventory: list[dict[str, object]] = Field(default_factory=list)
    component_specs: dict[str, dict[str, object]] = Field(default_factory=dict)
    completed_builds: list[dict[str, object]] = Field(default_factory=list)
    current_tier: str = ""
    errors: list[str] = Field(default_factory=list)
    run_status: str = "pending"  # pending, running, completed, failed
```

**Dependencies:** None (modifies existing file)

**Test file:** `tests/test_graph/test_state.py`

**Test cases:**
| Test Function | Verifies |
|--------------|----------|
| `test_graph_state_defaults` | New fields have correct defaults |
| `test_graph_state_with_builds` | State with completed builds serializes correctly |
| `test_graph_state_immutable_update` | State update returns new dict without mutation |

**Acceptance criteria:**

- [ ] `GraphState` includes all fields needed by the Inventory Architect
- [ ] Backward compatible — existing `messages` and `context` unchanged
- [ ] Default values allow clean state initialization
- [ ] All quality gates pass

**Complexity:** S

---

### Task 13: Implement Inventory Architect LangGraph node

**Description:** Create the LangGraph node for Agent 1 (Inventory Architect). This node fetches inventory, selects components per tier using LLM tool-calling, validates compatibility, ensures uniqueness, handles PSU/fan auto-add, and persists towers to the registry. Component selection is assisted by the LLM but validated with deterministic rules.

**Files to create:**

- `src/orchestrator/graph/nodes/__init__.py` — package init
- `src/orchestrator/graph/nodes/inventory_architect.py` — node function

**Signatures:**

```python
# src/orchestrator/graph/nodes/inventory_architect.py
from orchestrator.graph.state import GraphState
from orchestrator.services.aiecommerce import AIEcommerceClient
from orchestrator.services.compatibility import CompatibilityEngine
from orchestrator.services.uniqueness import UniquenessEngine
from orchestrator.services.tower_repository import TowerRepository
from orchestrator.services.component_audit_repository import ComponentAuditRepository

async def inventory_architect_node(state: GraphState) -> dict[str, object]:
    """LangGraph node: Inventory Architect (Agent 1).

    Fetches inventory, selects components for each requested tier,
    validates compatibility, ensures uniqueness, and persists builds.

    Args:
        state: Current graph state with requested_tiers.

    Returns:
        State update dict with completed_builds and run_status.
    """
    ...

async def _select_components_for_tier(
    tier: str,
    inventory: list["InventoryItem"],
    specs_cache: dict[int, "ProductSpecs"],
    audit_repo: ComponentAuditRepository,
) -> "TowerBuild":
    """Select components for a specific tier using availability and priority rules.

    Args:
        tier: Target tier (Home, Business, Gaming).
        inventory: Available inventory items.
        specs_cache: Cached product specs.
        audit_repo: For catalog rotation priority.

    Returns:
        A TowerBuild with selected components.
    """
    ...

def _should_add_psu(case_specs: "ProductSpecs") -> bool:
    """Check if the case needs a standalone PSU (FR-1.4)."""
    ...

def _should_add_fans(tier: str, case_specs: "ProductSpecs") -> bool:
    """Check if the gaming build needs extra fans (FR-1.5)."""
    ...
```

**Dependencies:** Task 5 (schemas), Task 7 (aiecommerce client), Task 8 (tower repo), Task 9 (audit repo), Task 10 (compatibility), Task 11 (uniqueness), Task 12 (state)

**Test file:** `tests/test_graph/test_inventory_architect.py`

**Test cases:**
| Test Function | Verifies |
|--------------|----------|
| `test_inventory_architect_home_tier` | Selects cheapest valid components for Home |
| `test_inventory_architect_gaming_tier` | Selects high-end components for Gaming |
| `test_inventory_architect_business_tier` | Selects balanced components for Business |
| `test_inventory_architect_validates_compatibility` | Rejects incompatible selections |
| `test_inventory_architect_ensures_uniqueness` | Produces unique hash, retries if duplicate |
| `test_inventory_architect_auto_adds_psu` | Adds PSU when case doesn't include one |
| `test_inventory_architect_auto_adds_fans` | Adds fans for Gaming builds |
| `test_inventory_architect_prioritizes_rotation` | Components with oldest bundled date selected first |
| `test_inventory_architect_empty_inventory` | Returns error state when no components available |
| `test_inventory_architect_api_error` | Returns error state on API failure |
| `test_inventory_architect_persists_tower` | Tower stored in registry after successful build |
| `test_inventory_architect_records_audit` | Component audit updated with bundle usage |

**Acceptance criteria:**

- [ ] Node implements FR-1.1 through FR-1.7
- [ ] Home tier selects cheapest valid configuration
- [ ] Business tier selects mid-range balanced configuration
- [ ] Gaming tier selects performance-focused configuration with GPU
- [ ] All builds pass compatibility validation
- [ ] All builds produce unique hashes
- [ ] PSU auto-added when case lacks integrated PSU (FR-1.4)
- [ ] 2–3 fans auto-added for Gaming when case lacks them (FR-1.5)
- [ ] Components with oldest `last_bundled_date` are prioritized (FR-1.7)
- [ ] Towers persisted to Local Registry with `component_skus` JSON
- [ ] `ComponentAudit` updated for each used SKU (FR-6.2)
- [ ] Error states propagated via `errors` and `run_status` in graph state
- [ ] All quality gates pass

**Complexity:** L

---

### Task 14: Define LangGraph workflow with Inventory Architect

**Description:** Create the LangGraph `StateGraph` definition with the Inventory Architect node, entry point, conditional edges (success → END, failure → END with error), and compilation. This is the workflow skeleton that will be extended in Phase 2.

**Files to create:**

- `src/orchestrator/graph/workflow.py` — graph definition and compilation

**Signatures:**

```python
# src/orchestrator/graph/workflow.py
from langgraph.graph import StateGraph, END
from orchestrator.graph.state import GraphState
from orchestrator.graph.nodes.inventory_architect import inventory_architect_node

def build_assembly_graph() -> StateGraph:
    """Build and compile the LangGraph assembly workflow.

    Phase 1 graph: START → inventory_architect → END

    Returns:
        Compiled StateGraph ready for invocation.
    """
    ...

def _route_after_assembly(state: GraphState) -> str:
    """Conditional edge: route based on assembly result.

    Returns:
        'end' if successful or failed; future phases add more routes.
    """
    ...
```

**Dependencies:** Task 12 (state), Task 13 (inventory architect node)

**Test file:** `tests/test_graph/test_workflow.py`

**Test cases:**
| Test Function | Verifies |
|--------------|----------|
| `test_build_assembly_graph_compiles` | Graph compiles without error |
| `test_workflow_successful_run` | End-to-end run with mocked services produces builds |
| `test_workflow_failed_run` | API error propagates to final state |
| `test_workflow_empty_tiers` | Empty tier list results in no builds |

**Acceptance criteria:**

- [ ] Graph compiles and runs end-to-end
- [ ] `inventory_architect_node` is the first (and currently only) node
- [ ] Conditional edge routes to END regardless (Phase 1)
- [ ] Graph state is correctly passed through and returned
- [ ] All quality gates pass

**Complexity:** M

---

### Task 15: Implement tower API routes

**Description:** Create FastAPI route handlers for tower listing endpoints — list all towers and get tower detail by hash (FR-7.1, FR-7.2).

**Files to create:**

- `src/orchestrator/api/routes/towers.py` — tower routes

**Files to modify:**

- `src/orchestrator/main.py` — include tower router

**Signatures:**

```python
# src/orchestrator/api/routes/towers.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.core.database import get_db_session
from orchestrator.schemas.tower import TowerDetail, TowerListResponse

router = APIRouter(prefix="/api/v1/towers", tags=["towers"])

@router.get("/", response_model=TowerListResponse)
async def list_towers(
    category: str | None = None,
    status: str | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> TowerListResponse:
    """List all published towers with optional filters."""
    ...

@router.get("/{bundle_hash}", response_model=TowerDetail)
async def get_tower(
    bundle_hash: str,
    session: AsyncSession = Depends(get_db_session),
) -> TowerDetail:
    """Get detailed tower info by bundle hash."""
    ...
```

**Dependencies:** Task 1 (database), Task 6 (tower schemas), Task 8 (tower repository)

**Test file:** `tests/test_api/test_towers.py`

**Test cases:**
| Test Function | Verifies |
|--------------|----------|
| `test_list_towers_empty` | Returns empty list when no towers |
| `test_list_towers_with_data` | Returns correct tower summaries |
| `test_list_towers_filter_category` | Category filter works |
| `test_list_towers_filter_status` | Status filter works |
| `test_get_tower_found` | Returns tower detail for existing hash |
| `test_get_tower_not_found` | Returns 404 for missing hash |

**Acceptance criteria:**

- [ ] `GET /api/v1/towers/` returns paginated tower list (FR-7.1)
- [ ] `GET /api/v1/towers/{bundle_hash}/` returns tower detail (FR-7.2)
- [ ] Category and status query filters supported
- [ ] 404 returned for non-existent bundle hash
- [ ] Response times < 500ms for list, < 200ms for detail
- [ ] Router included in `main.py`
- [ ] All quality gates pass

**Complexity:** M

---

### Task 16: Implement run trigger API route

**Description:** Create a POST endpoint to manually trigger an assembly run (FR-7.4). The endpoint is protected by API key authentication and invokes the LangGraph workflow.

**Files to create:**

- `src/orchestrator/api/routes/triggers.py` — trigger routes

**Files to modify:**

- `src/orchestrator/main.py` — include triggers router

**Signatures:**

```python
# src/orchestrator/api/routes/triggers.py
from fastapi import APIRouter, Depends

from orchestrator.core.security import verify_api_key
from orchestrator.schemas.tower import RunTriggerRequest, RunTriggerResponse

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])

@router.post("/trigger/", response_model=RunTriggerResponse)
async def trigger_assembly_run(
    request: RunTriggerRequest = RunTriggerRequest(),
    _api_key: str = Depends(verify_api_key),
) -> RunTriggerResponse:
    """Manually trigger an assembly run for specified tiers.

    Requires API key authentication via X-API-Key header.
    """
    ...
```

**Dependencies:** Task 4 (security), Task 6 (schemas), Task 14 (workflow)

**Test file:** `tests/test_api/test_triggers.py`

**Test cases:**
| Test Function | Verifies |
|--------------|----------|
| `test_trigger_run_success` | Successful run returns created towers |
| `test_trigger_run_with_specific_tiers` | Only requested tiers are assembled |
| `test_trigger_run_no_api_key` | Returns 401/403 without API key |
| `test_trigger_run_invalid_api_key` | Returns 401 with wrong key |
| `test_trigger_run_workflow_error` | Returns error details on failure |

**Acceptance criteria:**

- [ ] `POST /api/v1/runs/trigger/` triggers the assembly workflow (FR-7.4)
- [ ] API key required via `X-API-Key` header
- [ ] Default tiers: Home, Business, Gaming
- [ ] Response includes tower hashes and error details
- [ ] Unauthorized requests return 401
- [ ] All quality gates pass

**Complexity:** M

---

### Task 17: Update test fixtures and conftest

**Description:** Extend `tests/conftest.py` with shared fixtures for database sessions (in-memory SQLite), mock services, and test data factories. These fixtures are used across all test modules.

**Files to modify:**

- `tests/conftest.py` — add fixtures

**Files to create:**

- `tests/test_models/__init__.py` — package init
- `tests/test_services/__init__.py` — package init
- `tests/test_graph/__init__.py` — package init
- `tests/test_api/__init__.py` — package init
- `tests/test_core/__init__.py` — package init
- `tests/test_schemas/__init__.py` — package init
- `tests/factories.py` — test data factories

**Signatures:**

```python
# tests/conftest.py additions

@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async SQLAlchemy session backed by in-memory SQLite."""
    ...

@pytest.fixture
def mock_aiecommerce_client() -> AIEcommerceClient:
    """Provide a mocked AIEcommerceClient."""
    ...

@pytest.fixture
def sample_inventory() -> list[InventoryItem]:
    """Provide sample inventory data for testing."""
    ...

# tests/factories.py
def make_inventory_item(**overrides: object) -> InventoryItem:
    """Factory for creating test InventoryItem instances."""
    ...

def make_product_specs(**overrides: object) -> ProductSpecs:
    """Factory for creating test ProductSpecs instances."""
    ...

def make_tower_build(**overrides: object) -> TowerBuild:
    """Factory for creating test TowerBuild instances."""
    ...
```

**Dependencies:** Task 1 (database), Task 2 (models), Task 5 (schemas)

**Test file:** N/A (this is test infrastructure)

**Test cases:** N/A (fixtures are tested implicitly by all other tests)

**Acceptance criteria:**

- [ ] `db_session` fixture provides async session with in-memory SQLite
- [ ] All tables are created and torn down per test
- [ ] Factory functions generate valid test data with customizable overrides
- [ ] All existing tests continue to pass
- [ ] All quality gates pass

**Complexity:** M

---

### Task 18: Integration testing — full assembly run

**Description:** Write end-to-end integration tests that exercise the full assembly pipeline: trigger endpoint → LangGraph workflow → inventory fetch (mocked) → compatibility check → uniqueness check → tower persistence → API retrieval.

**Files to create:**

- `tests/test_integration/test_assembly_pipeline.py` — end-to-end tests
- `tests/test_integration/__init__.py` — package init

**Signatures:**

```python
# tests/test_integration/test_assembly_pipeline.py

async def test_full_assembly_run_three_tiers(
    client: AsyncClient, db_session: AsyncSession, mock_inventory: ...,
) -> None:
    """Given inventory, trigger a run and verify 3 towers are created and stored."""
    ...

async def test_assembly_run_produces_unique_hashes(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """Two consecutive runs produce towers with different hashes."""
    ...

async def test_assembly_run_with_incompatible_inventory(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """Given only incompatible components, run reports errors gracefully."""
    ...
```

**Dependencies:** All previous tasks (1–17)

**Test file:** `tests/test_integration/test_assembly_pipeline.py`

**Test cases:**
| Test Function | Verifies |
|--------------|----------|
| `test_full_assembly_run_three_tiers` | 3 towers created and stored for all tiers |
| `test_assembly_run_produces_unique_hashes` | No duplicate hashes across runs |
| `test_assembly_run_with_incompatible_inventory` | Graceful error reporting |
| `test_towers_retrievable_after_run` | GET /api/v1/towers/ returns created towers |
| `test_tower_detail_after_run` | GET /api/v1/towers/{hash}/ returns correct detail |

**Acceptance criteria:**

- [ ] Full pipeline tested end-to-end with mocked external APIs
- [ ] All three tiers produce valid, stored towers
- [ ] Uniqueness is verified across multiple runs
- [ ] Error scenarios handled gracefully
- [ ] Tests use in-memory SQLite
- [ ] ≥ 80% overall coverage maintained
- [ ] All quality gates pass

**Complexity:** M

---

## 6. Testing Strategy

### Unit Tests

| Module                     | Tests    | Mocking                              |
| -------------------------- | -------- | ------------------------------------ |
| Compatibility engine       | 11 tests | None (pure logic)                    |
| Uniqueness engine          | 8 tests  | TowerRepository (mock `hash_exists`) |
| Tower repository           | 9 tests  | In-memory SQLite session             |
| Component audit repository | 5 tests  | In-memory SQLite session             |
| aiecommerce client         | 6 tests  | httpx responses (mock transport)     |
| Inventory architect node   | 12 tests | All services mocked                  |
| Schemas                    | 10 tests | None (validation only)               |

### Integration Tests

| Scope                  | Tests   | Setup                         |
| ---------------------- | ------- | ----------------------------- |
| Tower API routes       | 6 tests | In-memory SQLite + TestClient |
| Trigger API routes     | 5 tests | Mocked workflow + API key     |
| Full assembly pipeline | 5 tests | All mocked externals, real DB |

### Test Data Factories

Centralized in `tests/factories.py` — generates valid `InventoryItem`, `ProductSpecs`, `TowerBuild`, and `ComponentSelection` instances with sensible defaults and override support.

### Coverage Target

≥ 80% line coverage across `src/orchestrator/`, enforced by `pytest --cov`.

---

## 7. Quality Gates

Every task that produces code changes must pass:

```bash
uv run ruff check . --fix    # Lint (zero errors)
uv run ruff format .          # Format (no changes)
uv run mypy .                 # Type check (zero errors)
uv run pytest --cov=src/orchestrator --cov-report=term-missing  # Tests (≥80% coverage)
```

---

## 8. Risks and Mitigations

| Risk                                                                                                | Likelihood | Impact | Mitigation                                                                                               |
| --------------------------------------------------------------------------------------------------- | ---------- | ------ | -------------------------------------------------------------------------------------------------------- |
| **aiecommerce API response format mismatch** — actual response differs from assumed Pydantic schema | Medium     | High   | Define schemas from API docs; add integration test with recorded response; use `extra="allow"` initially |
| **Compatibility rules incomplete** — edge cases in component specs miss some incompatible combos    | Medium     | High   | Start with the 5 core rules (FR-1.3); log all validation decisions; add rules incrementally              |
| **LLM non-determinism in component selection** — different LLM responses for same inventory         | Medium     | Medium | Use structured tool-calling; validate ALL outputs with deterministic rules; set temperature=0            |
| **SQLite vs PostgreSQL behavioral differences** — tests pass on SQLite but fail on PostgreSQL       | Low        | Medium | Use SQLAlchemy abstractions; avoid raw SQL; test critical paths on PostgreSQL in CI                      |
| **Hash uniqueness exhaustion** — limited inventory yields few combinations                          | Low        | Medium | Track remaining capacity; `ensure_unique` max_attempts is configurable; log warnings at 80% capacity     |
| **Circular imports between schemas and services** — deeply nested type references                   | Low        | Low    | Use `TYPE_CHECKING` imports; keep schemas independent of services                                        |

---

## 9. Suggested Implementation Order

```
Task  1: Configure async database session management       [S]  (no deps)
Task  3: Create custom exception classes                   [S]  (no deps)
Task  4: Implement API key authentication dependency       [S]  (no deps)
Task  5: Define inventory Pydantic schemas                 [S]  (no deps)
Task  6: Define tower API Pydantic schemas                 [S]  (no deps)
Task 12: Extend LangGraph state for tower assembly         [S]  (no deps)
─── foundation complete ───
Task  2: Define Local Registry SQLAlchemy models           [S]  (← Task 1)
Task 17: Update test fixtures and conftest                 [M]  (← Tasks 1, 2, 5)
─── data layer complete ───
Task  7: Extend aiecommerce client with inventory methods  [M]  (← Tasks 3, 5)
Task  8: Tower repository (database CRUD)                  [M]  (← Tasks 1, 2)
Task  9: Component audit repository                        [M]  (← Tasks 1, 2)
Task 10: Compatibility validation engine                   [M]  (← Tasks 3, 5)
Task 11: SHA-256 uniqueness engine                         [M]  (← Tasks 3, 5, 8)
─── service layer complete ───
Task 13: Implement Inventory Architect LangGraph node      [L]  (← Tasks 5, 7–12)
Task 14: Define LangGraph workflow                         [M]  (← Tasks 12, 13)
─── agent layer complete ───
Task 15: Implement tower API routes                        [M]  (← Tasks 1, 6, 8)
Task 16: Implement run trigger API route                   [M]  (← Tasks 4, 6, 14)
─── API layer complete ───
Task 18: Integration testing — full assembly run           [M]  (← All)
```

### Total Estimated Effort

- **S tasks:** 6 (< 2 hrs each → ~12 hrs)
- **M tasks:** 11 (2–8 hrs each → ~44 hrs)
- **L tasks:** 1 (> 8 hrs → ~12 hrs)
- **Total:** ~68 hrs (≈ 3.5 weeks at 20 hrs/week)
