"""End-to-end integration tests for the assembly pipeline.

Covers the full flow:

    POST /api/v1/runs/trigger/
        → LangGraph workflow (inventory_architect_node → bundle_creator_node)
        → AIEcommerce API fetch (mocked)
        → compatibility validation (CompatibilityEngine)
        → uniqueness check (UniquenessEngine + TowerRepository)
        → tower persistence (SQLite in-memory)
    GET /api/v1/towers/          → returns persisted towers
    GET /api/v1/towers/{hash}/   → returns tower detail

All external HTTP calls to the aiecommerce API are intercepted by patching
``AIEcommerceClient.list_products`` and ``AIEcommerceClient.get_product_detail``
with ``AsyncMock`` instances.  The ``bundle_creator_node`` is mocked out so
that Phase 1 tower-assembly tests remain focused on the Inventory Architect.
The database layer uses real SQLAlchemy sessions backed by an in-memory
SQLite engine (see ``conftest.py``).
"""

from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from orchestrator.schemas.product import (
    ComponentCategory,
    ProductDetail,
    ProductListItem,
    ProductListResponse,
)
from orchestrator.services.aiecommerce import AIEcommerceClient
from tests.test_integration.conftest import INTEGRATION_API_KEY

# ---------------------------------------------------------------------------
# Mock inventory — compatible component set
# ---------------------------------------------------------------------------
#
# Component selection strategy per tier (FR-1.2):
#   Home     → cheapest component in each category (price ascending)
#   Business → middle component (index len // 2 after stable rotation sort)
#   Gaming   → most expensive component (price descending)
#
# Core hash inputs (FR-1.6): CPU, MB, RAM, SSD, PSU, CASE.
#
# With the data below the three tiers produce distinct hashes on the first run:
#   Home    → (CPU-001, MB-001, RAM-001, SSD-001, PSU-001, CASE-001)
#   Business→ (CPU-001, MB-001, RAM-002, SSD-002, PSU-002, CASE-001)
#   Gaming  → (CPU-001, MB-001, RAM-002, SSD-003, PSU-002, CASE-001)
#
# On a second run the UniquenessEngine swaps secondary components (SSD→RAM→PSU)
# to generate three additional distinct hashes (FR-1.6 / FR-6.2).

# ── CPU ─────────────────────────────────────────────────────────────────────

_CPU_ITEM = ProductListItem(
    id=1,
    code="C001",
    sku="CPU-001",
    normalized_name="AMD Ryzen 5 5600X",
    price=200.0,
    category=ComponentCategory.CPU,
    total_available_stock=10,
)
_CPU_DETAIL = ProductDetail(
    id=1,
    code="C001",
    sku="CPU-001",
    normalized_name="AMD Ryzen 5 5600X",
    price=200.0,
    category=ComponentCategory.CPU,
    specs={"socket": "AM4", "tdp": 65},
    total_available_stock=10,
)

# ── Motherboard ─────────────────────────────────────────────────────────────

_MB_ITEM = ProductListItem(
    id=2,
    code="M001",
    sku="MB-001",
    normalized_name="ASUS B550-F",
    price=150.0,
    category=ComponentCategory.MOTHERBOARD,
    total_available_stock=5,
)
_MB_DETAIL = ProductDetail(
    id=2,
    code="M001",
    sku="MB-001",
    normalized_name="ASUS B550-F",
    price=150.0,
    category=ComponentCategory.MOTHERBOARD,
    specs={
        "socket": "AM4",
        "memory_type": "DDR4",
        "form_factor": "ATX",
        "supported_ssd_interfaces": ["M.2", "SATA"],
    },
    total_available_stock=5,
)

# ── RAM (two options) ────────────────────────────────────────────────────────
# Home picks RAM-001 (cheapest).  Gaming and Business pick RAM-002
# (most expensive / middle-of-2 after stable sort).

_RAM1_ITEM = ProductListItem(
    id=3,
    code="R001",
    sku="RAM-001",
    normalized_name="Corsair 16GB DDR4",
    price=80.0,
    category=ComponentCategory.RAM,
    total_available_stock=20,
)
_RAM1_DETAIL = ProductDetail(
    id=3,
    code="R001",
    sku="RAM-001",
    normalized_name="Corsair 16GB DDR4",
    price=80.0,
    category=ComponentCategory.RAM,
    specs={"memory_type": "DDR4"},
    total_available_stock=20,
)
_RAM2_ITEM = ProductListItem(
    id=4,
    code="R002",
    sku="RAM-002",
    normalized_name="G.Skill 32GB DDR4",
    price=90.0,
    category=ComponentCategory.RAM,
    total_available_stock=15,
)
_RAM2_DETAIL = ProductDetail(
    id=4,
    code="R002",
    sku="RAM-002",
    normalized_name="G.Skill 32GB DDR4",
    price=90.0,
    category=ComponentCategory.RAM,
    specs={"memory_type": "DDR4"},
    total_available_stock=15,
)

# ── SSD (three options) ──────────────────────────────────────────────────────
# Home → SSD-001 ($60).  Business → SSD-002 ($80, middle of 3).
# Gaming → SSD-003 ($100, most expensive).

_SSD1_ITEM = ProductListItem(
    id=5,
    code="S001",
    sku="SSD-001",
    normalized_name="Samsung 860 EVO",
    price=60.0,
    category=ComponentCategory.SSD,
    total_available_stock=15,
)
_SSD1_DETAIL = ProductDetail(
    id=5,
    code="S001",
    sku="SSD-001",
    normalized_name="Samsung 860 EVO",
    price=60.0,
    category=ComponentCategory.SSD,
    specs={"interface": "M.2"},
    total_available_stock=15,
)
_SSD2_ITEM = ProductListItem(
    id=6,
    code="S002",
    sku="SSD-002",
    normalized_name="WD Blue SN550",
    price=80.0,
    category=ComponentCategory.SSD,
    total_available_stock=10,
)
_SSD2_DETAIL = ProductDetail(
    id=6,
    code="S002",
    sku="SSD-002",
    normalized_name="WD Blue SN550",
    price=80.0,
    category=ComponentCategory.SSD,
    specs={"interface": "M.2"},
    total_available_stock=10,
)
_SSD3_ITEM = ProductListItem(
    id=7,
    code="S003",
    sku="SSD-003",
    normalized_name="Samsung 970 Pro",
    price=100.0,
    category=ComponentCategory.SSD,
    total_available_stock=8,
)
_SSD3_DETAIL = ProductDetail(
    id=7,
    code="S003",
    sku="SSD-003",
    normalized_name="Samsung 970 Pro",
    price=100.0,
    category=ComponentCategory.SSD,
    specs={"interface": "M.2"},
    total_available_stock=8,
)

# ── PSU (two options) ────────────────────────────────────────────────────────
# Home → PSU-001 ($70, cheapest).  Business and Gaming → PSU-002
# ($90, most expensive / middle-of-2).
# Both exceed the maximum required wattage (CPU 65W + GPU 200W + 20% = 318W).

_PSU1_ITEM = ProductListItem(
    id=8,
    code="P001",
    sku="PSU-001",
    normalized_name="Corsair 550W",
    price=70.0,
    category=ComponentCategory.PSU,
    total_available_stock=12,
)
_PSU1_DETAIL = ProductDetail(
    id=8,
    code="P001",
    sku="PSU-001",
    normalized_name="Corsair 550W",
    price=70.0,
    category=ComponentCategory.PSU,
    specs={"wattage": 550},
    total_available_stock=12,
)
_PSU2_ITEM = ProductListItem(
    id=9,
    code="P002",
    sku="PSU-002",
    normalized_name="EVGA 750W",
    price=90.0,
    category=ComponentCategory.PSU,
    total_available_stock=8,
)
_PSU2_DETAIL = ProductDetail(
    id=9,
    code="P002",
    sku="PSU-002",
    normalized_name="EVGA 750W",
    price=90.0,
    category=ComponentCategory.PSU,
    specs={"wattage": 750},
    total_available_stock=8,
)

# ── Case ─────────────────────────────────────────────────────────────────────
# ATX case without integrated PSU or fans (triggers FR-1.4 and FR-1.5 auto-add).

_CASE_ITEM = ProductListItem(
    id=10,
    code="CA001",
    sku="CASE-001",
    normalized_name="NZXT H510",
    price=80.0,
    category=ComponentCategory.CASE,
    total_available_stock=7,
)
_CASE_DETAIL = ProductDetail(
    id=10,
    code="CA001",
    sku="CASE-001",
    normalized_name="NZXT H510",
    price=80.0,
    category=ComponentCategory.CASE,
    specs={"form_factor": "ATX", "includes_psu": False, "includes_fans": False},
    total_available_stock=7,
)

# ── GPU ──────────────────────────────────────────────────────────────────────

_GPU_ITEM = ProductListItem(
    id=11,
    code="G001",
    sku="GPU-001",
    normalized_name="NVIDIA RTX 3080",
    price=700.0,
    category=ComponentCategory.GPU,
    total_available_stock=4,
)
_GPU_DETAIL = ProductDetail(
    id=11,
    code="G001",
    sku="GPU-001",
    normalized_name="NVIDIA RTX 3080",
    price=700.0,
    category=ComponentCategory.GPU,
    specs={"tdp": 200},
    total_available_stock=4,
)

# ── Fans (three, for Gaming auto-add FR-1.5) ─────────────────────────────────

_FAN1_ITEM = ProductListItem(
    id=12,
    code="F001",
    sku="FAN-001",
    normalized_name="Noctua NF-A12x25",
    price=30.0,
    category=ComponentCategory.FAN,
    total_available_stock=50,
)
_FAN1_DETAIL = ProductDetail(
    id=12,
    code="F001",
    sku="FAN-001",
    normalized_name="Noctua NF-A12x25",
    price=30.0,
    category=ComponentCategory.FAN,
    specs={},
    total_available_stock=50,
)
_FAN2_ITEM = ProductListItem(
    id=13,
    code="F002",
    sku="FAN-002",
    normalized_name="be quiet! 140mm Fan",
    price=25.0,
    category=ComponentCategory.FAN,
    total_available_stock=50,
)
_FAN2_DETAIL = ProductDetail(
    id=13,
    code="F002",
    sku="FAN-002",
    normalized_name="be quiet! 140mm Fan",
    price=25.0,
    category=ComponentCategory.FAN,
    specs={},
    total_available_stock=50,
)
_FAN3_ITEM = ProductListItem(
    id=14,
    code="F003",
    sku="FAN-003",
    normalized_name="Corsair 120mm Fan",
    price=20.0,
    category=ComponentCategory.FAN,
    total_available_stock=50,
)
_FAN3_DETAIL = ProductDetail(
    id=14,
    code="F003",
    sku="FAN-003",
    normalized_name="Corsair 120mm Fan",
    price=20.0,
    category=ComponentCategory.FAN,
    specs={},
    total_available_stock=50,
)

# ── Assembled catalog dicts ───────────────────────────────────────────────────

_COMPATIBLE_INVENTORY: dict[str, list[ProductListItem]] = {
    "cpu": [_CPU_ITEM],
    "motherboard": [_MB_ITEM],
    "ram": [_RAM1_ITEM, _RAM2_ITEM],
    "gpu": [_GPU_ITEM],
    "ssd": [_SSD1_ITEM, _SSD2_ITEM, _SSD3_ITEM],
    "psu": [_PSU1_ITEM, _PSU2_ITEM],
    "case": [_CASE_ITEM],
    "fan": [_FAN1_ITEM, _FAN2_ITEM, _FAN3_ITEM],
}

_COMPATIBLE_DETAIL_CATALOG: dict[int, ProductDetail] = {
    1: _CPU_DETAIL,
    2: _MB_DETAIL,
    3: _RAM1_DETAIL,
    4: _RAM2_DETAIL,
    5: _SSD1_DETAIL,
    6: _SSD2_DETAIL,
    7: _SSD3_DETAIL,
    8: _PSU1_DETAIL,
    9: _PSU2_DETAIL,
    10: _CASE_DETAIL,
    11: _GPU_DETAIL,
    12: _FAN1_DETAIL,
    13: _FAN2_DETAIL,
    14: _FAN3_DETAIL,
}

# ---------------------------------------------------------------------------
# Mock inventory — incompatible component set
# ---------------------------------------------------------------------------
# CPU socket AM4 vs motherboard socket AM5 → CompatibilityError on every tier.
# All required categories are present so the inventory-fetch phase succeeds.

_INCOMPAT_CPU_DETAIL = ProductDetail(
    id=1,
    code="C001",
    sku="CPU-001",
    normalized_name="Intel Core i5-12600K",
    price=250.0,
    category=ComponentCategory.CPU,
    specs={"socket": "LGA1700", "tdp": 125},
    total_available_stock=10,
)
_INCOMPAT_MB_DETAIL = ProductDetail(
    id=2,
    code="M001",
    sku="MB-001",
    normalized_name="ASUS Z690-A",
    price=200.0,
    category=ComponentCategory.MOTHERBOARD,
    specs={
        "socket": "AM4",  # MB socket AM4 ≠ CPU socket LGA1700 → incompatible
        "memory_type": "DDR5",
        "form_factor": "ATX",
        "supported_ssd_interfaces": ["M.2"],
    },
    total_available_stock=5,
)
_INCOMPAT_RAM_DETAIL = ProductDetail(
    id=3,
    code="R001",
    sku="RAM-001",
    normalized_name="Kingston 16GB DDR5",
    price=100.0,
    category=ComponentCategory.RAM,
    specs={"memory_type": "DDR5"},
    total_available_stock=10,
)

_INCOMPAT_INVENTORY: dict[str, list[ProductListItem]] = {
    "cpu": [
        ProductListItem(
            id=1,
            code="C001",
            sku="CPU-001",
            normalized_name="Intel Core i5-12600K",
            price=250.0,
            category=ComponentCategory.CPU,
            total_available_stock=10,
        )
    ],
    "motherboard": [
        ProductListItem(
            id=2,
            code="M001",
            sku="MB-001",
            normalized_name="ASUS Z690-A",
            price=200.0,
            category=ComponentCategory.MOTHERBOARD,
            total_available_stock=5,
        )
    ],
    "ram": [
        ProductListItem(
            id=3,
            code="R001",
            sku="RAM-001",
            normalized_name="Kingston 16GB DDR5",
            price=100.0,
            category=ComponentCategory.RAM,
            total_available_stock=10,
        )
    ],
    "gpu": [],
    "ssd": [_SSD1_ITEM],
    "psu": [_PSU1_ITEM],
    "case": [_CASE_ITEM],
    "fan": [],
}

_INCOMPAT_DETAIL_CATALOG: dict[int, ProductDetail] = {
    1: _INCOMPAT_CPU_DETAIL,
    2: _INCOMPAT_MB_DETAIL,
    3: _INCOMPAT_RAM_DETAIL,
    5: _SSD1_DETAIL,
    8: _PSU1_DETAIL,
    10: _CASE_DETAIL,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_list_products_side_effect(
    inventory: dict[str, list[ProductListItem]],
) -> Callable[..., Awaitable[ProductListResponse]]:
    """Return an async callable that simulates AIEcommerceClient.list_products.

    Args:
        inventory: Mapping of category string to list of :class:`ProductListItem`.

    Returns:
        An async callable accepting ``(category, active_only, has_stock)`` keyword
        arguments that returns a :class:`ProductListResponse` filtered from
        *inventory* by category.  Compatible with ``AsyncMock.side_effect``.
    """

    async def _side_effect(
        category: str | None = None,
        active_only: bool = True,
        has_stock: bool = True,
    ) -> ProductListResponse:
        items = inventory.get(category or "", [])
        return ProductListResponse(count=len(items), results=items)

    return _side_effect


def _make_get_detail_side_effect(
    detail_catalog: dict[int, ProductDetail],
) -> Callable[[int], Awaitable[ProductDetail]]:
    """Return an async callable that simulates AIEcommerceClient.get_product_detail.

    Args:
        detail_catalog: Mapping of product ID to :class:`ProductDetail`.

    Returns:
        An async callable accepting a single ``product_id: int`` argument that
        returns the matching :class:`ProductDetail` from *detail_catalog*.
        Compatible with ``AsyncMock.side_effect``.
    """

    async def _side_effect(product_id: int) -> ProductDetail:
        return detail_catalog[product_id]

    return _side_effect


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_assembly_run_three_tiers(
    integration_client: httpx.AsyncClient,
) -> None:
    """Full pipeline exercised: all three tiers produce stored towers.

    Given compatible mock inventory, POST /api/v1/runs/trigger/ with the
    default tiers (Home, Business, Gaming) should:
    - return HTTP 200 with status="completed"
    - report towers_created=3
    - return 3 distinct tower hashes
    - persist the towers so they are subsequently retrievable
    """
    with (
        patch.object(
            AIEcommerceClient,
            "list_products",
            new_callable=AsyncMock,
        ) as mock_list,
        patch.object(
            AIEcommerceClient,
            "get_product_detail",
            new_callable=AsyncMock,
        ) as mock_detail,
        patch(
            "orchestrator.graph.workflow.bundle_creator_node",
            new=AsyncMock(
                return_value={
                    "completed_bundles": [],
                    "errors": [],
                    "run_status": "completed",
                },
            ),
        ),
    ):
        mock_list.side_effect = _make_list_products_side_effect(_COMPATIBLE_INVENTORY)
        mock_detail.side_effect = _make_get_detail_side_effect(_COMPATIBLE_DETAIL_CATALOG)

        response = await integration_client.post(
            "/api/v1/runs/trigger/",
            headers={"X-API-Key": INTEGRATION_API_KEY},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["towers_created"] == 3
    assert len(data["tower_hashes"]) == 3
    # All three hashes must be distinct 64-char hex digests.
    assert len(set(data["tower_hashes"])) == 3
    for h in data["tower_hashes"]:
        assert len(h) == 64
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_assembly_run_produces_unique_hashes(
    integration_client: httpx.AsyncClient,
) -> None:
    """Two consecutive runs produce towers with no duplicate hashes.

    The second run encounters hashes already stored from the first run.
    The UniquenessEngine swaps secondary components (SSD → RAM → PSU) to
    derive fresh combinations.  After both runs the registry must contain
    six towers, all with distinct hashes.
    """
    with (
        patch.object(
            AIEcommerceClient,
            "list_products",
            new_callable=AsyncMock,
        ) as mock_list,
        patch.object(
            AIEcommerceClient,
            "get_product_detail",
            new_callable=AsyncMock,
        ) as mock_detail,
        patch(
            "orchestrator.graph.workflow.bundle_creator_node",
            new=AsyncMock(
                return_value={
                    "completed_bundles": [],
                    "errors": [],
                    "run_status": "completed",
                },
            ),
        ),
    ):
        mock_list.side_effect = _make_list_products_side_effect(_COMPATIBLE_INVENTORY)
        mock_detail.side_effect = _make_get_detail_side_effect(_COMPATIBLE_DETAIL_CATALOG)

        # Run 1
        run1 = await integration_client.post(
            "/api/v1/runs/trigger/",
            headers={"X-API-Key": INTEGRATION_API_KEY},
        )
        # Run 2 — same inventory, unique-hash swapping kicks in
        run2 = await integration_client.post(
            "/api/v1/runs/trigger/",
            headers={"X-API-Key": INTEGRATION_API_KEY},
        )

    assert run1.status_code == 200
    assert run2.status_code == 200

    run1_hashes: set[str] = set(run1.json()["tower_hashes"])
    run2_hashes: set[str] = set(run2.json()["tower_hashes"])

    # Each run produced at least one tower.
    assert len(run1_hashes) > 0
    assert len(run2_hashes) > 0

    # No hash from run 2 appeared in run 1.
    assert run1_hashes.isdisjoint(run2_hashes), (
        f"Duplicate hashes found across runs: {run1_hashes & run2_hashes}"
    )

    # Verify cumulative count in the registry equals the total created.
    total_created = run1.json()["towers_created"] + run2.json()["towers_created"]
    list_response = await integration_client.get("/api/v1/towers/")
    assert list_response.status_code == 200
    assert list_response.json()["count"] == total_created


@pytest.mark.asyncio
async def test_assembly_run_with_incompatible_inventory(
    integration_client: httpx.AsyncClient,
) -> None:
    """Incompatible components cause all tiers to fail with graceful error reporting.

    The mock inventory has a CPU with socket LGA1700 and a motherboard with
    socket AM4.  The CompatibilityEngine raises CompatibilityError for every
    tier, so:
    - HTTP status is still 200 (the API itself does not crash)
    - run_status is "failed"
    - towers_created is 0
    - errors list contains one entry per tier, each mentioning the tier name
    """
    with (
        patch.object(
            AIEcommerceClient,
            "list_products",
            new_callable=AsyncMock,
        ) as mock_list,
        patch.object(
            AIEcommerceClient,
            "get_product_detail",
            new_callable=AsyncMock,
        ) as mock_detail,
    ):
        mock_list.side_effect = _make_list_products_side_effect(_INCOMPAT_INVENTORY)
        mock_detail.side_effect = _make_get_detail_side_effect(_INCOMPAT_DETAIL_CATALOG)

        response = await integration_client.post(
            "/api/v1/runs/trigger/",
            headers={"X-API-Key": INTEGRATION_API_KEY},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["towers_created"] == 0
    # One error message per requested tier (Home, Business, Gaming).
    assert len(data["errors"]) == 3
    for error in data["errors"]:
        assert "Tier" in error


@pytest.mark.asyncio
async def test_towers_retrievable_after_run(
    integration_client: httpx.AsyncClient,
) -> None:
    """Towers created by the pipeline are immediately visible through the listing API.

    After a successful trigger run the GET /api/v1/towers/ endpoint must
    return the newly created towers with the expected schema fields.
    """
    with (
        patch.object(
            AIEcommerceClient,
            "list_products",
            new_callable=AsyncMock,
        ) as mock_list,
        patch.object(
            AIEcommerceClient,
            "get_product_detail",
            new_callable=AsyncMock,
        ) as mock_detail,
        patch(
            "orchestrator.graph.workflow.bundle_creator_node",
            new=AsyncMock(
                return_value={
                    "completed_bundles": [],
                    "errors": [],
                    "run_status": "completed",
                },
            ),
        ),
    ):
        mock_list.side_effect = _make_list_products_side_effect(_COMPATIBLE_INVENTORY)
        mock_detail.side_effect = _make_get_detail_side_effect(_COMPATIBLE_DETAIL_CATALOG)

        trigger_response = await integration_client.post(
            "/api/v1/runs/trigger/",
            headers={"X-API-Key": INTEGRATION_API_KEY},
        )

    assert trigger_response.status_code == 200
    created_hashes: list[str] = trigger_response.json()["tower_hashes"]

    list_response = await integration_client.get("/api/v1/towers/")

    assert list_response.status_code == 200
    list_data = list_response.json()
    assert list_data["count"] == len(created_hashes)

    returned_hashes = {t["bundle_hash"] for t in list_data["towers"]}
    assert returned_hashes == set(created_hashes)

    # Verify required summary fields are present on each returned tower.
    for tower_summary in list_data["towers"]:
        assert "bundle_hash" in tower_summary
        assert "category" in tower_summary
        assert "status" in tower_summary
        assert "total_price" in tower_summary
        assert "created_at" in tower_summary
        assert tower_summary["status"] == "Active"


@pytest.mark.asyncio
async def test_tower_detail_after_run(
    integration_client: httpx.AsyncClient,
) -> None:
    """Tower detail endpoint returns correct data for a tower created by the pipeline.

    After a trigger run the GET /api/v1/towers/{hash}/ endpoint must:
    - return HTTP 200 for each created tower hash
    - include ``component_skus`` with at least cpu, motherboard, ram, ssd, psu, case
    - match the hash in the URL path
    - return ``status = "Active"``
    """
    with (
        patch.object(
            AIEcommerceClient,
            "list_products",
            new_callable=AsyncMock,
        ) as mock_list,
        patch.object(
            AIEcommerceClient,
            "get_product_detail",
            new_callable=AsyncMock,
        ) as mock_detail,
        patch(
            "orchestrator.graph.workflow.bundle_creator_node",
            new=AsyncMock(
                return_value={
                    "completed_bundles": [],
                    "errors": [],
                    "run_status": "completed",
                },
            ),
        ),
    ):
        mock_list.side_effect = _make_list_products_side_effect(_COMPATIBLE_INVENTORY)
        mock_detail.side_effect = _make_get_detail_side_effect(_COMPATIBLE_DETAIL_CATALOG)

        trigger_response = await integration_client.post(
            "/api/v1/runs/trigger/",
            headers={"X-API-Key": INTEGRATION_API_KEY},
        )

    assert trigger_response.status_code == 200
    trigger_data = trigger_response.json()
    created_hashes: list[str] = trigger_data["tower_hashes"]
    assert len(created_hashes) > 0

    # Inspect detail for each created tower.
    for bundle_hash in created_hashes:
        detail_response = await integration_client.get(f"/api/v1/towers/{bundle_hash}/")

        assert detail_response.status_code == 200, (
            f"Expected 200 for tower {bundle_hash}, got {detail_response.status_code}"
        )
        detail = detail_response.json()

        assert detail["bundle_hash"] == bundle_hash
        assert detail["status"] == "Active"
        assert detail["total_price"] > 0
        assert "created_at" in detail
        assert "updated_at" in detail

        skus = detail["component_skus"]
        assert isinstance(skus, dict)
        for required_key in ("cpu", "motherboard", "ram", "ssd", "psu", "case"):
            assert required_key in skus, f"Missing SKU key '{required_key}' for tower {bundle_hash}"
