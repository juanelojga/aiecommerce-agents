"""Shared utilities for step-by-step workflow testing scripts.

Provides coloured terminal output, JSON file I/O for chaining steps,
and common CLI argument parsing helpers.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Output directory for inter-step JSON files.
OUTPUT_DIR = Path(__file__).resolve().parent / "output"


# ---------------------------------------------------------------------------
# Terminal colours (ANSI escape codes)
# ---------------------------------------------------------------------------

_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def print_header(text: str) -> None:
    """Print a bold cyan section header with surrounding lines.

    Args:
        text: Header text to display.
    """
    width = max(len(text) + 4, 60)
    line = "=" * width
    print(f"\n{_CYAN}{_BOLD}{line}{_RESET}")
    print(f"{_CYAN}{_BOLD}  {text}{_RESET}")
    print(f"{_CYAN}{_BOLD}{line}{_RESET}\n")


def print_subheader(text: str) -> None:
    """Print a yellow sub-header with a dashed underline.

    Args:
        text: Sub-header text to display.
    """
    print(f"\n{_YELLOW}{_BOLD}--- {text} ---{_RESET}\n")


def print_success(text: str) -> None:
    """Print a green success message with a checkmark.

    Args:
        text: Success message to display.
    """
    print(f"  {_GREEN}✔ {text}{_RESET}")


def print_error(text: str) -> None:
    """Print a red error message with an X mark.

    Args:
        text: Error message to display.
    """
    print(f"  {_RED}✘ {text}{_RESET}")


def print_warning(text: str) -> None:
    """Print a yellow warning message.

    Args:
        text: Warning message to display.
    """
    print(f"  {_YELLOW}⚠ {text}{_RESET}")


def print_info(text: str) -> None:
    """Print a dim informational message.

    Args:
        text: Info message to display.
    """
    print(f"  {_DIM}{text}{_RESET}")


def print_key_value(key: str, value: object, indent: int = 4) -> None:
    """Print a key-value pair with consistent formatting.

    Args:
        key: The label / key name.
        value: The value to display.
        indent: Number of leading spaces for alignment.
    """
    pad = " " * indent
    print(f"{pad}{_BOLD}{key}:{_RESET} {value}")


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    """Print a simple ASCII table.

    Args:
        headers: Column header strings.
        rows: List of row data (each row is a list of cell strings).
    """
    if not rows:
        print_info("(no data)")
        return

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(cell))

    sep = "  "
    header_line = sep.join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    divider = sep.join("-" * w for w in col_widths)

    print(f"    {_BOLD}{header_line}{_RESET}")
    print(f"    {divider}")
    for row in rows:
        cells = [(row[i] if i < len(row) else "").ljust(col_widths[i]) for i in range(len(headers))]
        print(f"    {sep.join(cells)}")


def print_json_preview(data: object, max_lines: int = 20) -> None:
    """Pretty-print a JSON-serialisable object, truncated if too long.

    Args:
        data: Data to serialise and display.
        max_lines: Maximum number of lines to display before truncating.
    """
    text = json.dumps(data, indent=2, default=str)
    lines = text.splitlines()
    for line in lines[:max_lines]:
        print(f"    {_DIM}{line}{_RESET}")
    if len(lines) > max_lines:
        print(f"    {_DIM}... ({len(lines) - max_lines} more lines){_RESET}")


# ---------------------------------------------------------------------------
# JSON I/O for inter-step chaining
# ---------------------------------------------------------------------------


def save_step_output(filename: str, data: Any) -> Path:
    """Save step output as a JSON file in the output directory.

    Args:
        filename: Name of the JSON file (e.g. ``"step1_inventory.json"``).
        data: JSON-serialisable data to persist.

    Returns:
        Full path to the saved file.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = OUTPUT_DIR / filename
    filepath.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print_success(f"Output saved → {filepath}")
    return filepath


def load_step_output(filename: str) -> Any:
    """Load a previously saved step output JSON file.

    Args:
        filename: Name of the JSON file to load.

    Returns:
        Parsed JSON data.

    Raises:
        SystemExit: If the file does not exist (with a helpful message).
    """
    filepath = OUTPUT_DIR / filename
    if not filepath.exists():
        print_error(f"Required input file not found: {filepath}")
        print_info(f"Run the previous step first to generate {filename}.")
        sys.exit(1)
    return json.loads(filepath.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Common CLI argument parsing
# ---------------------------------------------------------------------------


def build_base_parser(description: str) -> argparse.ArgumentParser:
    """Create an argument parser with common flags.

    Args:
        description: Script description for the help text.

    Returns:
        Pre-configured ``ArgumentParser`` with ``--tiers`` and ``--dry-run``.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--tiers",
        nargs="+",
        default=["Home", "Business", "Gaming"],
        choices=["Home", "Business", "Gaming"],
        help="Tiers to process (default: all three).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without calling external APIs.",
    )
    return parser


def print_step_summary(step_name: str, success_count: int, error_count: int) -> None:
    """Print a final step summary with counts.

    Args:
        step_name: Human-readable step name.
        success_count: Number of successful operations.
        error_count: Number of errors encountered.
    """
    print_subheader(f"{step_name} — Summary")
    print_key_value("Successes", success_count)
    print_key_value("Errors", error_count)
    if error_count == 0:
        print_success(f"{step_name} completed successfully!")
    else:
        print_warning(f"{step_name} completed with {error_count} error(s).")
