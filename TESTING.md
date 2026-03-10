# Step-by-Step Workflow Testing Guide

This guide lets you test **each stage of the assembly pipeline individually**, with visible results at every step. Each script is standalone — you can run them in order (chained via JSON output files) or re-run a single step without repeating earlier ones.

## Overview

| Step | Script | What It Tests | External APIs |
|------|--------|---------------|---------------|
| 0 | `test_step0_healthcheck.py` | Environment, DB, API connectivity | AIEcommerce |
| 1 | `test_step1_product_api.py` | Product inventory fetching | AIEcommerce |
| 2 | `test_step2_tower_assembly.py` | Component selection, compatibility, uniqueness | AIEcommerce (optional) |
| 3 | `test_step3_bundle_creation.py` | Peripheral selection, bundle hashing | AIEcommerce |
| 4 | `test_step4_creative_assets.py` | Image/video generation, compliance | Gemini (skippable with `--dry-run`) |
| 5 | `test_step5_ml_publish.py` | Pricing, listing content, ML publishing | MercadoLibre (skippable with `--dry-run`) |
| 6 | `test_step6_full_pipeline.py` | End-to-end LangGraph workflow | All of the above |

---

## Prerequisites

### 1. Start the Database

```bash
docker compose up -d db
```

Wait a few seconds for PostgreSQL to initialise. The test scripts will auto-create tables on first run.

### 2. Install Dependencies

```bash
uv sync
```

### 3. Configure Environment

Copy and edit your `.env` file with real API credentials:

```bash
cp .env.example .env
# Edit .env with your editor
```

**Required for all steps:**
- `DATABASE_URL` — PostgreSQL connection string
- `AIECOMMERCE_API_URL` — External product API base URL
- `AIECOMMERCE_API_KEY` — External product API key

**Required for Step 4 (without `--dry-run`):**
- `GOOGLE_API_KEY` — Gemini API key for image/video generation

**Required for Step 5 (without `--dry-run`):**
- `MERCADOLIBRE_ACCESS_TOKEN` — ML OAuth2 access token
- `MERCADOLIBRE_REFRESH_TOKEN` — ML OAuth2 refresh token
- `MERCADOLIBRE_CLIENT_ID` — ML OAuth2 client ID
- `MERCADOLIBRE_CLIENT_SECRET` — ML OAuth2 client secret

---

## Step 0 — Environment Health Check

Validates that all prerequisites are ready before you start testing.

```bash
uv run python scripts/test_step0_healthcheck.py
```

**What it checks:**
1. Environment variables are loaded (critical API keys present).
2. PostgreSQL is reachable and tables can be created.
3. AIEcommerce API responds to a test call.

**Expected output:**
```
============================================================
  Step 0 — Environment Health Check
============================================================

--- 1. Environment Variables ---

  ✔ DATABASE_URL = postgresql+asyncpg://orchestrator:orchestrator@localhost:5432/orchestrator
  ✔ AIECOMMERCE_API_URL = https://your-api-url.com
  ✔ AIECOMMERCE_API_KEY = ***

--- 2. Database Connection ---

  ✔ Database connection successful (SELECT 1 = OK)
  ✔ Database tables created / verified

--- 3. AIEcommerce API Connection ---

  ✔ API responded — 42 total CPUs, 20 in page

--- Results ---

  ✔ ENV: PASS
  ✔ DATABASE: PASS
  ✔ API: PASS

  ✔ All checks passed! You are ready to run the workflow steps.
```

**Troubleshooting:**
- `DATABASE: FAIL` → Run `docker compose up -d db` and wait a few seconds.
- `API: FAIL` → Check `AIECOMMERCE_API_URL` and `AIECOMMERCE_API_KEY` in `.env`.

---

## Step 1 — Product API Communication

Fetches the full inventory from the AIEcommerce API and displays product details.

```bash
uv run python scripts/test_step1_product_api.py
```

**Options:**
```bash
# Also fetch peripheral categories (keyboard, mouse, monitor, speakers)
uv run python scripts/test_step1_product_api.py --include-peripherals
```

**What it does:**
1. Fetches inventory for all 8 core component categories (CPU, Motherboard, RAM, GPU, SSD, PSU, Case, Fan).
2. Retrieves detailed specs for 1 sample product per category.
3. Displays an inventory summary table and spec preview.
4. Saves full data to `scripts/output/step1_inventory.json`.

**Expected output:**
```
============================================================
  Step 1 — Product API Communication
============================================================

  ✔ CPU: 15 products fetched
  ✔ MOTHERBOARD: 8 products fetched
  ✔ RAM: 12 products fetched
  ...

--- Inventory Summary ---

    Category      In Page  Total  Status
    ----------    -------  -----  ------
    CPU           15       15     OK
    MOTHERBOARD   8        8      OK
    RAM           12       12     OK
    ...

--- Sample Product Details (1 per category) ---

    Category      SKU         Name                          Price     Stock  Spec Keys
    ----------    ----------  ----------------------------  --------  -----  -------------------
    CPU           CPU-001     Intel Core i7-13700K          $349.99   25     socket, cores, tdp
    MOTHERBOARD   MB-001      ASUS ROG Strix Z790-E         $289.99   10     socket, memory_type
    ...

  ✔ Output saved → scripts/output/step1_inventory.json
```

---

## Step 2 — Tower Assembly (Inventory Architect)

Selects components for each tier, validates compatibility, and persists towers.

```bash
uv run python scripts/test_step2_tower_assembly.py
```

**Options:**
```bash
# Test only specific tiers
uv run python scripts/test_step2_tower_assembly.py --tiers Home Gaming

# Fetch fresh inventory from API instead of using Step 1 output
uv run python scripts/test_step2_tower_assembly.py --fresh
```

**What it does:**
1. Loads inventory from Step 1 output (or fetches fresh with `--fresh`).
2. For each tier: selects components using tier strategy.
3. Validates CPU↔Motherboard socket, RAM↔Motherboard, SSD↔Motherboard, PSU wattage, case form factor.
4. Ensures the build hash is unique (swaps SSD → RAM → PSU if collision).
5. Persists the tower to `published_towers` table.
6. Saves builds to `scripts/output/step2_towers.json`.

**Expected output:**
```
--- Tier: Home ---

    Role         SKU         Name                          Price
    ----------   ---------   ----------------------------  --------
    CPU          CPU-003     Intel Core i3-12100           $129.99
    MOTHERBOARD  MB-005      Gigabyte B660M DS3H           $109.99
    RAM          RAM-008     Kingston 16GB DDR4             $49.99
    SSD          SSD-002     WD Blue 500GB                  $39.99
    PSU          PSU-004     EVGA 500W                      $44.99
    CASE         CASE-001    DeepCool Matrexx 40            $39.99

  ✔ Component selection complete for Home
  ✔ Compatibility validation passed
  ✔ Uniqueness check passed — hash: a3f8c21b9e4d7f01...
  ✔ Tower persisted to database
    Bundle Hash: a3f8c21b9e4d7f01...
    Total Price: $414.94
    Components: 6
```

**Troubleshooting:**
- `Compatibility: CPU socket mismatch` → The inventory may have incompatible components. This is expected — the system validates real constraints.
- `No SSD components available` → The API may not have stock for that category.

---

## Step 3 — Bundle Creation (Bundle Creator)

Adds tier-appropriate peripherals to each tower build.

```bash
uv run python scripts/test_step3_bundle_creation.py
```

**Options:**
```bash
uv run python scripts/test_step3_bundle_creation.py --tiers Home Business
```

**What it does:**
1. Loads tower builds from Step 2 output.
2. Fetches peripheral inventory (keyboard, mouse, monitor, speakers) from the API.
3. Selects peripherals per tier: Home=cheapest, Business=balanced, Gaming=premium+speakers.
4. Computes `bundle_id` hash (SHA-256 of tower_hash + sorted peripheral SKUs).
5. Persists bundles to `published_bundles` table.
6. Saves output to `scripts/output/step3_bundles.json`.

**Expected output:**
```
--- Tier: Home (Tower: a3f8c21b...) ---

  ✔ Selected 3 peripheral(s)

    Role       SKU         Name                          Price
    ---------  ---------   ----------------------------  --------
    KEYBOARD   KB-002      Logitech K120                  $12.99
    MOUSE      MS-001      Logitech M100                   $8.99
    MONITOR    MON-003     LG 22MK430H 22"               $129.99

  ✔ Bundle ID: b7e2d94a...
    Total Peripheral Price: $151.97
  ✔ Bundle persisted to database
```

---

## Step 4 — Creative Asset Generation (Creative Director)

Generates product images and videos for each build using Google Gemini.

```bash
# Dry run — shows prompts without calling Gemini API (recommended first!)
uv run python scripts/test_step4_creative_assets.py --dry-run

# Real run — calls Gemini API (requires GOOGLE_API_KEY)
uv run python scripts/test_step4_creative_assets.py
```

**Options:**
```bash
uv run python scripts/test_step4_creative_assets.py --dry-run --tiers Home
```

**What it does:**
1. Loads builds and bundles from Step 3 output.
2. Constructs image prompts (4 styles: front_view, three_quarter, detail_closeup, lifestyle_context).
3. Constructs a video prompt with deterministic style/angle variation.
4. In `--dry-run`: displays all prompts, saves placeholder assets.
5. In real mode: calls Gemini Imagen (4 images) + Veo (1 video), validates MercadoLibre compliance, persists to `creative_assets` table.
6. Saves output to `scripts/output/step4_assets.json`.

**Expected output (dry-run):**
```
--- Image Prompts (4 styles) ---

    Style               Prompt Preview
    ------------------  ---------------------------------------------------------------
    front_view          Professional product photography of a PC tower in DeepCool...
    three_quarter       Three-quarter angle product shot of a PC tower in DeepCool...
    detail_closeup      Close-up detail shot highlighting premium build quality of...
    lifestyle_context   Lifestyle product photo showing a PC tower in DeepCool Mat...

--- Video Prompt ---

    Style: tech_showcase
    Camera Angle: orbit
    Prompt: Professional tech showcase video of an assembled PC tower...

  ✔ DRY RUN — Skipping Gemini API call
```

> **Cost note:** Each real run generates 4 images + 1 video per build. Use `--dry-run` first to verify prompts look correct.

---

## Step 5 — MercadoLibre Publishing (Channel Manager)

Calculates final pricing, generates listing content, and publishes to MercadoLibre.

```bash
# Dry run — computes pricing + listing content without calling ML API
uv run python scripts/test_step5_ml_publish.py --dry-run

# Real run — requires ML OAuth tokens
uv run python scripts/test_step5_ml_publish.py
```

**Options:**
```bash
uv run python scripts/test_step5_ml_publish.py --dry-run --tiers Gaming
```

**What it does:**
1. Loads all prior data (builds, bundles, assets) from Step 4 output.
2. Calculates final price: `(component cost) × (1 + margin%) × (1 + ML fee%)`.
3. Generates listing title (≤60 chars) and multi-line description.
4. In `--dry-run`: displays pricing breakdown and listing content preview.
5. In real mode: uploads images/video to ML, creates the listing, stores ML ID.
6. Saves output to `scripts/output/step5_listings.json`.

**Expected output (dry-run):**
```
--- Tier: Home (Tower: a3f8c21b...) ---

    Component Cost: $566.91
    Assembly Margin: 15.0%
    ML Fee: 12.0%
    Final Price: $730.23

--- Listing Content ---

    Title: PC Home Intel Core i3-12100 16GB DDR4
    Title Length: 42 chars (max 60)
    Description preview:
    Computadora ensamblada con los siguientes componentes:
    - CPU: Intel Core i3-12100
    - Motherboard: Gigabyte B660M DS3H
    ...

  ✔ DRY RUN — Skipping ML API calls
```

---

## Step 6 — Full Pipeline (End-to-End)

Runs the complete LangGraph workflow as the trigger endpoint does — all 4 agents in sequence.

```bash
uv run python scripts/test_step6_full_pipeline.py
```

**Options:**
```bash
uv run python scripts/test_step6_full_pipeline.py --tiers Home
```

**What it does:**
1. Calls `build_assembly_graph()` from the workflow module.
2. Invokes the full graph with `{"requested_tiers": [...]}`.
3. Displays a summary of each stage's results from the final graph state.
4. Saves the complete output to `scripts/output/step6_full_pipeline.json`.

This is equivalent to calling `POST /api/v1/runs/trigger/` but with full terminal output.

---

## How Steps Connect

Each step saves its output as a JSON file in `scripts/output/`. The next step loads it:

```
Step 1 → step1_inventory.json → Step 2 (loads inventory)
Step 2 → step2_towers.json   → Step 3 (loads tower builds)
Step 3 → step3_bundles.json  → Step 4 (loads builds + bundles)
Step 4 → step4_assets.json   → Step 5 (loads builds + bundles + assets)
```

**Re-running a single step:** If Step 3 fails, you can fix the issue and re-run just Step 3. It will load the existing Step 2 output. You only need to re-run subsequent steps (4, 5) if the output data changed.

**Running independently:** Step 6 (full pipeline) runs everything end-to-end via LangGraph and does not read prior step output files.

---

## Output Files

All output is saved under `scripts/output/` (git-ignored):

| File | Contents |
|------|----------|
| `step1_inventory.json` | Full inventory + specs per category |
| `step2_towers.json` | Completed tower builds with component details |
| `step3_bundles.json` | Bundle builds + tower builds |
| `step4_assets.json` | Creative assets + builds + bundles |
| `step5_listings.json` | Published listings with ML IDs |
| `step6_full_pipeline.json` | Complete pipeline result |

---

## Recommended Testing Flow

### First-time setup
```bash
docker compose up -d db     # Start PostgreSQL
uv sync                      # Install dependencies
cp .env.example .env         # Configure environment
# Edit .env with real API keys
```

### Verify everything works
```bash
uv run python scripts/test_step0_healthcheck.py
```

### Test each step individually
```bash
# 1. Check API connectivity and fetch inventory
uv run python scripts/test_step1_product_api.py

# 2. Assemble towers (uses Step 1 output)
uv run python scripts/test_step2_tower_assembly.py

# 3. Create bundles with peripherals (uses Step 2 output)
uv run python scripts/test_step3_bundle_creation.py

# 4. Preview creative prompts without API costs
uv run python scripts/test_step4_creative_assets.py --dry-run

# 5. Preview pricing and listing content without ML API
uv run python scripts/test_step5_ml_publish.py --dry-run
```

### Test with a single tier first
```bash
uv run python scripts/test_step2_tower_assembly.py --tiers Home
uv run python scripts/test_step3_bundle_creation.py --tiers Home
uv run python scripts/test_step4_creative_assets.py --dry-run --tiers Home
uv run python scripts/test_step5_ml_publish.py --dry-run --tiers Home
```

### Run the full pipeline
```bash
# Only when all individual steps work correctly
uv run python scripts/test_step6_full_pipeline.py --tiers Home
```

---

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `Database connection failed` | PostgreSQL not running | `docker compose up -d db` |
| `API connection failed` | Wrong URL or key | Check `.env` values |
| `No CPU components available` | API returned empty results | Verify the API has active products with stock |
| `CPU socket mismatch` | Incompatible CPU + Motherboard in inventory | Expected — the system properly validates compatibility |
| `Could not generate unique build` | All possible hash combinations already exist | Clear the `published_towers` table or add new inventory |
| `Required input file not found` | Previous step was not run | Run the preceding step first |
| `GOOGLE_API_KEY not set` | Gemini credentials missing | Add to `.env` or use `--dry-run` for Step 4 |
| `MercadoLibre token expired` | OAuth tokens need refresh | Update tokens in `.env` or use `--dry-run` for Step 5 |
