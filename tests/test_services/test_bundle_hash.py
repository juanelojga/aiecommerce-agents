"""Tests for the bundle hash utility."""

from orchestrator.services.bundle_hash import compute_bundle_hash

# A sample 64-char hex string representing a tower hash.
_TOWER_HASH = "a" * 64
_ALT_TOWER_HASH = "b" * 64


class TestComputeBundleHash:
    """Unit tests for :func:`compute_bundle_hash`."""

    def test_deterministic_hash(self) -> None:
        """Same inputs must always produce the same hash."""
        peripherals = {"keyboard": "KB-001", "mouse": "MS-200"}
        first = compute_bundle_hash(_TOWER_HASH, peripherals)
        second = compute_bundle_hash(_TOWER_HASH, peripherals)
        assert first == second

    def test_different_peripherals_different_hash(self) -> None:
        """Different peripheral SKUs must produce different hashes."""
        hash_a = compute_bundle_hash(_TOWER_HASH, {"keyboard": "KB-001"})
        hash_b = compute_bundle_hash(_TOWER_HASH, {"keyboard": "KB-999"})
        assert hash_a != hash_b

    def test_different_tower_different_hash(self) -> None:
        """A different tower hash must produce a different bundle hash."""
        peripherals = {"keyboard": "KB-001", "mouse": "MS-200"}
        hash_a = compute_bundle_hash(_TOWER_HASH, peripherals)
        hash_b = compute_bundle_hash(_ALT_TOWER_HASH, peripherals)
        assert hash_a != hash_b

    def test_order_independent(self) -> None:
        """Dict insertion order must not affect the resulting hash."""
        hash_a = compute_bundle_hash(_TOWER_HASH, {"keyboard": "KB-001", "mouse": "MS-200"})
        hash_b = compute_bundle_hash(_TOWER_HASH, {"mouse": "MS-200", "keyboard": "KB-001"})
        assert hash_a == hash_b

    def test_hash_length_64(self) -> None:
        """Output must be a 64-character lowercase hex string."""
        result = compute_bundle_hash(_TOWER_HASH, {"keyboard": "KB-001"})
        assert len(result) == 64
        assert result == result.lower()
        assert all(c in "0123456789abcdef" for c in result)

    def test_empty_peripherals(self) -> None:
        """Function must handle an empty peripheral dict without error."""
        result = compute_bundle_hash(_TOWER_HASH, {})
        assert isinstance(result, str)
        assert len(result) == 64
