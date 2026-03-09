"""Tests for the Channel Manager LangGraph node.

Covers FR-4.1 through FR-4.4:

- FR-4.1: Calculates final listing price via PricingCalculator.
- FR-4.3: Creates ML listing with title, description, price, images, video.
- FR-4.4: Stores ``mercadolibre_id`` in Local Registry via repositories.
- ML API errors handled gracefully (logs error, continues with other tiers).
- Returns ``{"published_listings": [...], "errors": [...], "run_status": "..."}``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.core.exceptions import MercadoLibreError
from orchestrator.graph.nodes.channel_manager import (
    _append_build_error,
    _collect_build_assets,
    _find_matching_bundle,
    channel_manager_node,
)
from orchestrator.graph.state import GraphState
from orchestrator.schemas.mercadolibre import MLListingResponse

# ---------------------------------------------------------------------------
# Test fixture helpers
# ---------------------------------------------------------------------------

_TOWER_HASH_A = "a" * 64
_TOWER_HASH_B = "b" * 64
_TOWER_HASH_C = "c" * 64


def _make_component(
    name: str,
    sku: str = "SKU-001",
    category: str = "cpu",
    price: float = 100.0,
) -> dict[str, object]:
    """Build a minimal serialised ``ComponentSelection`` dict for testing.

    Args:
        name: Normalised component name.
        sku: Stock-keeping unit code.
        category: Component category value string.
        price: Component price.

    Returns:
        A dict matching the shape of ``ComponentSelection.model_dump()``.
    """
    return {
        "sku": sku,
        "normalized_name": name,
        "category": category,
        "price": price,
        "specs": {
            "id": 1,
            "code": "CODE-1",
            "sku": sku,
            "normalized_name": name,
            "price": price,
            "category": category,
            "specs": {},
        },
    }


def _make_build(
    tier: str = "Gaming",
    bundle_hash: str = _TOWER_HASH_A,
) -> dict[str, object]:
    """Create a minimal serialised ``TowerBuild`` dict for testing.

    Args:
        tier: Build tier name (Home, Business, or Gaming).
        bundle_hash: SHA-256 hash identifying the build.

    Returns:
        A dict matching the shape of ``TowerBuild.model_dump()``.
    """
    return {
        "tier": tier,
        "bundle_hash": bundle_hash,
        "total_price": 700.0,
        "cpu": _make_component("Intel Core i7-13700K", "CPU-001", "cpu", 300.0),
        "motherboard": _make_component("ASUS ROG Strix Z790-E", "MB-001", "motherboard", 100.0),
        "ram": _make_component("Corsair 32GB DDR5", "RAM-001", "ram", 100.0),
        "gpu": _make_component("NVIDIA RTX 4080", "GPU-001", "gpu", 100.0),
        "ssd": _make_component("Samsung 990 Pro 2TB", "SSD-001", "ssd", 50.0),
        "psu": _make_component("Corsair RM850x", "PSU-001", "psu", 30.0),
        "case": _make_component("NZXT H510", "CASE-001", "case", 20.0),
    }


def _make_bundle(
    tower_hash: str = _TOWER_HASH_A,
    bundle_id: str = "bndl-001",
    tier: str = "Gaming",
) -> dict[str, object]:
    """Create a minimal serialised ``BundleBuild`` dict for testing.

    Args:
        tower_hash: SHA-256 hash of the associated tower build.
        bundle_id: Identifier for this bundle.
        tier: Build tier name.

    Returns:
        A dict matching the shape of ``BundleBuild.model_dump()``.
    """
    return {
        "tower_hash": tower_hash,
        "tier": tier,
        "peripherals": [
            {"normalized_name": "Logitech G Pro", "category": "keyboard"},
            {"normalized_name": "Logitech G502", "category": "mouse"},
        ],
        "bundle_id": bundle_id,
        "total_peripheral_price": 150.0,
    }


def _make_asset(
    tower_hash: str = _TOWER_HASH_A,
    media_type: str = "image",
    url: str = "https://storage.example.com/img.png",
) -> dict[str, object]:
    """Create a minimal serialised creative asset dict.

    Args:
        tower_hash: Tower hash this asset belongs to.
        media_type: Asset media type (image or video).
        url: Public URL of the asset.

    Returns:
        A dict matching the shape of creative asset data.
    """
    return {
        "tower_hash": tower_hash,
        "media_type": media_type,
        "url": url,
    }


def _make_ml_response(
    ml_id: str = "MLA123456789",
    title: str = "PC Gaming",
    price: float = 1000.0,
) -> MLListingResponse:
    """Create a mock ML listing response.

    Args:
        ml_id: MercadoLibre listing ID.
        title: Listing title.
        price: Listing price.

    Returns:
        An MLListingResponse instance.
    """
    return MLListingResponse(
        id=ml_id,
        title=title,
        price=price,
        status="active",
        permalink=f"https://www.mercadolibre.com.ar/{ml_id}",
    )


def _configure_session_factory(mock_factory: Any) -> AsyncMock:
    """Configure the async_session_factory mock as an async context manager.

    Returns:
        The mock session object for further assertions.
    """
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_session


def _patch_node(
    ml_client_mock: Any | None = None,
    ml_response: MLListingResponse | None = None,
    ml_error: MercadoLibreError | None = None,
) -> tuple[Any, ...]:
    """Build context manager patches for channel_manager_node.

    Args:
        ml_client_mock: Custom MercadoLibreClient mock.
        ml_response: ML response to return from create_listing.
        ml_error: Error to raise from create_listing.

    Returns:
        Tuple of (patches..., ml_client_mock_instance).
    """
    if ml_client_mock is None:
        ml_client_mock = MagicMock()
        if ml_error:
            ml_client_mock.create_listing = AsyncMock(side_effect=ml_error)
        else:
            resp = ml_response or _make_ml_response()
            ml_client_mock.create_listing = AsyncMock(return_value=resp)
        ml_client_mock.upload_image = AsyncMock(return_value="ML-IMG-001")
        ml_client_mock.upload_video = AsyncMock(return_value="ML-VID-001")

    tower_repo_mock = AsyncMock()
    tower_repo_mock.update_ml_id = AsyncMock(return_value=None)

    bundle_repo_mock = AsyncMock()
    bundle_repo_mock.update_ml_id = AsyncMock(return_value=None)

    return (
        patch(
            "orchestrator.graph.nodes.channel_manager.MercadoLibreClient",
            return_value=ml_client_mock,
        ),
        patch(
            "orchestrator.graph.nodes.channel_manager.TowerRepository",
            return_value=tower_repo_mock,
        ),
        patch(
            "orchestrator.graph.nodes.channel_manager.BundleRepository",
            return_value=bundle_repo_mock,
        ),
        patch(
            "orchestrator.graph.nodes.channel_manager.async_session_factory",
        ),
        ml_client_mock,
        tower_repo_mock,
        bundle_repo_mock,
    )


async def _run_node(
    state: GraphState,
    ml_client_mock: Any | None = None,
    ml_response: MLListingResponse | None = None,
    ml_error: MercadoLibreError | None = None,
) -> tuple[dict[str, object], Any, Any, Any]:
    """Execute the channel_manager_node with all dependencies mocked.

    Returns:
        Tuple of (result_dict, ml_client_mock, tower_repo_mock, bundle_repo_mock).
    """
    (
        ml_client_patch,
        tower_repo_patch,
        bundle_repo_patch,
        session_patch,
        ml_client,
        tower_repo,
        bundle_repo,
    ) = _patch_node(ml_client_mock, ml_response, ml_error)

    with ml_client_patch, tower_repo_patch, bundle_repo_patch, session_patch as mock_factory:
        _configure_session_factory(mock_factory)
        result = await channel_manager_node(state)

    return result, ml_client, tower_repo, bundle_repo


# ---------------------------------------------------------------------------
# Unit tests: helper functions
# ---------------------------------------------------------------------------


class TestCollectBuildAssets:
    """Tests for _collect_build_assets."""

    def test_collects_images_and_video(self) -> None:
        """Returns image URLs and video URL for a matching tower_hash."""
        assets: list[dict[str, object]] = [
            _make_asset(_TOWER_HASH_A, "image", "https://img1.png"),
            _make_asset(_TOWER_HASH_A, "image", "https://img2.png"),
            _make_asset(_TOWER_HASH_A, "video", "https://video.mp4"),
            _make_asset(_TOWER_HASH_B, "image", "https://other.png"),
        ]
        images, video = _collect_build_assets(_TOWER_HASH_A, assets)
        assert images == ["https://img1.png", "https://img2.png"]
        assert video == "https://video.mp4"

    def test_no_matching_assets(self) -> None:
        """Returns empty lists when no assets match the tower_hash."""
        assets = [_make_asset(_TOWER_HASH_B, "image", "https://img.png")]
        images, video = _collect_build_assets(_TOWER_HASH_A, assets)
        assert images == []
        assert video is None

    def test_images_only(self) -> None:
        """Returns images when there are no video assets."""
        assets = [_make_asset(_TOWER_HASH_A, "image", "https://img.png")]
        images, video = _collect_build_assets(_TOWER_HASH_A, assets)
        assert images == ["https://img.png"]
        assert video is None


class TestFindMatchingBundle:
    """Tests for _find_matching_bundle."""

    def test_correct_hash_matching(self) -> None:
        """Returns the bundle whose tower_hash matches the build's bundle_hash."""
        build = _make_build(bundle_hash=_TOWER_HASH_A)
        bundles = [
            _make_bundle(tower_hash=_TOWER_HASH_B, bundle_id="bndl-B"),
            _make_bundle(tower_hash=_TOWER_HASH_A, bundle_id="bndl-A"),
        ]
        result = _find_matching_bundle(build, bundles)
        assert result is not None
        assert result["bundle_id"] == "bndl-A"

    def test_no_match(self) -> None:
        """Returns None when no bundle matches."""
        build = _make_build(bundle_hash=_TOWER_HASH_C)
        bundles = [_make_bundle(tower_hash=_TOWER_HASH_A)]
        result = _find_matching_bundle(build, bundles)
        assert result is None

    def test_empty_bundles(self) -> None:
        """Returns None when bundles list is empty."""
        build = _make_build()
        assert _find_matching_bundle(build, []) is None


class TestAppendBuildError:
    """Tests for _append_build_error."""

    def test_appends_formatted_error(self) -> None:
        """Appends a formatted error message with the tier prefix."""
        errors: list[str] = []
        _append_build_error(errors, "Gaming", "Upload failed")
        assert len(errors) == 1
        assert errors[0] == "Tier 'Gaming': Upload failed"


# ---------------------------------------------------------------------------
# Integration tests: channel_manager_node
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_channel_manager_empty_builds() -> None:
    """Empty builds → empty listings, completed status."""
    state = GraphState(completed_builds=[], completed_bundles=[], completed_assets=[])
    result, _, _, _ = await _run_node(state)
    assert result["published_listings"] == []
    assert result["errors"] == []
    assert result["run_status"] == "completed"


@pytest.mark.asyncio
async def test_channel_manager_single_build() -> None:
    """Single build produces 1 published listing."""
    build = _make_build()
    assets = [
        _make_asset(_TOWER_HASH_A, "image", "https://img1.png"),
        _make_asset(_TOWER_HASH_A, "image", "https://img2.png"),
    ]
    state = GraphState(
        completed_builds=[build],
        completed_bundles=[_make_bundle()],
        completed_assets=assets,
    )
    result, ml_client, _, _ = await _run_node(state)
    assert len(result["published_listings"]) == 1  # type: ignore[arg-type]
    ml_client.create_listing.assert_called_once()


@pytest.mark.asyncio
async def test_channel_manager_price_calculation() -> None:
    """Correct price in ML listing request (FR-4.1).

    Build component sum = 300 + 100 + 100 + 100 + 50 + 30 + 20 = 700
    With 0% margin and 0% fee: price = 700.0
    """
    build = _make_build()
    state = GraphState(
        completed_builds=[build],
        completed_bundles=[],
        completed_assets=[],
    )

    with (
        patch(
            "orchestrator.graph.nodes.channel_manager.get_settings",
        ) as mock_settings,
        patch(
            "orchestrator.graph.nodes.channel_manager.MercadoLibreClient",
        ) as mock_ml_cls,
        patch(
            "orchestrator.graph.nodes.channel_manager.TowerRepository",
            return_value=AsyncMock(),
        ),
        patch(
            "orchestrator.graph.nodes.channel_manager.BundleRepository",
            return_value=AsyncMock(),
        ),
        patch(
            "orchestrator.graph.nodes.channel_manager.async_session_factory",
        ) as mock_factory,
    ):
        settings = MagicMock()
        settings.ASSEMBLY_MARGIN_PERCENT = 0.0
        settings.ML_FEE_PERCENT = 0.0
        mock_settings.return_value = settings

        ml_mock = MagicMock()
        ml_mock.create_listing = AsyncMock(return_value=_make_ml_response())
        ml_mock.upload_image = AsyncMock(return_value="ML-IMG-001")
        ml_mock.upload_video = AsyncMock(return_value="ML-VID-001")
        mock_ml_cls.return_value = ml_mock

        _configure_session_factory(mock_factory)

        result = await channel_manager_node(state)

    # Verify the listing was created with the correct price.
    call_args = ml_mock.create_listing.call_args
    listing_req = call_args[0][0]
    assert listing_req.price == 700.0
    assert result["run_status"] == "completed"


@pytest.mark.asyncio
async def test_channel_manager_title_generation() -> None:
    """Listing title matches expected format from ListingContentGenerator."""
    build = _make_build()
    state = GraphState(
        completed_builds=[build],
        completed_bundles=[],
        completed_assets=[],
    )
    _result, ml_client, _, _ = await _run_node(state)

    # Verify the listing was created with a non-empty title.
    call_args = ml_client.create_listing.call_args
    listing_req = call_args[0][0]
    assert listing_req.title
    # Should contain "PC" and tier.
    assert "PC" in listing_req.title
    assert "Gaming" in listing_req.title


@pytest.mark.asyncio
async def test_channel_manager_media_upload() -> None:
    """Images and video uploaded to ML."""
    build = _make_build()
    assets = [
        _make_asset(_TOWER_HASH_A, "image", "https://img1.png"),
        _make_asset(_TOWER_HASH_A, "image", "https://img2.png"),
        _make_asset(_TOWER_HASH_A, "video", "https://video.mp4"),
    ]
    state = GraphState(
        completed_builds=[build],
        completed_bundles=[],
        completed_assets=assets,
    )
    _result, ml_client, _, _ = await _run_node(state)

    # 2 images uploaded.
    assert ml_client.upload_image.call_count == 2
    # 1 video uploaded.
    assert ml_client.upload_video.call_count == 1

    # Listing request should have picture IDs and video_id.
    call_args = ml_client.create_listing.call_args
    listing_req = call_args[0][0]
    assert len(listing_req.pictures) == 2
    assert listing_req.video_id == "ML-VID-001"


@pytest.mark.asyncio
async def test_channel_manager_ml_id_stored() -> None:
    """ML ID stored in tower repository (FR-4.4)."""
    build = _make_build()
    bundle = _make_bundle()
    state = GraphState(
        completed_builds=[build],
        completed_bundles=[bundle],
        completed_assets=[],
    )
    _result, _, tower_repo, bundle_repo = await _run_node(
        state, ml_response=_make_ml_response(ml_id="MLA-STORED")
    )

    # Tower repo should have update_ml_id called with the tower hash and ML ID.
    tower_repo.update_ml_id.assert_called_once_with(_TOWER_HASH_A, "MLA-STORED")
    # Bundle repo should also have update_ml_id called.
    bundle_repo.update_ml_id.assert_called_once()


@pytest.mark.asyncio
async def test_channel_manager_ml_api_error() -> None:
    """ML error logged, other tiers still processed."""
    build_a = _make_build(tier="Gaming", bundle_hash=_TOWER_HASH_A)
    build_b = _make_build(tier="Home", bundle_hash=_TOWER_HASH_B)

    ml_client = MagicMock()
    ml_client.upload_image = AsyncMock(return_value="ML-IMG-001")
    ml_client.upload_video = AsyncMock(return_value="ML-VID-001")
    # First call fails, second succeeds.
    ml_client.create_listing = AsyncMock(
        side_effect=[
            MercadoLibreError("API error", status_code=500),
            _make_ml_response(ml_id="MLA-HOME"),
        ]
    )

    state = GraphState(
        completed_builds=[build_a, build_b],
        completed_bundles=[],
        completed_assets=[],
    )
    result, _, _, _ = await _run_node(state, ml_client_mock=ml_client)

    # One listing failed, one succeeded.
    assert len(result["published_listings"]) == 1  # type: ignore[arg-type]
    assert len(result["errors"]) >= 1  # type: ignore[arg-type]
    # The surviving listing is from Home tier.
    listings = result["published_listings"]
    assert isinstance(listings, list)
    listing = listings[0]
    assert isinstance(listing, dict)
    assert listing["ml_id"] == "MLA-HOME"
    # Status should still be completed since at least one listing succeeded.
    assert result["run_status"] == "completed"


@pytest.mark.asyncio
async def test_channel_manager_multiple_tiers() -> None:
    """All 3 tiers published independently."""
    builds = [
        _make_build(tier="Home", bundle_hash=_TOWER_HASH_A),
        _make_build(tier="Business", bundle_hash=_TOWER_HASH_B),
        _make_build(tier="Gaming", bundle_hash=_TOWER_HASH_C),
    ]
    ml_client = MagicMock()
    ml_client.upload_image = AsyncMock(return_value="ML-IMG-001")
    ml_client.upload_video = AsyncMock(return_value="ML-VID-001")
    ml_client.create_listing = AsyncMock(
        side_effect=[
            _make_ml_response(ml_id="MLA-HOME"),
            _make_ml_response(ml_id="MLA-BIZ"),
            _make_ml_response(ml_id="MLA-GAMING"),
        ]
    )
    state = GraphState(
        completed_builds=builds,
        completed_bundles=[],
        completed_assets=[],
    )
    result, _, _, _ = await _run_node(state, ml_client_mock=ml_client)

    assert len(result["published_listings"]) == 3  # type: ignore[arg-type]
    assert result["run_status"] == "completed"
    listings = result["published_listings"]
    assert isinstance(listings, list)
    ml_ids = [p["ml_id"] for p in listings]
    assert "MLA-HOME" in ml_ids
    assert "MLA-BIZ" in ml_ids
    assert "MLA-GAMING" in ml_ids


@pytest.mark.asyncio
async def test_channel_manager_no_assets() -> None:
    """Build without assets still published (no images)."""
    build = _make_build()
    state = GraphState(
        completed_builds=[build],
        completed_bundles=[],
        completed_assets=[],
    )
    result, ml_client, _, _ = await _run_node(state)

    # Listing should still be created even without media assets.
    ml_client.create_listing.assert_called_once()
    call_args = ml_client.create_listing.call_args
    listing_req = call_args[0][0]
    assert listing_req.pictures == []
    assert listing_req.video_id is None
    assert len(result["published_listings"]) == 1  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_channel_manager_published_listings_output() -> None:
    """Output dict contains serialized listing data."""
    build = _make_build()
    state = GraphState(
        completed_builds=[build],
        completed_bundles=[],
        completed_assets=[],
    )
    result, _, _, _ = await _run_node(
        state, ml_response=_make_ml_response(ml_id="MLA-OUT", price=1234.56)
    )

    listings = result["published_listings"]
    assert isinstance(listings, list)
    assert len(listings) == 1
    listing = listings[0]
    assert isinstance(listing, dict)
    assert listing["ml_id"] == "MLA-OUT"
    assert listing["price"] == 1234.56
    assert listing["tier"] == "Gaming"
    assert "permalink" in listing


@pytest.mark.asyncio
async def test_channel_manager_bundle_listing() -> None:
    """Bundle listing includes peripheral info in description."""
    build = _make_build()
    bundle = _make_bundle(
        tower_hash=_TOWER_HASH_A,
        bundle_id="bndl-kit",
    )
    state = GraphState(
        completed_builds=[build],
        completed_bundles=[bundle],
        completed_assets=[],
    )
    _result, ml_client, _, _ = await _run_node(state)

    call_args = ml_client.create_listing.call_args
    listing_req = call_args[0][0]
    # Description should mention peripherals.
    assert "Periféricos" in listing_req.description
    # Title should use Kit format.
    assert "Kit PC" in listing_req.title
