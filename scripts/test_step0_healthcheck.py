#!/usr/bin/env python3
"""Step 0 — Environment Health Check.

Validates that all prerequisites are in place before running the workflow:
  1. Environment variables are loaded (critical API keys present).
  2. PostgreSQL database is reachable and tables can be created.
  3. AIEcommerce API responds to a lightweight product listing call.

Usage:
    uv run python scripts/test_step0_healthcheck.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure the project root is on sys.path so ``orchestrator`` is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from _test_utils import (
    print_error,
    print_header,
    print_info,
    print_key_value,
    print_subheader,
    print_success,
    print_warning,
)


async def _check_env() -> bool:
    """Verify that required environment variables are set.

    Returns:
        ``True`` if all critical variables are present.
    """
    from orchestrator.core.config import get_settings

    print_subheader("1. Environment Variables")

    settings = get_settings()

    def _mask(val: str) -> str:
        return "***" if val else "(empty)"

    checks: list[tuple[str, str, bool]] = [
        ("DATABASE_URL", settings.DATABASE_URL, bool(settings.DATABASE_URL)),
        (
            "AIECOMMERCE_API_URL",
            settings.AIECOMMERCE_API_URL,
            bool(settings.AIECOMMERCE_API_URL),
        ),
        (
            "AIECOMMERCE_API_KEY",
            _mask(settings.AIECOMMERCE_API_KEY),
            bool(settings.AIECOMMERCE_API_KEY),
        ),
        ("API_KEY", _mask(settings.API_KEY), bool(settings.API_KEY)),
        (
            "GOOGLE_API_KEY",
            _mask(settings.GOOGLE_API_KEY),
            bool(settings.GOOGLE_API_KEY),
        ),
        (
            "MERCADOLIBRE_ACCESS_TOKEN",
            _mask(settings.MERCADOLIBRE_ACCESS_TOKEN),
            bool(settings.MERCADOLIBRE_ACCESS_TOKEN),
        ),
    ]

    all_ok = True
    for name, display_value, is_set in checks:
        if is_set:
            print_success(f"{name} = {display_value}")
        else:
            print_warning(f"{name} = {display_value}  (not set — may be needed later)")
            # Only fail for truly critical vars
            if name in ("DATABASE_URL", "AIECOMMERCE_API_URL", "AIECOMMERCE_API_KEY"):
                all_ok = False

    # Show non-critical config
    print_info(f"APP_NAME = {settings.APP_NAME}")
    print_info(f"DEBUG = {settings.DEBUG}")
    print_info(f"ASSEMBLY_MARGIN_PERCENT = {settings.ASSEMBLY_MARGIN_PERCENT}%")
    print_info(f"ML_FEE_PERCENT = {settings.ML_FEE_PERCENT}%")

    return all_ok


async def _check_database() -> bool:
    """Verify that the database is reachable and tables are created.

    Returns:
        ``True`` if the database connection and table creation succeed.
    """
    print_subheader("2. Database Connection")

    try:
        from orchestrator.core.database import create_tables, engine

        # Test the raw connection
        async with engine.connect() as conn:
            result = await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            row = result.scalar()
            if row == 1:
                print_success("Database connection successful (SELECT 1 = OK)")
            else:
                print_error(f"Unexpected result from SELECT 1: {row}")
                return False

        # Create tables (idempotent)
        await create_tables()
        print_success("Database tables created / verified")
        return True

    except Exception as exc:
        print_error(f"Database connection failed: {exc}")
        print_info("Make sure PostgreSQL is running: docker compose up -d db")
        return False


async def _check_api() -> bool:
    """Verify that the AIEcommerce API is reachable.

    Makes a lightweight ``list_products`` call for a single category
    to confirm connectivity.

    Returns:
        ``True`` if the API responds successfully.
    """
    print_subheader("3. AIEcommerce API Connection")

    try:
        from orchestrator.core.config import get_settings
        from orchestrator.schemas.product import ComponentCategory
        from orchestrator.services.aiecommerce import AIEcommerceClient

        settings = get_settings()
        client = AIEcommerceClient(settings)

        print_info(f"Connecting to {settings.AIECOMMERCE_API_URL} ...")
        response = await client.list_products(
            category=ComponentCategory.CPU,
            active_only=True,
            has_stock=True,
        )
        count = len(response.results)
        print_success(f"API responded — {response.count} total CPUs, {count} in page")

        if count > 0:
            sample = response.results[0]
            label = f"{sample.sku} — {sample.normalized_name} (${sample.price:.2f})"
            print_key_value("Sample product", label)
        return True

    except Exception as exc:
        print_error(f"API connection failed: {exc}")
        print_info("Check AIECOMMERCE_API_URL and AIECOMMERCE_API_KEY in .env")
        return False


async def main() -> None:
    """Run all health checks and report results."""
    print_header("Step 0 — Environment Health Check")

    results: dict[str, bool] = {}

    results["env"] = await _check_env()
    results["database"] = await _check_database()
    results["api"] = await _check_api()

    # Final summary
    print_subheader("Results")
    all_passed = True
    for name, passed in results.items():
        if passed:
            print_success(f"{name.upper()}: PASS")
        else:
            print_error(f"{name.upper()}: FAIL")
            all_passed = False

    if all_passed:
        print_success("\nAll checks passed! You are ready to run the workflow steps.")
    else:
        print_error("\nSome checks failed. Fix the issues above before proceeding.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
