# PRD: Agent Orchestrator — Automated PC Bundle Pipeline

- **Version:** 1.0
- **Date:** 2026-03-03
- **Audience:** Development team

## 1. Product overview

### 1.1 Document title and version

- PRD: Agent Orchestrator — Automated PC Bundle Pipeline
- Version: 1.0

### 1.2 Product summary

The Agent Orchestrator is a stateful multi-agent system that transforms raw hardware inventory from the *aiecommerce* data provider into unique, market-ready PC bundle listings on MercadoLibre. It autonomously handles component selection, compatibility validation, pricing, media generation, and publication — replacing manual catalog management entirely.

The system operates on a 2–3 times daily publishing cadence, generating one unique bundle per run for each of three categories (Home, Business, Gaming). A parallel Sentinel loop runs every 2 hours to synchronize inventory levels, pausing or dynamically updating live listings to eliminate "ghost selling" (selling items that are out of stock).

The project follows a Host-Engine architecture: FastAPI serves as the operational shell (API, auth, scheduling), while LangGraph orchestrates the complex, non-linear assembly logic through a stateful directed graph. The existing Phase 1 foundation (FastAPI skeleton, project structure, tooling) is already in place.

## 2. Goals

### 2.1 Business goals

- Eliminate manual PC bundle creation and catalog management on MercadoLibre.
- Publish up to 50 active listings across Home, Business, and Gaming categories.
- Achieve zero ghost-sell incidents through real-time stock synchronization.
- Maximize hardware rotation by prioritizing least-recently-bundled components.
- Maintain unique listings to avoid MercadoLibre duplicate-listing penalties.

### 2.2 User goals

- Developers can extend the agent pipeline with new nodes without modifying existing ones.
- Operators can monitor system health, listing status, and Sentinel activity through API endpoints.
- The system runs autonomously on Railway with minimal manual intervention after deployment.

### 2.3 Non-goals

- Building a customer-facing storefront or shopping cart.
- Supporting marketplaces other than MercadoLibre in this version.
- Implementing real-time chat or customer support automation.
- Handling order fulfillment, shipping tracking, or post-sale logistics.
- Building a custom image/video rendering pipeline (media generation service is TBD and will be integrated behind an abstract interface).

## 3. User personas

### 3.1 Key user types

- Platform operator (the business owner running the system).
- Developer (engineering team maintaining and extending the codebase).

### 3.2 Basic persona details

- **Operator (Juan)**: Business owner who manages the PC hardware inventory via the *aiecommerce* platform. Needs the orchestrator to autonomously translate that inventory into profitable MercadoLibre listings without daily manual work. Monitors the system through API dashboards and logs.
- **Developer**: Backend engineer responsible for adding new agent nodes, adjusting pricing formulas, and maintaining integrations. Needs clean abstractions, strict typing, and comprehensive test coverage.

### 3.3 Role-based access

- **System (internal)**: Full access to all API endpoints, database, and external services. Executes the publication pipeline and Sentinel cycles.
- **Operator (API consumer)**: Authenticated access to health, listing status, and manual trigger endpoints. Cannot modify graph logic or database schema directly.
- **External services (MercadoLibre, aiecommerce)**: Scoped OAuth2/API-key access with least-privilege permissions.

## 4. Functional requirements

- **Publication pipeline graph** (Priority: High)
  - The system must execute a stateful LangGraph workflow that progresses through inventory selection, bundle assembly, media generation, pricing, and publication stages.
  - The graph must produce one unique bundle per category (Home, Business, Gaming) per run.
  - Pipeline runs must be triggerable via API endpoint and via scheduled cron (2–3 times daily).
  - The graph state must be immutable — nodes return state update dicts, never mutate in place.

- **Inventory Architect node** (Priority: High)
  - Must select 6 core tower components: CPU, Motherboard, RAM, SSD, PSU, Case.
  - Must resolve hardware dependencies (e.g., if selected case lacks an integrated PSU, a standalone PSU must be added).
  - Must prioritize components with the oldest `last_bundled_date` (LRU selection).
  - Must validate that the selected combination has not been previously published by checking the SHA-256 tower hash against the `published_towers` registry.
  - If a duplicate hash is detected, must iterate and select an alternative configuration.

- **Bundle Creator node** (Priority: High)
  - Must append category-specific peripherals to the core tower (e.g., monitors, keyboards, mice, headsets).
  - Peripheral selection rules must be configurable per category.
  - Must record the full bundle (tower + peripherals) in the `published_bundles` registry.

- **Creative Director node** (Priority: Medium)
  - Must trigger generation of 4 unique product images per listing.
  - Must trigger generation of 1 technical specification video per listing.
  - Generated media must comply with MercadoLibre visual rules (minimum resolution, aspect ratio, no watermarks).
  - The media generation service must be abstracted behind a `Protocol`/`ABC` interface so the provider can be swapped.

- **Financial Strategist node** (Priority: High)
  - Must calculate the final listing price using the tiered margin formula: `final_price = (component_costs + assembly_fee + shipping_cost) / (1 - marketplace_fees - tax_rate)`.
  - Margin tiers, assembly fees, and shipping costs must be configurable via environment or settings.
  - Must produce a cost breakdown attached to the graph state for audit purposes.

- **Channel Manager node** (Priority: High)
  - Must publish the finalized bundle to MercadoLibre via their Items API.
  - Must record the MercadoLibre listing ID (`ml_id`) and tower hash in the `published_towers` registry.
  - Must handle API errors gracefully (retry with exponential backoff, log failures).

- **Uniqueness engine** (Priority: High)
  - Must generate a SHA-256 hash from the sorted list of core tower component SKUs.
  - Must validate the hash against the `published_towers` table before proceeding to publication.
  - Must reject and trigger re-selection if a duplicate is detected.

- **Hybrid Sentinel** (Priority: High)
  - Must run every 2 hours as a background polling loop.
  - **Hard Pause (Tower Sentinel)**: If any core tower component (CPU, MB, RAM, SSD, PSU, Case) reaches 0 stock, the associated MercadoLibre listing must be immediately paused.
  - **Dynamic Replacement (Bundle Sentinel)**: If a peripheral reaches 0 stock, the system must find a suitable replacement, update the listing price/description, and sync to MercadoLibre without pausing.
  - Must log all actions (pauses, replacements, failures) to structured logs.

- **Local Registry database** (Priority: High)
  - Must implement three tables: `published_towers`, `published_bundles`, `component_audit`.
  - Must use SQLAlchemy async with the repository pattern.
  - Must support PostgreSQL (production on Railway) and SQLite (local development).

- **AIEcommerce API client** (Priority: High)
  - Must fetch product catalog, stock levels, and pricing from the *aiecommerce* Django API.
  - Must use `httpx.AsyncClient` with configurable base URL and API key authentication.
  - Must map API responses to Pydantic schemas.

- **MercadoLibre API client** (Priority: High)
  - Must support OAuth2 authentication flow (token acquisition and refresh).
  - Must support creating, updating, and pausing item listings.
  - Must be isolated in its own service module with Pydantic request/response models.

## 5. User experience

### 5.1 Entry points and first-time user flow

- Developer clones the repo and runs `uv sync` to install all dependencies.
- Configuration is done via `.env` file (copy `.env.example`).
- `uv run uvicorn orchestrator.main:app --reload` starts the local server.
- Health check at `GET /health` confirms the system is operational.
- Database tables are auto-created on first startup via SQLAlchemy `create_all`.

### 5.2 Core experience

- **Pipeline trigger**: Operator hits `POST /api/pipeline/run` (or the scheduler fires automatically). The LangGraph pipeline executes end-to-end, producing up to 3 new MercadoLibre listings.
- **Monitoring**: Operator checks `GET /api/listings` to see all active listings with their status, category, and last sync time.
- **Sentinel**: Runs automatically every 2 hours. Operator can check `GET /api/sentinel/status` for last run time and actions taken.

### 5.3 Advanced features and edge cases

- If the inventory contains fewer than 6 unique core components available for a category, the pipeline must skip that category and log a warning rather than failing the entire run.
- If MercadoLibre API is temporarily unavailable, the Channel Manager must retry up to 3 times with exponential backoff, then mark the bundle as `pending_publication` for the next cycle.
- If the Sentinel detects stock changes for a listing already in `pending_publication` state, it must not attempt to update MercadoLibre — only update the local registry.
- If all possible tower combinations have been published (hash collision on every attempt), the pipeline must log an alert and skip that category.

### 5.4 UI/UX highlights

- This is a headless API system; there is no user interface.
- All operator interaction happens through REST API endpoints and structured JSON logs.
- Railway deployment dashboard provides log streaming and environment variable management.

## 6. Narrative

Juan runs a PC hardware business. Every morning, his *aiecommerce* platform reflects the latest stock arrivals — new CPUs, motherboards, RAM kits. Previously, Juan would spend hours manually assembling these into bundles, photographing them, writing descriptions, calculating prices with margins and fees, and publishing to MercadoLibre. If something went out of stock, he'd scramble to pause listings before customers ordered ghost inventory.

Now, the Agent Orchestrator handles it all. Three times a day, the pipeline wakes up, examines the available inventory, and assembles unique PC bundles for Home, Business, and Gaming segments. It generates professional images, calculates profitable prices, and publishes directly to MercadoLibre. Every 2 hours, the Sentinel checks stock levels — if a CPU runs out, the listing pauses instantly; if a keyboard goes out of stock, it swaps in a similar one and updates the listing seamlessly. Juan monitors everything from a few API calls and focuses on growing his business instead of managing catalogs.

## 7. Success metrics

### 7.1 User-centric metrics

- Zero ghost-sell incidents per month (listings paused before any out-of-stock order is placed).
- Operator spends less than 15 minutes per day on catalog management tasks.
- 100% of published listings have complete media (4 images + 1 video).

### 7.2 Business metrics

- Up to 50 active, unique MercadoLibre listings maintained simultaneously.
- Hardware rotation: every SKU is bundled at least once within 30 days of availability.
- Revenue per listing meets or exceeds the calculated margin target.

### 7.3 Technical metrics

- Publication pipeline completes end-to-end in under 5 minutes per category.
- Sentinel cycle completes in under 2 minutes for 50 active listings.
- API response times under 500ms for all operator endpoints (p95).
- Test coverage at or above 80% line coverage.
- Zero `mypy` errors, zero `ruff` lint errors on every commit.

## 8. Technical considerations

### 8.1 Integration points

- **aiecommerce API** (Django): Product catalog, stock levels, pricing. Authenticated via API key. Already stubbed in `src/orchestrator/services/aiecommerce.py`.
- **MercadoLibre API**: OAuth2-authenticated REST API for item CRUD, category lookup, and listing management. New service module required.
- **Media generation service**: TBD provider for image and video generation. Must be wrapped behind an abstract `MediaGenerator` protocol so the implementation can be swapped (e.g., DALL-E, Bannerbear, custom renderer).
- **OpenAI API**: Used by LangGraph/LangChain for LLM-powered agent reasoning. Already configured in settings.
- **PostgreSQL** (Railway): Production database for the Local Registry. SQLite for local development.

### 8.2 Data storage and privacy

- The Local Registry stores only internal operational data (SKUs, hashes, MercadoLibre IDs, timestamps). No customer PII is stored.
- OAuth2 tokens for MercadoLibre must be stored securely (encrypted at rest or fetched on demand).
- API keys and secrets are loaded from environment variables via `pydantic-settings`, never committed to source control.
- Database connection strings are environment-specific (Railway injects `DATABASE_URL` automatically).

### 8.3 Scalability and performance

- The system manages approximately 500 SKUs and up to 50 active listings — a modest scale that does not require horizontal scaling.
- Railway's single-container deployment is sufficient for the expected load.
- SQLAlchemy async ensures non-blocking database I/O.
- `httpx.AsyncClient` enables concurrent outbound HTTP calls during Sentinel cycles.
- The LangGraph pipeline is inherently sequential per category but categories can be processed in parallel if needed.

### 8.4 Potential challenges

- **MercadoLibre API reliability**: Network failures or temporary outages require robust retry logic and circuit-breaker patterns.
- **Media generation latency**: Image/video generation may be slow (30–60 seconds per asset). The pipeline must tolerate this without timing out.
- **Component compatibility logic**: Ensuring CPU-motherboard socket compatibility, RAM generation matching, and PSU wattage adequacy requires a well-defined rules engine or LLM-assisted reasoning.
- **Hash space exhaustion**: With a finite inventory (~500 SKUs), the number of unique tower combinations is bounded. The system must detect when no new unique combinations are possible.
- **Railway cold starts**: The Sentinel polling loop must be resilient to container restarts. Consider persisting the last-run timestamp in the database.

## 9. Milestones and sequencing

### 9.1 Project estimate

- Medium-large: 8–10 weeks for a single developer.

### 9.2 Team size and composition

- 1 backend/AI engineer (full-stack Python, LangGraph, FastAPI).
- Optional: 1 part-time frontend/DevOps for Railway deployment and monitoring dashboard.

### 9.3 Suggested phases

- **Phase 1 — Foundation** (Completed)
  - Repository scaffolding with `uv`.
  - Ruff, Mypy, pre-commit hooks configuration.
  - FastAPI skeleton with health endpoint.
  - Project structure (`src/orchestrator/` layout).
  - Basic `Settings`, logging, and CORS setup.

- **Phase 2 — Registry and state** (1–2 weeks)
  - SQLAlchemy async models for `published_towers`, `published_bundles`, `component_audit`.
  - Alembic migration setup (or `create_all` for initial development).
  - Repository pattern for data access.
  - Extended `GraphState` Pydantic model with tower, bundle, pricing, and media fields.
  - SHA-256 hashing utility for tower uniqueness.

- **Phase 3 — Service integration** (1–2 weeks)
  - Full *aiecommerce* client: product listing, stock queries, category filtering.
  - Pydantic schemas for all *aiecommerce* API responses.
  - MercadoLibre API client: OAuth2 flow, item CRUD, listing pause/resume.
  - Pydantic schemas for MercadoLibre request/response payloads.
  - Unit tests with mocked HTTP responses for both clients.

- **Phase 4 — Agent logic** (2–3 weeks)
  - Inventory Architect node: LRU selection, dependency resolution, hash validation.
  - Bundle Creator node: category-specific peripheral attachment.
  - Financial Strategist node: tiered margin pricing calculator.
  - LangGraph wiring: nodes connected in a directed graph with conditional edges.
  - Integration tests for the full pipeline with mocked services.

- **Phase 5 — Media and publishing** (1–2 weeks)
  - Media generator protocol/ABC definition.
  - Placeholder or initial media generation implementation.
  - Creative Director node integration into the graph.
  - Channel Manager node: MercadoLibre publication, registry recording.
  - End-to-end pipeline test with mocked external APIs.

- **Phase 6 — The Sentinel** (1–2 weeks)
  - Tower Sentinel: stock polling, hard-pause logic.
  - Bundle Sentinel: peripheral replacement, dynamic update logic.
  - 2-hour scheduling loop (in-process async or Railway cron).
  - API endpoints for Sentinel status and manual trigger.
  - Railway deployment configuration and production environment setup.

## 10. User stories

### 10.1 Run the publication pipeline

- **ID**: GH-001
- **Description**: As an operator, I want to trigger the publication pipeline via an API call so that new PC bundles are assembled and published to MercadoLibre without manual intervention.
- **Acceptance criteria**:
  - A `POST /api/pipeline/run` endpoint exists and requires authentication.
  - The endpoint triggers the full LangGraph pipeline (Architect → Creator → Creative Director → Financial Strategist → Channel Manager).
  - The pipeline produces up to 3 bundles (one per category: Home, Business, Gaming) per run.
  - The response includes a summary of bundles created, skipped, or failed.
  - If the pipeline is already running, the endpoint returns HTTP 409 Conflict.

### 10.2 Select core tower components with LRU priority

- **ID**: GH-002
- **Description**: As the system, I want the Inventory Architect to select 6 core components (CPU, MB, RAM, SSD, PSU, Case) prioritizing those with the oldest `last_bundled_date` so that all hardware rotates through listings evenly.
- **Acceptance criteria**:
  - Components are sorted by `last_bundled_date` ascending (oldest first).
  - Only components with `stock_level >= 1` are eligible for selection.
  - The selection satisfies hardware compatibility rules (CPU socket matches motherboard, RAM generation matches motherboard, PSU wattage is adequate).
  - If the case includes an integrated PSU, a standalone PSU is not selected.
  - The selected tower's SHA-256 hash is unique (not present in `published_towers`).

### 10.3 Validate tower uniqueness

- **ID**: GH-003
- **Description**: As the system, I want to validate that every assembled tower configuration is unique so that MercadoLibre does not penalize the account for duplicate listings.
- **Acceptance criteria**:
  - A SHA-256 hash is generated from the sorted list of core tower component SKUs.
  - The hash is checked against the `published_towers` table before publication.
  - If the hash already exists, the Inventory Architect re-selects components and generates a new configuration.
  - After 10 failed uniqueness attempts for a category, the pipeline skips that category and logs a warning.

### 10.4 Append category-specific peripherals

- **ID**: GH-004
- **Description**: As the system, I want the Bundle Creator to attach peripherals (monitors, keyboards, mice, headsets) based on the bundle category so that each listing is a complete, market-ready PC package.
- **Acceptance criteria**:
  - Peripheral rules are defined per category (e.g., Gaming requires a gaming monitor + mechanical keyboard; Home requires a basic monitor + standard keyboard).
  - Only peripherals with `stock_level >= 1` are selected.
  - The peripheral SKUs are stored as a JSON array in the `published_bundles` table.
  - If a required peripheral type has no available stock, the bundle is still published with available peripherals and a log warning is emitted.

### 10.5 Generate listing media

- **ID**: GH-005
- **Description**: As the system, I want the Creative Director to generate 4 product images and 1 technical spec video per listing so that every MercadoLibre publication has professional visual content.
- **Acceptance criteria**:
  - The media generation service is called with the bundle's component list and category.
  - 4 unique images are generated, each meeting MercadoLibre's minimum resolution (1200x1200 px) and aspect ratio requirements.
  - 1 technical specification video is generated summarizing the bundle's specs.
  - Media URLs are attached to the graph state for the Channel Manager to use.
  - The media generator is behind an abstract `MediaGenerator` protocol, allowing the provider to be swapped without changing node logic.

### 10.6 Calculate listing price with tiered margins

- **ID**: GH-006
- **Description**: As the system, I want the Financial Strategist to calculate the final listing price using a tiered margin formula so that each bundle is profitably priced after all fees and taxes.
- **Acceptance criteria**:
  - The formula is: `final_price = (component_costs + assembly_fee + shipping_cost) / (1 - marketplace_fees - tax_rate)`.
  - `component_costs` is the sum of all component and peripheral costs from *aiecommerce*.
  - `assembly_fee`, `shipping_cost`, `marketplace_fees`, and `tax_rate` are configurable via environment variables or settings.
  - A full cost breakdown (per-component costs, fees, margin) is attached to the graph state.
  - The final price is a positive number rounded to 2 decimal places.

### 10.7 Publish bundle to MercadoLibre

- **ID**: GH-007
- **Description**: As the system, I want the Channel Manager to publish the finalized bundle to MercadoLibre and record the mapping in the Local Registry so that the listing is live and trackable.
- **Acceptance criteria**:
  - The MercadoLibre Items API is called with the bundle title, description, price, category, and media URLs.
  - On success, the MercadoLibre listing ID (`ml_id`) is stored in `published_towers` alongside the tower hash and category.
  - On API failure, the system retries up to 3 times with exponential backoff.
  - After 3 failures, the bundle is marked as `pending_publication` in the registry.
  - The `component_audit` table is updated with the current timestamp for all bundled SKUs' `last_bundled_date`.

### 10.8 Pause listing on core component stock-out

- **ID**: GH-008
- **Description**: As the system, I want the Tower Sentinel to immediately pause a MercadoLibre listing when any core tower component reaches 0 stock so that customers cannot purchase unavailable bundles.
- **Acceptance criteria**:
  - The Sentinel polls *aiecommerce* API for current stock levels of all components in active listings.
  - If any core component (CPU, MB, RAM, SSD, PSU, Case) has `stock_level == 0`, the associated MercadoLibre listing is paused via the API.
  - The listing status in `published_towers` is updated to `paused`.
  - The pause action is logged with the listing ID, component SKU, and timestamp.
  - The Sentinel cycle completes in under 2 minutes for 50 active listings.

### 10.9 Dynamically replace out-of-stock peripherals

- **ID**: GH-009
- **Description**: As the system, I want the Bundle Sentinel to replace out-of-stock peripherals with similar available items and update the live listing so that bundles remain purchasable without pausing.
- **Acceptance criteria**:
  - If a peripheral in an active bundle has `stock_level == 0`, the system selects a replacement peripheral of the same type with `stock_level >= 1`.
  - The replacement is recorded in `published_bundles` (updated peripheral SKUs JSON).
  - The listing price is recalculated using the Financial Strategist formula.
  - The MercadoLibre listing is updated with the new peripheral, price, and description.
  - If no replacement is available for a peripheral type, the listing remains active with the remaining peripherals and a log warning is emitted.

### 10.10 Schedule automated pipeline and sentinel runs

- **ID**: GH-010
- **Description**: As an operator, I want the publication pipeline to run automatically 2–3 times daily and the Sentinel to run every 2 hours so that the system operates autonomously without manual triggers.
- **Acceptance criteria**:
  - The publication pipeline is scheduled to run at configurable times (default: 3 times daily).
  - The Sentinel loop runs every 2 hours, starting from application boot.
  - Both schedules are configurable via environment variables.
  - If a scheduled run overlaps with an in-progress run, it is skipped and logged.
  - The scheduling mechanism is resilient to Railway container restarts (last-run timestamp persisted in database).

### 10.11 View active listings and system status

- **ID**: GH-011
- **Description**: As an operator, I want to query active listings and Sentinel status via API endpoints so that I can monitor the system's health and output.
- **Acceptance criteria**:
  - `GET /api/listings` returns all entries from `published_towers` with their status, category, `ml_id`, and creation date.
  - `GET /api/listings` supports filtering by `status` (active, paused, pending_publication) and `category`.
  - `GET /api/sentinel/status` returns the last Sentinel run timestamp, number of pauses performed, and number of replacements made.
  - All endpoints require authentication and return JSON responses.
  - Response times are under 500ms (p95).

### 10.12 Persist and query the Local Registry

- **ID**: GH-012
- **Description**: As a developer, I want three database tables (`published_towers`, `published_bundles`, `component_audit`) with repository-pattern access so that all pipeline and Sentinel state is persisted and queryable.
- **Acceptance criteria**:
  - `published_towers` has columns: `bundle_hash` (PK, VARCHAR), `ml_id` (VARCHAR), `category` (VARCHAR), `status` (VARCHAR), `created_at` (TIMESTAMP), `updated_at` (TIMESTAMP).
  - `published_bundles` has columns: `bundle_id` (PK, UUID), `tower_id` (FK to `published_towers.bundle_hash`), `peripheral_skus` (JSON), `total_price` (DECIMAL), `created_at` (TIMESTAMP).
  - `component_audit` has columns: `sku` (PK, VARCHAR), `last_bundled_date` (TIMESTAMP, nullable), `stock_level` (INTEGER), `updated_at` (TIMESTAMP).
  - Each table has a corresponding repository class with async CRUD methods.
  - Repositories are injected via FastAPI `Depends()`.

### 10.13 Authenticate API requests

- **ID**: GH-013
- **Description**: As an operator, I want all API endpoints (except health check) to require authentication so that unauthorized users cannot trigger pipelines or view listing data.
- **Acceptance criteria**:
  - An API key-based or OAuth2 Bearer token authentication mechanism is implemented.
  - The health check endpoint (`GET /health`) remains unauthenticated.
  - All other endpoints return HTTP 401 Unauthorized if no valid credential is provided.
  - The authentication mechanism is implemented as a FastAPI dependency (`Depends()`).
  - API keys or OAuth2 configuration are loaded from environment variables.

### 10.14 Handle pipeline errors gracefully

- **ID**: GH-014
- **Description**: As a developer, I want the pipeline to handle errors at each node gracefully so that a failure in one category does not prevent other categories from being processed.
- **Acceptance criteria**:
  - Each node catches exceptions and attaches error details to the graph state rather than raising unhandled exceptions.
  - If a node fails for one category, the pipeline continues processing remaining categories.
  - All errors are logged with structured JSON including the node name, category, error message, and stack trace.
  - The pipeline run summary endpoint reports per-category success/failure status.
  - Custom exception classes are defined in `src/orchestrator/exceptions.py`.

### 10.15 MercadoLibre OAuth2 token management

- **ID**: GH-015
- **Description**: As the system, I want to manage MercadoLibre OAuth2 tokens (acquisition, refresh, and storage) so that API calls are always authenticated with a valid token.
- **Acceptance criteria**:
  - An OAuth2 callback endpoint (`GET /auth/callback`) exchanges the authorization code for access and refresh tokens.
  - Tokens are stored securely (database or encrypted environment variable).
  - The MercadoLibre client automatically refreshes the access token when it expires (before making API calls).
  - If token refresh fails, the system logs an alert and marks affected operations as failed.
  - The `MERCADOLIBRE_CLIENT_ID`, `MERCADOLIBRE_CLIENT_SECRET`, and `MERCADOLIBRE_REDIRECT_URI` settings are already defined in the config.
