"""SHA-256 uniqueness engine for tower builds.

Computes a deterministic hash from the core component SKU set of a
:class:`~orchestrator.schemas.product.TowerBuild`, checks the Local Registry
for duplicates, and swaps secondary components when a collision is detected.
"""

import hashlib
import logging

from orchestrator.core.exceptions import UniquenessError
from orchestrator.schemas.product import ComponentCategory, ComponentSelection, TowerBuild
from orchestrator.services.tower_repository import TowerRepository

logger = logging.getLogger(__name__)

# The ordered list of categories used to derive the bundle hash.
# GPU and fans are intentionally excluded: two towers that share the same core
# components but differ only in GPU are treated as the same build.
_CORE_CATEGORIES: tuple[ComponentCategory, ...] = (
    ComponentCategory.CPU,
    ComponentCategory.MOTHERBOARD,
    ComponentCategory.RAM,
    ComponentCategory.SSD,
    ComponentCategory.PSU,
    ComponentCategory.CASE,
)

# The swap order for resolving hash collisions.  Secondary components are cycled
# through this sequence before giving up and raising UniquenessError.
_SWAP_ORDER: tuple[ComponentCategory, ...] = (
    ComponentCategory.SSD,
    ComponentCategory.RAM,
    ComponentCategory.PSU,
)


class UniquenessEngine:
    """Ensures every build has a unique component combination.

    Computes SHA-256 hash of sorted core SKU set (CPU, MB, RAM, SSD, PSU, Case)
    and verifies against the Local Registry.

    Args:
        tower_repository: Repository used to check for existing hashes.
    """

    def __init__(self, tower_repository: TowerRepository) -> None:
        """Initialise with an injected tower repository.

        Args:
            tower_repository: The data-access object used to query existing hashes.
        """
        self._repo = tower_repository

    def compute_hash(self, build: TowerBuild) -> str:
        """Compute SHA-256 hash from core component SKUs.

        The hash is produced from the *sorted* set of core-component SKUs so
        that the result is order-independent and deterministic for a given
        component selection.

        Args:
            build: The tower build whose core SKUs to hash.

        Returns:
            64-character hex digest of the sorted SKU set.
        """
        # Collect SKUs for the six core categories; GPU and fans are excluded.
        core_skus: list[str] = [
            build.cpu.sku,
            build.motherboard.sku,
            build.ram.sku,
            build.ssd.sku,
            build.psu.sku,
            build.case.sku,
        ]
        # Sort to guarantee the same hash regardless of construction order.
        canonical = ",".join(sorted(core_skus))
        return hashlib.sha256(canonical.encode()).hexdigest()

    async def is_unique(self, build: TowerBuild) -> bool:
        """Check if the build hash is unique in the registry.

        Args:
            build: The build to check.

        Returns:
            ``True`` if no tower with this hash exists, ``False`` otherwise.
        """
        bundle_hash = self.compute_hash(build)
        exists = await self._repo.hash_exists(bundle_hash)
        return not exists

    async def ensure_unique(
        self,
        build: TowerBuild,
        alternatives: dict[str, list[ComponentSelection]],
        max_attempts: int = 10,
    ) -> TowerBuild:
        """Ensure build uniqueness, swapping secondary components if needed.

        Iterates through alternative components in the order defined by
        :data:`_SWAP_ORDER` (SSD → RAM → PSU).  For each category a candidate
        replacement is popped from the front of the corresponding list in
        *alternatives* and applied to a new build copy before re-checking
        uniqueness.  If all alternatives are exhausted without finding a unique
        build, :class:`~orchestrator.core.exceptions.UniquenessError` is raised.

        Args:
            build: The initial build to check.
            alternatives: Mapping of category name → alternative components.
            max_attempts: Maximum swap attempts before raising UniquenessError.

        Returns:
            A unique build (may have swapped components).

        Raises:
            UniquenessError: If no unique combination is found within
                *max_attempts* swaps.
        """
        current = build
        attempts = 0

        # Track remaining alternatives per swap-category so we can pop from
        # them without mutating the caller's dict.
        remaining: dict[str, list[ComponentSelection]] = {
            key: list(value) for key, value in alternatives.items()
        }

        while attempts < max_attempts:
            if await self.is_unique(current):
                # Stamp the computed hash onto the returned build.
                return current.model_copy(update={"bundle_hash": self.compute_hash(current)})

            attempts += 1
            swapped = False

            for category in _SWAP_ORDER:
                alt_list = remaining.get(category.value, [])
                if alt_list:
                    replacement = alt_list.pop(0)
                    current = self._apply_swap(current, category, replacement)
                    swapped = True
                    logger.debug(
                        "Swapped %s to %s after collision (attempt %d)",
                        category.value,
                        replacement.sku,
                        attempts,
                    )
                    break

            if not swapped:
                # No alternatives left in any swap category.
                break

        raise UniquenessError(
            f"Could not produce a unique build after {attempts} attempt(s); "
            "all alternative components exhausted."
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_swap(
        build: TowerBuild,
        category: ComponentCategory,
        replacement: ComponentSelection,
    ) -> TowerBuild:
        """Return a new build with one core component replaced.

        Args:
            build: The source build (not mutated).
            category: The component category to replace.
            replacement: The new :class:`ComponentSelection` to use.

        Returns:
            A new :class:`TowerBuild` with the swapped component.
        """
        # Map category enum to the corresponding TowerBuild field name.
        field_map: dict[ComponentCategory, str] = {
            ComponentCategory.CPU: "cpu",
            ComponentCategory.MOTHERBOARD: "motherboard",
            ComponentCategory.RAM: "ram",
            ComponentCategory.SSD: "ssd",
            ComponentCategory.PSU: "psu",
            ComponentCategory.CASE: "case",
        }
        field = field_map[category]
        return build.model_copy(update={field: replacement})
