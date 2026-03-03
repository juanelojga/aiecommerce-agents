"""Smoke test to verify the project scaffolding works."""

from main import main


def test_main_runs(capsys: object) -> None:
    """Verify that main() executes without errors."""
    main()
