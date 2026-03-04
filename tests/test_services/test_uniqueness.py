"""Tests for the SHA-256 uniqueness engine."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from orchestrator.core.exceptions import UniquenessError
from orchestrator.schemas.inventory import (
    ComponentCategory,
    ComponentSelection,
    ProductSpecs,
    TowerBuild,
)
from orchestrator.services.uniqueness import UniquenessEngine

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_specs(sku: str) -> ProductSpecs:
    """Return minimal ProductSpecs for a given SKU."""
    return ProductSpecs(id=1, sku=sku)


def _make_selection(
    category: ComponentCategory, sku: str, price: float = 100.0
) -> ComponentSelection:
    """Return a ComponentSelection for the given category and SKU."""
    return ComponentSelection(
        sku=sku,
        name=f"Component {sku}",
        category=category,
        price=price,
        specs=_make_specs(sku),
    )


def _make_build(
    cpu_sku: str = "CPU-001",
    mb_sku: str = "MB-001",
    ram_sku: str = "RAM-001",
    ssd_sku: str = "SSD-001",
    psu_sku: str = "PSU-001",
    case_sku: str = "CASE-001",
) -> TowerBuild:
    """Build a minimal TowerBuild with the supplied SKUs."""
    return TowerBuild(
        tier="Home",
        cpu=_make_selection(ComponentCategory.CPU, cpu_sku),
        motherboard=_make_selection(ComponentCategory.MOTHERBOARD, mb_sku),
        ram=_make_selection(ComponentCategory.RAM, ram_sku),
        ssd=_make_selection(ComponentCategory.SSD, ssd_sku),
        psu=_make_selection(ComponentCategory.PSU, psu_sku),
        case=_make_selection(ComponentCategory.CASE, case_sku),
    )


def _make_engine(hash_exists_return: bool = False) -> UniquenessEngine:
    """Return an UniquenessEngine with a mocked TowerRepository."""
    repo = MagicMock()
    repo.hash_exists = AsyncMock(return_value=hash_exists_return)
    return UniquenessEngine(tower_repository=repo)


# ---------------------------------------------------------------------------
# compute_hash
# ---------------------------------------------------------------------------


class TestComputeHash:
    """Tests for UniquenessEngine.compute_hash."""

    def test_compute_hash_deterministic(self) -> None:
        """Same build always produces the same hash."""
        engine = _make_engine()
        build = _make_build()
        assert engine.compute_hash(build) == engine.compute_hash(build)

    def test_compute_hash_order_independent(self) -> None:
        """Hash is derived from a sorted SKU set, so the collection order is irrelevant.

        Verify that the hash matches a manually computed SHA-256 over the
        *sorted* SKU list, confirming that sorted() is applied before hashing.
        """
        import hashlib

        engine = _make_engine()
        build = _make_build(
            cpu_sku="CPU-001",
            mb_sku="MB-001",
            ram_sku="RAM-001",
            ssd_sku="SSD-001",
            psu_sku="PSU-001",
            case_sku="CASE-001",
        )
        # Manually compute the expected hash using the same sorted-join strategy.
        skus = ["CPU-001", "MB-001", "RAM-001", "SSD-001", "PSU-001", "CASE-001"]
        expected = hashlib.sha256(",".join(sorted(skus)).encode()).hexdigest()
        assert engine.compute_hash(build) == expected

    def test_compute_hash_64_chars(self) -> None:
        """SHA-256 hex digest is exactly 64 characters long."""
        engine = _make_engine()
        digest = engine.compute_hash(_make_build())
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_compute_hash_differs_on_different_skus(self) -> None:
        """Different SKU sets produce different hashes."""
        engine = _make_engine()
        hash_a = engine.compute_hash(_make_build(cpu_sku="CPU-001"))
        hash_b = engine.compute_hash(_make_build(cpu_sku="CPU-999"))
        assert hash_a != hash_b

    def test_compute_hash_excludes_gpu(self) -> None:
        """GPU is excluded from the hash; builds differing only in GPU must match."""
        engine = _make_engine()
        build_without_gpu = _make_build()
        build_with_gpu = build_without_gpu.model_copy(
            update={"gpu": _make_selection(ComponentCategory.GPU, "GPU-001")}
        )
        assert engine.compute_hash(build_without_gpu) == engine.compute_hash(build_with_gpu)


# ---------------------------------------------------------------------------
# is_unique
# ---------------------------------------------------------------------------


class TestIsUnique:
    """Tests for UniquenessEngine.is_unique."""

    @pytest.mark.asyncio
    async def test_is_unique_true(self) -> None:
        """Returns True when the hash does not exist in the registry."""
        engine = _make_engine(hash_exists_return=False)
        assert await engine.is_unique(_make_build()) is True

    @pytest.mark.asyncio
    async def test_is_unique_false(self) -> None:
        """Returns False when the hash already exists in the registry."""
        engine = _make_engine(hash_exists_return=True)
        assert await engine.is_unique(_make_build()) is False


# ---------------------------------------------------------------------------
# ensure_unique
# ---------------------------------------------------------------------------


class TestEnsureUnique:
    """Tests for UniquenessEngine.ensure_unique."""

    @pytest.mark.asyncio
    async def test_ensure_unique_already_unique(self) -> None:
        """Returns the build unchanged when it is already unique."""
        engine = _make_engine(hash_exists_return=False)
        build = _make_build()
        result = await engine.ensure_unique(build, alternatives={})
        # The returned build has bundle_hash populated.
        assert len(result.bundle_hash) == 64
        # Core components are unchanged.
        assert result.cpu.sku == build.cpu.sku
        assert result.ssd.sku == build.ssd.sku

    @pytest.mark.asyncio
    async def test_ensure_unique_stamps_bundle_hash(self) -> None:
        """ensure_unique populates bundle_hash on the returned build."""
        engine = _make_engine(hash_exists_return=False)
        build = _make_build()
        result = await engine.ensure_unique(build, alternatives={})
        assert result.bundle_hash == engine.compute_hash(build)

    @pytest.mark.asyncio
    async def test_ensure_unique_swaps_ssd_on_collision(self) -> None:
        """Swaps SSD when the initial build collides."""
        repo = MagicMock()
        # First call (original build) → exists; second call (swapped SSD) → unique.
        repo.hash_exists = AsyncMock(side_effect=[True, False])
        engine = UniquenessEngine(tower_repository=repo)

        build = _make_build(ssd_sku="SSD-001")
        alt_ssd = _make_selection(ComponentCategory.SSD, "SSD-002")
        result = await engine.ensure_unique(build, alternatives={"ssd": [alt_ssd]})

        assert result.ssd.sku == "SSD-002"

    @pytest.mark.asyncio
    async def test_ensure_unique_swaps_ram_after_ssd_exhausted(self) -> None:
        """Falls through to RAM swap when no SSD alternatives remain."""
        repo = MagicMock()
        # First call (original) → exists; second call (swapped RAM) → unique.
        repo.hash_exists = AsyncMock(side_effect=[True, False])
        engine = UniquenessEngine(tower_repository=repo)

        build = _make_build(ram_sku="RAM-001")
        alt_ram = _make_selection(ComponentCategory.RAM, "RAM-002")
        # No SSD alternatives provided.
        result = await engine.ensure_unique(build, alternatives={"ram": [alt_ram]})

        assert result.ram.sku == "RAM-002"

    @pytest.mark.asyncio
    async def test_ensure_unique_swaps_psu_as_last_resort(self) -> None:
        """Falls through to PSU swap when SSD and RAM alternatives are exhausted."""
        repo = MagicMock()
        repo.hash_exists = AsyncMock(side_effect=[True, False])
        engine = UniquenessEngine(tower_repository=repo)

        build = _make_build(psu_sku="PSU-001")
        alt_psu = _make_selection(ComponentCategory.PSU, "PSU-002")
        result = await engine.ensure_unique(build, alternatives={"psu": [alt_psu]})

        assert result.psu.sku == "PSU-002"

    @pytest.mark.asyncio
    async def test_ensure_unique_exhausted_raises(self) -> None:
        """Raises UniquenessError when all alternatives are exhausted."""
        # Every hash_exists call returns True → every candidate collides.
        engine = _make_engine(hash_exists_return=True)
        build = _make_build()

        with pytest.raises(UniquenessError):
            await engine.ensure_unique(build, alternatives={}, max_attempts=3)

    @pytest.mark.asyncio
    async def test_ensure_unique_multiple_ssd_alternatives(self) -> None:
        """Cycles through multiple SSD alternatives until one is unique."""
        repo = MagicMock()
        # Original + first SSD swap collide; second SSD swap is unique.
        repo.hash_exists = AsyncMock(side_effect=[True, True, False])
        engine = UniquenessEngine(tower_repository=repo)

        build = _make_build(ssd_sku="SSD-001")
        alt_ssds = [
            _make_selection(ComponentCategory.SSD, "SSD-002"),
            _make_selection(ComponentCategory.SSD, "SSD-003"),
        ]
        result = await engine.ensure_unique(build, alternatives={"ssd": alt_ssds})

        assert result.ssd.sku == "SSD-003"
