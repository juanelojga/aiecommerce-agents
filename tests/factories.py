"""Test data factories for ORM models.

Each factory function returns a transient (unsaved) ORM instance with
sensible defaults. Any field can be overridden by passing keyword arguments.

Example usage::

    tower = make_tower(category=TowerCategory.HOME, total_price=799.99)
    bundle = make_bundle(tower_hash="a" * 64)
    audit = make_component_audit(sku="MY-SKU", stock_level=5)
"""

from orchestrator.models.bundle import PublishedBundle
from orchestrator.models.component_audit import ComponentAudit
from orchestrator.models.creative_asset import CreativeAsset
from orchestrator.models.tower import PublishedTower, TowerCategory, TowerStatus

# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------

_DEFAULT_TOWER_HASH = "a" * 64
_DEFAULT_BUNDLE_ID = "b" * 64
_DEFAULT_COMPONENT_SKUS: dict[str, object] = {
    "cpu": "AMD-RYZEN-5600X",
    "gpu": "NVIDIA-RTX3080",
}
_DEFAULT_PERIPHERAL_SKUS: dict[str, object] = {
    "monitor": "DELL-U2723D",
    "keyboard": "LOGITECH-MX-KEYS",
}


# ---------------------------------------------------------------------------
# PublishedTower factory
# ---------------------------------------------------------------------------


def make_tower(**overrides: object) -> PublishedTower:
    """Create a transient :class:`PublishedTower` with default field values.

    Args:
        **overrides: Any :class:`PublishedTower` field values to override.

    Returns:
        An unsaved :class:`PublishedTower` instance ready to be added to a
        database session.
    """
    defaults: dict[str, object] = {
        "bundle_hash": _DEFAULT_TOWER_HASH,
        "category": TowerCategory.GAMING,
        "status": TowerStatus.ACTIVE,
        "component_skus": dict(_DEFAULT_COMPONENT_SKUS),
        "total_price": 1299.99,
        "ml_id": None,
    }
    defaults.update(overrides)
    return PublishedTower(**defaults)


# ---------------------------------------------------------------------------
# PublishedBundle factory
# ---------------------------------------------------------------------------


def make_bundle(**overrides: object) -> PublishedBundle:
    """Create a transient :class:`PublishedBundle` with default field values.

    Args:
        **overrides: Any :class:`PublishedBundle` field values to override.

    Returns:
        An unsaved :class:`PublishedBundle` instance ready to be added to a
        database session.

    Note:
        The default ``tower_hash`` matches the default ``bundle_hash`` produced
        by :func:`make_tower`, so a ``make_tower`` + ``make_bundle`` pair is
        consistent without extra configuration.
    """
    defaults: dict[str, object] = {
        "bundle_id": _DEFAULT_BUNDLE_ID,
        "tower_hash": _DEFAULT_TOWER_HASH,
        "peripheral_skus": dict(_DEFAULT_PERIPHERAL_SKUS),
        "ml_id": None,
    }
    defaults.update(overrides)
    return PublishedBundle(**defaults)


# ---------------------------------------------------------------------------
# ComponentAudit factory
# ---------------------------------------------------------------------------


def make_component_audit(**overrides: object) -> ComponentAudit:
    """Create a transient :class:`ComponentAudit` with default field values.

    Args:
        **overrides: Any :class:`ComponentAudit` field values to override.

    Returns:
        An unsaved :class:`ComponentAudit` instance ready to be added to a
        database session.
    """
    defaults: dict[str, object] = {
        "sku": "AMD-RYZEN-5600X",
        "category": "CPU",
        "bundle_count": 0,
        "stock_level": 10,
        "last_bundled_date": None,
    }
    defaults.update(overrides)
    return ComponentAudit(**defaults)


# ---------------------------------------------------------------------------
# CreativeAsset factory
# ---------------------------------------------------------------------------


def make_creative_asset(**overrides: object) -> CreativeAsset:
    """Create a transient :class:`CreativeAsset` with default field values.

    Args:
        **overrides: Any :class:`CreativeAsset` field values to override.

    Returns:
        An unsaved :class:`CreativeAsset` instance ready to be added to a
        database session.
    """
    defaults: dict[str, object] = {
        "tower_hash": _DEFAULT_TOWER_HASH,
        "bundle_id": _DEFAULT_BUNDLE_ID,
        "media_type": "image",
        "url": "https://example.com/asset.png",
        "mime_type": "image/png",
        "width": 1920,
        "height": 1080,
        "duration_seconds": None,
        "style": "photorealistic",
        "prompt_used": "A high-end gaming PC setup",
    }
    defaults.update(overrides)
    return CreativeAsset(**defaults)
