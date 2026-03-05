"""SHA-256 hash utility for bundles (tower + peripherals).

Computes a deterministic, order-independent hash that uniquely identifies a
bundle composed of a tower build and a set of peripheral accessories.  The
approach mirrors the tower hash produced by
:class:`~orchestrator.services.uniqueness.UniquenessEngine`.
"""

import hashlib


def compute_bundle_hash(tower_hash: str, peripheral_skus: dict[str, str]) -> str:
    """Compute SHA-256 hash for a bundle (tower + peripherals).

    The hash is computed from the tower hash concatenated with sorted
    peripheral role-SKU pairs, ensuring order independence.

    Args:
        tower_hash: The tower's hash (64-char hex).
        peripheral_skus: Mapping of peripheral role to SKU identifier
            (e.g. {"keyboard": "KB-001", "mouse": "MS-200"}).

    Returns:
        64-character lowercase hex SHA-256 digest.
    """
    sorted_peripherals = sorted(peripheral_skus.items())
    payload = tower_hash + "|" + "|".join(f"{role}:{sku}" for role, sku in sorted_peripherals)
    return hashlib.sha256(payload.encode()).hexdigest()
