from __future__ import annotations

from pathlib import Path


def source_checkout_root() -> Path:
    """Return the repository root when running from a source checkout."""
    return Path(__file__).resolve().parents[2]


def factors_root() -> Path:
    return source_checkout_root() / "factors"


def templates_root() -> Path:
    return source_checkout_root() / "templates"
