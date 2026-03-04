# Product Requirements Document (PRD): PC Assembler & Marketing Agentic System

## 1. Executive Summary

The PC Assembler & Marketing Agentic System is a stateful, multi-agent orchestration platform that automatically assembles unique PC configurations across three market tiers (Home, Business, Gaming), bundles them with category-appropriate peripherals, generates multimedia marketing assets, and publishes fully priced listings to MercadoLibre — all while continuously monitoring stock and pricing to keep listings accurate. Built for a small e-commerce operation selling assembled PCs in Latin America, the system eliminates the manual effort of catalog creation, pricing calculation, and marketplace management by delegating each concern to a specialized AI agent coordinated through a LangGraph workflow.

**Problem Statement:** Creating and maintaining unique PC build listings on MercadoLibre is a labor-intensive, error-prone process. Each listing requires component compatibility verification, pricing calculation (parts + assembly margin + marketplace fees), professional creative assets, and continuous stock monitoring to avoid selling builds whose parts are no longer available ("ghost selling").

**Proposed Solution:** A FastAPI-based agent orchestrator powered by LangGraph that runs 2–3 times daily to produce never-before-seen PC configurations, automatically generates marketing media, publishes to MercadoLibre, and monitors inventory every 2 hours to pause or dynamically update listings as stock changes.

## 2. Product Overview

### Background and Context

The system extends an existing Django-based platform called **aiecommerce**, which already handles hardware catalog scraping, normalization, and enrichment from distributors (e.g., Tecnomega). That platform serves as the "Single Source of Truth" for component data — SKUs, prices, stock levels, and technical specifications — exposed through a secure REST API (Django Rest Framework).

This project (**aiecommerce-agents**) is the second layer in the architecture: a decoupled, standalone FastAPI application that consumes the aiecommerce API and orchestrates four specialized agents to automate the full lifecycle of assembled PC listings on MercadoLibre.

### Product Vision and Positioning

The agent orchestrator transforms a raw hardware catalog into a continuously refreshed storefront of unique assembled PCs, eliminating manual work while ensuring every listing is technically valid, competitively priced, visually distinctive, and stock-accurate.

## 3. Goals and Success Metrics

| Objective                             | KPI                                                         | Target                     | Timeframe      |
| ------------------------------------- | ----------------------------------------------------------- | -------------------------- | -------------- |
| Automate PC assembly listing creation | Unique builds published per day                             | ≥ 6 (2 runs × 3 tiers)     | By MVP launch  |
| Eliminate ghost selling               | Listings with out-of-stock core components remaining active | 0                          | Continuous     |
| Ensure technical validity             | Builds failing compatibility checks post-publication        | 0%                         | Continuous     |
| Maximize catalog coverage             | Components with `last_bundled_date` older than 30 days      | < 10% of active inventory  | Within 60 days |
| Reduce manual effort                  | Hours spent on manual listing creation per week             | < 1 hour (monitoring only) | By Phase 2     |
| Maintain listing freshness            | Time between stock-out detection and listing pause/update   | < 2 hours                  | Continuous     |

### Definition of Success

The system is successful when it autonomously produces 6+ unique, technically valid, fully priced PC build listings per day across all three tiers, publishes them to MercadoLibre with compliant multimedia assets, and keeps every active listing stock-accurate within a 2-hour window — with zero manual intervention required.

## 4. Non-Goals (Out of Scope)

- **Customer-facing storefront or website** — the system publishes exclusively to MercadoLibre.
- **Order fulfillment or logistics** — order processing, shipping, and delivery tracking remain manual or handled by other systems.
- **Payment processing** — handled entirely by MercadoLibre.
- **aiecommerce modifications** — the Django data provider is a separate project; this PRD covers only the agent orchestrator.
- **Multi-marketplace support** — only MercadoLibre is targeted in the initial version. Amazon, Linio, or other marketplaces are deferred.
- **Customer support or chatbot agents** — no end-user-facing AI interactions.
- **Physical assembly instructions** — the system selects components but does not generate assembly guides for warehouse staff.
- **GPU-intensive local media rendering** — creative asset generation relies on external API services, not local GPU compute.

## 5. Target Users and Use Cases

### User Personas

**Persona 1: The E-Commerce Operator (Primary)**

- Small business owner running an online PC shop via MercadoLibre.
- Currently spends 3–5 hours daily manually selecting components, verifying compatibility, calculating prices, creating images, and publishing listings.
- Needs: Automation of the entire listing lifecycle with confidence that every build is valid and every listing is stock-accurate.

**Persona 2: The System Administrator**

- Technical team member responsible for deploying, configuring, and monitoring the agent system.
- Needs: Clear configuration options, observable logs, and manual override capabilities (pause/resume runs, force a sentinel cycle).

### User Stories

1. **As an** e-commerce operator, **I want** the system to automatically generate 3 unique PC builds per run (Home, Business, Gaming) **so that** my MercadoLibre storefront always has fresh, varied listings without manual work.

2. **As an** e-commerce operator, **I want** every generated build to be technically valid (compatible socket, sufficient PSU wattage, correct RAM generation) **so that** I never sell an impossible configuration.

3. **As an** e-commerce operator, **I want** listings to be automatically paused when a core component goes out of stock **so that** I never sell a PC I cannot build.

4. **As an** e-commerce operator, **I want** peripheral components to be dynamically replaced when they go out of stock **so that** bundle listings stay active and revenue is not lost unnecessarily.

5. **As a** system administrator, **I want** to view the status of all published listings, their component mappings, and sentinel activity **so that** I can monitor system health and intervene if needed.

### Acceptance Criteria (Key Scenarios)

**Scenario: Unique Tower Assembly**

- **Given** the aiecommerce API returns available CPUs, motherboards, RAM, SSDs, PSUs, and cases
- **When** the Inventory Architect agent runs for the "Gaming" tier
- **Then** it produces a build where all components are socket/DDR/form-factor compatible, the PSU wattage covers estimated TDP, and the bundle hash does not exist in the Local Registry

**Scenario: Core Component Stock-Out**

- **Given** a published Gaming tower listing with `ml_id = ML-12345` containing motherboard SKU `MB-A320`
- **When** the Sentinel detects `MB-A320` stock has dropped to 0
- **Then** the system pauses listing `ML-12345` on MercadoLibre within the current sentinel cycle (≤ 2 hours)

**Scenario: Peripheral Dynamic Replacement**

- **Given** a published Business bundle listing containing keyboard SKU `KB-100`
- **When** the Sentinel detects `KB-100` stock is 0 but the tower components are all in stock
- **Then** the system selects a replacement keyboard with similar specs and price, recalculates the bundle price, updates the MercadoLibre listing description and price, and does NOT pause the listing

## 6. Functional Requirements

### 6.1 Tower Assembly (Agent 1: Inventory Architect) — Must Have

- FR-1.1: The system shall fetch the current inventory from the aiecommerce API, filtered by component category (CPU, motherboard, RAM, GPU, SSD, PSU, case), including only items with `is_active=True` and `available_quantity > 0`.
- FR-1.2: The system shall select components for three tiers per run:
  - **Home**: Cheapest technically valid configuration.
  - **Business**: Medium-tier balance between cost and reliable performance.
  - **Gaming**: Top-tier components focused on performance (high-end GPUs, high-speed RAM) and aesthetics.
- FR-1.3: The system shall validate technical compatibility for every build:
  - CPU socket matches motherboard socket.
  - RAM generation (DDR4/DDR5) matches motherboard support.
  - SSD form factor (M.2/2.5") is supported by the motherboard or case.
  - PSU wattage is ≥ estimated total TDP of CPU + GPU + 20% headroom.
  - Case form factor accommodates the motherboard (ATX, mATX, ITX).
- FR-1.4: The system shall automatically add a standalone PSU if the selected case does not include one (detected via case specs).
- FR-1.5: For Gaming tier builds, the system shall automatically add 2–3 extra cooling fans if the selected case does not include them.
- FR-1.6: The system shall compute a SHA-256 hash of the core component SKU set (CPU, MB, RAM, SSD, PSU, Case) and verify uniqueness against the Local Registry before finalizing. If the hash exists, the system shall swap a secondary component (e.g., different SSD brand or RAM configuration) and recheck until a unique combination is achieved.
- FR-1.7: The system shall prioritize components with the oldest `last_bundled_date` to ensure full catalog rotation.

### 6.2 Bundle Creation (Agent 2: Bundle Creator) — Must Have

- FR-2.1: The system shall be triggered immediately after tower creation to add peripherals appropriate to the tier.
- FR-2.2: Tiered peripheral selection:
  - **Home**: Basic keyboard, mouse, and monitor (cost-effective).
  - **Business**: Ergonomic keyboard, mouse, and standard office monitor.
  - **Gaming**: Mechanical keyboard, gaming mouse, high-refresh-rate monitor (≥ 144Hz), and speakers.
- FR-2.3: The system shall create a "Complete Kit" definition that links the peripheral set to the parent tower and stores all SKUs in the Local Registry.

### 6.3 Creative Asset Generation (Agent 3: Creative Director) — Must Have

- FR-3.1: The system shall generate 4 distinct product images per listing (tower and bundle).
- FR-3.2: The system shall generate 1 unique promotional video per listing.
- FR-3.3: Even if the same case model is reused across builds, each video shall feature different lighting, camera angles, and motion graphics to be visually distinct.
- FR-3.4: Videos shall include dynamic technical specification overlays displaying exact component details (e.g., "Dual-Channel 16GB DDR4 3200MHz").
- FR-3.5: All generated media shall comply with MercadoLibre Rule 25505: neutral backgrounds, no watermarks, no contact information, no text overlays with promotions.

### 6.4 Publication (Agent 4: Channel Manager) — Must Have

- FR-4.1: The system shall calculate the final listing price as: `Sum(component prices) + Assembly Margin + MercadoLibre Fees`.
- FR-4.2: Assembly margin and ML fee percentages shall be configurable via environment variables.
- FR-4.3: The system shall publish the listing to MercadoLibre via the MercadoLibre API, including title, description, price, images, and video.
- FR-4.4: The system shall store the returned `mercadolibre_id` in the Local Registry, mapped to every individual component SKU used in that build.

### 6.5 Stock & Price Monitoring (Hybrid Sentinel) — Must Have

- FR-5.1: The Sentinel shall execute every 2 hours (configurable via environment variable).
- FR-5.2: **Tower Sentinel (Hard Pause)**: If any core component (CPU, MB, RAM, SSD, PSU, Case) of an active listing reaches 0 stock, the system shall immediately pause the MercadoLibre listing. The listing shall not be resumed until the exact core component is restocked.
- FR-5.3: **Bundle Sentinel (Dynamic Replacement)**: If a peripheral component reaches 0 stock but all tower components are available:
  - The system shall find a replacement peripheral with similar technical specs and price from the aiecommerce inventory.
  - The system shall recalculate the total bundle price.
  - The system shall update the MercadoLibre listing description, replacing the old peripheral text with the new one.
  - The system shall update the listing price and stock without pausing it.
- FR-5.4: The Sentinel shall also detect price changes in components and recalculate listing prices accordingly.

### 6.6 Local Registry — Must Have

- FR-6.1: The system shall maintain a local SQLite database (async via aiosqlite) with the following tables:
  - **published_towers**: `bundle_hash` (PK), `ml_id`, `category` (Home/Business/Gaming), `status` (Active/Paused), `created_at`, `updated_at`.
  - **published_bundles**: `bundle_id` (PK), `tower_hash` (FK), `peripheral_skus` (JSON), `ml_id`, `created_at`, `updated_at`.
  - **component_audit**: `sku` (PK), `category`, `last_bundled_date`, `bundle_count`, `stock_level`, `updated_at`.
- FR-6.2: The system shall update `last_bundled_date` and `bundle_count` in the component_audit table every time a component is used in a new build.

### 6.7 API Endpoints — Should Have

- FR-7.1: `GET /api/v1/towers/` — List all published towers with status, category, and component summary.
- FR-7.2: `GET /api/v1/towers/{bundle_hash}/` — Get detailed tower info including all component SKUs and ML listing status.
- FR-7.3: `GET /api/v1/bundles/` — List all published bundles with status and peripheral info.
- FR-7.4: `POST /api/v1/runs/trigger/` — Manually trigger an assembly run (for admin use).
- FR-7.5: `POST /api/v1/sentinel/trigger/` — Manually trigger a sentinel cycle (for admin use).
- FR-7.6: `GET /api/v1/health/` — Health check endpoint (already implemented).

### 6.8 Scheduling — Should Have

- FR-8.1: The system shall support configurable scheduling for assembly runs (default: 3 times daily) and sentinel cycles (default: every 2 hours).
- FR-8.2: Scheduling shall be managed via an external scheduler (e.g., cron, systemd timer, or cloud scheduler) calling the trigger endpoints, or via an internal async scheduler.

### 6.9 Assembled Log Feedback — Could Have

- FR-9.1: The system shall report successful combinations back to the aiecommerce API via `POST /api/v1/agent/assembled-log/` for cross-system tracking.

## 7. Non-Functional Requirements

### Performance

- Assembly run (3 tiers) shall complete in < 5 minutes, excluding creative asset generation.
- Creative asset generation shall complete in < 10 minutes per listing.
- Sentinel cycle shall complete in < 3 minutes for up to 500 active listings.
- API endpoints shall respond in < 500ms for list operations and < 200ms for single-resource operations.

### Security and Privacy

- All communication with the aiecommerce API shall use HTTPS with Bearer token authentication.
- MercadoLibre OAuth2 credentials shall be stored as environment variables, never hard-coded.
- The trigger endpoints (`/runs/trigger/`, `/sentinel/trigger/`) shall be protected with API key authentication.
- CORS shall be restricted to known origins only.

### Reliability and Availability

- The system shall gracefully handle aiecommerce API downtime by retrying with exponential backoff (max 3 retries, base delay 5 seconds).
- The system shall gracefully handle MercadoLibre API downtime by queueing failed operations for the next sentinel cycle.
- Failed assembly runs shall not affect previously published listings.
- The system shall log all operations (assembly, publication, sentinel actions) with structured JSON logging.

### Scalability

- The system shall handle up to 500 active MercadoLibre listings simultaneously.
- The Local Registry (SQLite) is sufficient for the expected data volume (< 10,000 records). Migration to PostgreSQL shall be considered if volume exceeds this threshold.

### Compliance

- All MercadoLibre listings shall comply with MercadoLibre's Terms of Service and publication rules, specifically Rule 25505 for media content.
- The system shall not store customer personal data — all customer interaction happens on MercadoLibre.

## 8. Tech Stack and Architecture Overview

### Technology Choices

| Component           | Technology                      | Justification                                                        |
| ------------------- | ------------------------------- | -------------------------------------------------------------------- |
| Runtime             | Python 3.13+                    | Full type annotation support, async-first ecosystem                  |
| Web Framework       | FastAPI + uvicorn (ASGI)        | Async-native, automatic OpenAPI docs, dependency injection           |
| Agent Orchestration | LangGraph                       | Stateful multi-agent workflows with conditional edges, checkpointing |
| LLM Integration     | LangChain + langchain-openai    | Abstracted LLM interface, tool-use support                           |
| Data Validation     | Pydantic v2 + pydantic-settings | Request/response schemas, environment config                         |
| Database ORM        | SQLAlchemy (async) + aiosqlite  | Local Registry persistence with async support                        |
| HTTP Client         | httpx (async)                   | Outbound API calls to aiecommerce and MercadoLibre                   |
| Linter/Formatter    | Ruff                            | Fast, single-tool Python linting and formatting                      |
| Type Checker        | Mypy (strict mode)              | Static type safety                                                   |
| Testing             | pytest + pytest-asyncio + httpx | Async test support with FastAPI test client                          |
| Package Manager     | uv                              | Fast dependency resolution and virtual environment management        |

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Agent Orchestrator (FastAPI)                     │
│                                                                     │
│  ┌───────────────────── LangGraph Workflow ───────────────────────┐ │
│  │                                                                │ │
│  │  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   │ │
│  │  │ Agent 1  │──▶│ Agent 2  │──▶│ Agent 3  │──▶│ Agent 4  │   │ │
│  │  │Inventory │   │ Bundle   │   │ Creative │   │ Channel  │   │ │
│  │  │Architect │   │ Creator  │   │ Director │   │ Manager  │   │ │
│  │  └──────────┘   └──────────┘   └──────────┘   └──────────┘   │ │
│  │                                                                │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────────────────┐  │
│  │  Sentinel   │   │  Local      │   │  API Routes             │  │
│  │  (Scheduled)│   │  Registry   │   │  /towers, /bundles,     │  │
│  │             │   │  (SQLite)   │   │  /runs, /sentinel       │  │
│  └──────┬──────┘   └─────────────┘   └─────────────────────────┘  │
│         │                                                           │
└─────────┼───────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────┐         ┌─────────────────┐       ┌──────────────┐
│  aiecommerce    │         │  MercadoLibre   │       │  OpenAI /    │
│  REST API       │         │  API            │       │  Media APIs  │
│  (Django/DRF)   │         │  (OAuth2)       │       │              │
└─────────────────┘         └─────────────────┘       └──────────────┘
```

### Source Layout

```
src/orchestrator/
├── main.py                    # FastAPI app entry point
├── api/routes/                # HTTP route handlers
│   ├── health.py              # Health check (existing)
│   ├── towers.py              # Tower listing endpoints
│   ├── bundles.py             # Bundle listing endpoints
│   └── triggers.py            # Manual run/sentinel triggers
├── services/                  # External API clients
│   ├── aiecommerce.py         # aiecommerce API client (existing)
│   ├── mercadolibre.py        # MercadoLibre API client
│   └── media.py               # Creative asset generation client
├── models/                    # SQLAlchemy entities (Local Registry)
│   ├── base.py                # Declarative base (existing)
│   ├── tower.py               # PublishedTower model
│   ├── bundle.py              # PublishedBundle model
│   └── component_audit.py     # ComponentAudit model
├── schemas/                   # Pydantic schemas
│   ├── common.py              # Shared schemas (existing)
│   ├── inventory.py           # aiecommerce inventory schemas
│   ├── tower.py               # Tower request/response schemas
│   ├── bundle.py              # Bundle request/response schemas
│   └── mercadolibre.py        # ML API request/response schemas
├── graph/                     # LangGraph definitions
│   ├── state.py               # Graph state (existing, to be extended)
│   ├── workflow.py            # Main graph definition and edges
│   └── nodes/
│       ├── inventory_architect.py  # Agent 1: Tower assembly
│       ├── bundle_creator.py       # Agent 2: Peripheral bundling
│       ├── creative_director.py    # Agent 3: Media generation
│       └── channel_manager.py      # Agent 4: ML publication
├── core/                      # Global config and utilities
│   ├── config.py              # Settings (existing, to be extended)
│   ├── security.py            # API key auth guards
│   ├── logging.py             # Structured logging (existing)
│   └── exceptions.py          # Custom exception classes
scripts/
├── sentinel.py                # Sentinel monitoring loop (existing skeleton)
tests/
├── conftest.py                # Shared fixtures (existing)
├── test_main.py               # App integration tests (existing)
├── test_services/             # Service unit tests
├── test_graph/                # Graph node unit tests
├── test_api/                  # Route integration tests
└── test_models/               # Model/repository tests
```

## 9. Integration Points and Dependencies

### External Systems

| System               | Purpose                                             | Protocol            | Auth                         |
| -------------------- | --------------------------------------------------- | ------------------- | ---------------------------- |
| aiecommerce REST API | Source of component inventory, specs, pricing       | HTTPS REST          | Bearer API Key               |
| MercadoLibre API     | Listing CRUD, status management, media upload       | HTTPS REST (OAuth2) | OAuth2 access/refresh tokens |
| OpenAI API           | LLM-powered agent reasoning, description generation | HTTPS REST          | API Key                      |
| Media Generation API | Product images and video creation                   | HTTPS REST          | API Key (TBD)                |

### aiecommerce API Endpoints Consumed

- `GET /api/v1/agent/inventory/` — Filtered active inventory with stock > 0
- `GET /api/v1/agent/product/{id}/specs/` — Deep technical specs for compatibility checking
- `POST /api/v1/agent/assembled-log/` — Report successful combinations (feedback loop)

### Data Synchronization

- The aiecommerce platform runs `sync_price_list` and `scrape_tecnomega` tasks that update inventory. The agent orchestrator consumes this data on each run and sentinel cycle.
- No real-time push mechanism exists — the orchestrator pulls data at scheduled intervals.

### Critical Library Dependencies

- `langgraph >= 0.4.1` — Multi-agent workflow orchestration
- `langchain >= 0.3.25` — LLM abstraction layer
- `langchain-openai >= 0.3.24` — OpenAI model bindings
- `fastapi >= 0.135.1` — Web framework
- `httpx >= 0.28.1` — Async HTTP client
- `sqlalchemy[asyncio] >= 2.0.41` — Database ORM
- `aiosqlite >= 0.21.0` — Async SQLite driver
- `pydantic-settings >= 2.9.1` — Environment configuration

## 10. Phases and Milestones

### Phase 1: Foundation & Tower Assembly (MVP) — Weeks 1–4

**Deliverables:**

1. Local Registry schema (SQLAlchemy models for `published_towers`, `published_bundles`, `component_audit`) with async database session management.
2. aiecommerce API client with full inventory and specs fetching.
3. Agent 1 (Inventory Architect): Component selection with compatibility validation, uniqueness engine, and dependency resolver (PSU/fan auto-add).
4. LangGraph workflow with Agent 1 node, state management, and conditional edges.
5. Admin API endpoints for towers and manual run triggers.
6. Unit and integration tests with ≥ 80% coverage.

**Milestone:** The system can fetch inventory, assemble valid unique towers for all 3 tiers, store them in the Local Registry, and expose them via API.

### Phase 2: Bundling & Publication — Weeks 5–8

**Deliverables:**

1. Agent 2 (Bundle Creator): Tiered peripheral selection and Complete Kit creation.
2. MercadoLibre API client: OAuth2 authentication, listing CRUD, media upload.
3. Agent 4 (Channel Manager): Price calculation and MercadoLibre publication.
4. Extended LangGraph workflow: Tower → Bundle → Publication pipeline.
5. Bundle API endpoints.
6. Sentinel skeleton with Tower Sentinel (Hard Pause) logic.

**Milestone:** The system can assemble towers, bundle peripherals, calculate prices, and publish complete listings to MercadoLibre. Core component stock-outs trigger listing pauses.

### Phase 3: Creative Assets & Full Sentinel — Weeks 9–12

**Deliverables:**

1. Agent 3 (Creative Director): Integration with media generation APIs for images and video.
2. Media compliance validation (MercadoLibre Rule 25505).
3. Bundle Sentinel (Dynamic Replacement): Peripheral swap, price recalculation, and listing update without pause.
4. Complete LangGraph workflow: Tower → Bundle → Creative → Publication.
5. Assembled-log feedback to aiecommerce API.

**Milestone:** Full end-to-end pipeline operational. All four agents coordinated. Sentinel handles both hard pauses and dynamic replacements.

### Phase 4: Scheduling, Observability & Hardening — Weeks 13–16

**Deliverables:**

1. Scheduling infrastructure (configurable run frequency and sentinel intervals).
2. Structured JSON logging for production observability.
3. Retry logic and error recovery for all external API calls.
4. Performance optimization (caching, query optimization).
5. Comprehensive monitoring dashboard data (via API endpoints).
6. Load testing and production deployment.

**Milestone:** Production-ready system running autonomously with full observability.

## 11. Risks and Mitigation Strategies

| Risk                                                                                                                   | Likelihood | Impact | Mitigation                                                                                                                                     |
| ---------------------------------------------------------------------------------------------------------------------- | ---------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **aiecommerce API unavailability** — scraping or sync failures cause stale inventory data                              | Medium     | High   | Implement retry with exponential backoff; skip run if API is unreachable and alert operator; sentinel validates stock before every action      |
| **MercadoLibre API rate limits** — publishing too many listings in quick succession triggers throttling                | Medium     | Medium | Implement rate-limiting in the ML client; stagger publications with configurable delays; respect `X-RateLimit` headers                         |
| **MercadoLibre OAuth token expiry** — access token expires mid-run causing publication failures                        | Medium     | High   | Implement automatic token refresh using the refresh token; store tokens securely; alert on refresh failures                                    |
| **Compatibility validation gaps** — edge cases in component specs cause invalid builds                                 | Medium     | High   | Maintain a comprehensive compatibility rule set; log all validation decisions for audit; implement a manual review queue for flagged builds    |
| **Creative API cost escalation** — generating 4 images + 1 video per listing at scale becomes expensive                | Medium     | Medium | Track per-listing media cost; implement configurable quality tiers; cache and reuse common visual elements                                     |
| **Hash collision / uniqueness exhaustion** — limited inventory makes it impossible to generate new unique combinations | Low        | Medium | Track remaining combination capacity; alert when approaching exhaustion; allow manual override to skip uniqueness check                        |
| **SQLite concurrency under load** — simultaneous sentinel and assembly runs cause database locks                       | Low        | Medium | Use WAL mode for SQLite; if concurrency issues arise, migrate to PostgreSQL                                                                    |
| **LLM hallucination in agent reasoning** — the LLM selects incompatible components or generates incorrect descriptions | Medium     | High   | Use structured tool-calling (not free-text reasoning) for component selection; validate all outputs against hard-coded rules before persisting |

## 12. Testing and Validation Strategy

### Unit Testing

- **Scope:** All service classes, graph nodes, utility functions, and Pydantic schema validation.
- **Coverage target:** ≥ 80% line coverage, enforced in CI.
- **Framework:** `pytest` with `pytest-asyncio` for async tests.
- **Mocking:** Mock external API calls at the client boundary (`aiecommerce`, `mercadolibre`, media services) using `pytest-mock` or `unittest.mock.patch`. Never mock internal business logic.

### Integration Testing

- **Scope:** API routes tested via `httpx.AsyncClient` with the FastAPI `app`.
- **Database:** Use in-memory SQLite for test database sessions.
- **Coverage:** All CRUD endpoints, trigger endpoints, and error responses.

### Graph / Workflow Testing

- **Scope:** Test each LangGraph node in isolation with mocked dependencies, then test the complete graph with deterministic inputs.
- **Validation:** Assert that graph output state matches expected component selections, bundle compositions, and pricing calculations.

### End-to-End Testing

- **Scope:** Full pipeline from inventory fetch to MercadoLibre publication using recorded API responses (VCR-style fixtures).
- **Sentinel testing:** Simulate stock-out scenarios and verify correct pause/replacement behavior.

### Performance Testing

- **Assembly run:** Target < 5 minutes for 3 tiers with mocked external APIs.
- **Sentinel cycle:** Target < 3 minutes for 500 active listings with mocked external APIs.
- **API response times:** Validate < 500ms for list endpoints under normal load.

### Manual / UAT Testing

- **Pre-launch:** Operator reviews 10+ auto-generated listings on MercadoLibre sandbox for accuracy, pricing, and media quality.
- **Sentinel validation:** Manually zero out component stock in aiecommerce and verify correct listing pause/update behavior.

## 13. Open Questions and Future Work

### Open Questions

1. **Media generation provider**: Which API service(s) will be used for image and video generation? Candidates include OpenAI DALL-E/Sora, Stability AI, or specialized product photography APIs. Decision impacts cost, quality, and compliance.
2. **MercadoLibre sandbox environment**: Is a sandbox/test environment available for development and testing without affecting live listings?
3. **Assembly margin and ML fee structure**: What are the exact margin percentages and fee formulas? Are they flat rates or tiered by category/price range?
4. **"Similar peripheral" definition for Bundle Sentinel**: What constitutes a "similar" replacement peripheral? Same brand? Same price range (±10%)? Same category? Need explicit matching criteria.
5. **Catalog rotation strategy**: Should the system strictly enforce oldest-first rotation, or weight it by margin or historical sales performance?
6. **GPU requirement by tier**: Are GPUs required for all tiers, or only Gaming? Many Home/Business builds use integrated graphics.
7. **Scheduling infrastructure**: Should the scheduler be internal (async task scheduler within the FastAPI process) or external (cron/systemd/cloud scheduler calling trigger endpoints)?

### Future Work (Post-Launch Iterations)

- **Multi-marketplace support**: Extend the Channel Manager to publish to Amazon, Linio, and other Latin American marketplaces.
- **Sales performance feedback loop**: Ingest MercadoLibre sales data to inform tier selection and component prioritization (favor configurations that sell better).
- **Dynamic pricing optimization**: Use market data and competitor pricing to optimize assembly margins in real-time.
- **A/B testing for creative assets**: Generate multiple visual styles per listing and track which performs better.
- **Warehouse integration**: Connect to warehouse management systems for automatic pick-list generation when orders are placed.
- **Notification system**: Alert operators via email/Slack/Telegram on sentinel actions, failed runs, or low combination capacity.
- **Admin dashboard**: Web UI for monitoring system status, reviewing listings, and managing overrides.
