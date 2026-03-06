"""Tests for the ListingContentGenerator service."""

from orchestrator.services.listing_content import ListingContentGenerator

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_GENERATOR = ListingContentGenerator()

# Standard tower build dict (Gaming tier with GPU).
_GAMING_BUILD: dict[str, object] = {
    "tier": "Gaming",
    "cpu": {"normalized_name": "Intel Core i7-13700K"},
    "motherboard": {"normalized_name": "ASUS ROG Strix Z790-E"},
    "ram": {"normalized_name": "Corsair 32GB DDR5"},
    "gpu": {"normalized_name": "NVIDIA RTX 4080"},
    "ssd": {"normalized_name": "Samsung 990 Pro 2TB"},
    "psu": {"normalized_name": "Corsair RM850x"},
    "case": {"normalized_name": "NZXT H510"},
}

# Home tier build without a GPU.
_HOME_BUILD: dict[str, object] = {
    "tier": "Home",
    "cpu": {"normalized_name": "AMD Ryzen 5 5600X"},
    "motherboard": {"normalized_name": "MSI B550 Tomahawk"},
    "ram": {"normalized_name": "Kingston 16GB DDR4"},
    "gpu": None,
    "ssd": {"normalized_name": "WD Blue 1TB"},
    "psu": {"normalized_name": "EVGA 650W"},
    "case": {"normalized_name": "Fractal Design Pop Air"},
}

# Bundle dict with peripherals.
_BUNDLE: dict[str, object] = {
    "tier": "Gaming",
    "tower_hash": "abc123",
    "bundle_id": "bundle-xyz",
    "peripherals": [
        {"normalized_name": "LG 27GP850-B 27 QHD", "category": "monitor"},
        {"normalized_name": "Logitech G Pro X", "category": "keyboard"},
        {"normalized_name": "Logitech G502 X", "category": "mouse"},
    ],
}

# Build with very long component names to force title truncation.
_LONG_NAME_BUILD: dict[str, object] = {
    "tier": "Business",
    "cpu": {"normalized_name": "AMD Ryzen Threadripper Pro 5975WX 32-Core"},
    "motherboard": {"normalized_name": "ASUS Pro WS WRX80E-SAGE SE WIFI"},
    "ram": {"normalized_name": "Corsair 128GB DDR4 ECC Registered"},
    "gpu": {"normalized_name": "NVIDIA Quadro RTX A6000 48GB GDDR6"},
    "ssd": {"normalized_name": "Samsung 990 Pro 2TB NVMe"},
    "psu": {"normalized_name": "Seasonic Prime TX-1000"},
    "case": {"normalized_name": "Fractal Design Define 7 XL"},
}


# ---------------------------------------------------------------------------
# Tests: _extract_short_name
# ---------------------------------------------------------------------------


class TestExtractShortName:
    """Tests for _extract_short_name."""

    def test_extract_short_name(self) -> None:
        """Drops first token (brand) when name has three or more words."""
        component = {"normalized_name": "Intel Core i7-13700K"}
        assert _GENERATOR._extract_short_name(component) == "Core i7-13700K"

    def test_extract_short_name_two_words(self) -> None:
        """Returns full name unchanged when it has fewer than three words."""
        component = {"normalized_name": "RTX 4080"}
        assert _GENERATOR._extract_short_name(component) == "RTX 4080"

    def test_extract_short_name_single_word(self) -> None:
        """Returns the single word unchanged."""
        component = {"normalized_name": "i7"}
        assert _GENERATOR._extract_short_name(component) == "i7"

    def test_extract_short_name_empty_dict(self) -> None:
        """Returns empty string when normalized_name is absent."""
        assert _GENERATOR._extract_short_name({}) == ""

    def test_extract_short_name_corsair_ram(self) -> None:
        """Drops brand 'Corsair' from a RAM name."""
        component = {"normalized_name": "Corsair 32GB DDR5"}
        assert _GENERATOR._extract_short_name(component) == "32GB DDR5"


# ---------------------------------------------------------------------------
# Tests: generate_title
# ---------------------------------------------------------------------------


class TestGenerateTitleTowerOnly:
    """Tests for generate_title without a bundle."""

    def test_generate_title_tower_only(self) -> None:
        """Tower title has 'PC' prefix (not 'Kit') and is ≤ 60 chars."""
        title = _GENERATOR.generate_title(_GAMING_BUILD)
        assert title.startswith("PC ")
        assert not title.startswith("Kit")
        assert len(title) <= 60

    def test_generate_title_bundle(self) -> None:
        """Bundle title starts with 'Kit PC' prefix."""
        title = _GENERATOR.generate_title(_GAMING_BUILD, _BUNDLE)
        assert title.startswith("Kit PC ")
        assert len(title) <= 60

    def test_generate_title_truncation(self) -> None:
        """Title is truncated to exactly 60 chars when content is too long."""
        title = _GENERATOR.generate_title(_LONG_NAME_BUILD)
        assert len(title) <= 60

    def test_generate_title_gaming_tier(self) -> None:
        """Gaming tier title includes GPU short name."""
        title = _GENERATOR.generate_title(_GAMING_BUILD)
        assert "Gaming" in title
        assert "RTX 4080" in title

    def test_generate_title_home_tier_no_gpu(self) -> None:
        """Home tier title omits GPU segment when build has no GPU."""
        title = _GENERATOR.generate_title(_HOME_BUILD)
        assert "Home" in title
        # No GPU in _HOME_BUILD; ensure the title still forms correctly.
        assert len(title) <= 60
        # GPU placeholder should not appear in the title.
        assert "RTX" not in title

    def test_generate_title_includes_tier(self) -> None:
        """Title contains the tier name."""
        title = _GENERATOR.generate_title(_GAMING_BUILD)
        assert "Gaming" in title

    def test_generate_title_includes_cpu_and_ram(self) -> None:
        """Title contains at minimum CPU and RAM short names."""
        title = _GENERATOR.generate_title(_GAMING_BUILD)
        # CPU short name: "Core i7-13700K"
        assert "i7-13700K" in title or "Core" in title
        # RAM short name: "32GB DDR5"
        assert "32GB" in title or "DDR5" in title


# ---------------------------------------------------------------------------
# Tests: generate_description
# ---------------------------------------------------------------------------


class TestGenerateDescription:
    """Tests for generate_description."""

    def test_generate_description_includes_components(self) -> None:
        """Description lists all present component specifications."""
        desc = _GENERATOR.generate_description(_GAMING_BUILD)
        assert "CPU" in desc
        assert "RAM" in desc
        assert "Intel Core i7-13700K" in desc
        assert "Corsair 32GB DDR5" in desc
        assert "NVIDIA RTX 4080" in desc

    def test_generate_description_includes_peripherals(self) -> None:
        """Bundle description includes a peripherals section."""
        desc = _GENERATOR.generate_description(_GAMING_BUILD, _BUNDLE)
        # Peripherals section header should be present.
        assert "Periférico" in desc
        # Each peripheral's normalized_name should appear.
        assert "LG 27GP850-B 27 QHD" in desc
        assert "Logitech G Pro X" in desc
        assert "Logitech G502 X" in desc

    def test_generate_description_no_bundle(self) -> None:
        """Tower-only description excludes the peripherals section."""
        desc = _GENERATOR.generate_description(_GAMING_BUILD)
        # Should NOT contain a peripherals section.
        assert "Periférico" not in desc

    def test_generate_description_includes_footer(self) -> None:
        """Description ends with the standard footer text."""
        desc = _GENERATOR.generate_description(_GAMING_BUILD)
        # Footer should contain assembly/warranty wording.
        assert "garantía" in desc.lower() or "armado" in desc.lower()

    def test_generate_description_all_component_roles(self) -> None:
        """Description includes every non-None component role."""
        desc = _GENERATOR.generate_description(_GAMING_BUILD)
        for role in ("CPU", "MOTHERBOARD", "RAM", "GPU", "SSD", "PSU", "CASE"):
            assert role in desc

    def test_generate_description_skips_none_components(self) -> None:
        """Components that are None are not listed in the description."""
        desc = _GENERATOR.generate_description(_HOME_BUILD)
        # _HOME_BUILD has gpu=None, so GPU should not appear.
        assert "GPU" not in desc
