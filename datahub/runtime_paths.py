from __future__ import annotations

import os
from pathlib import Path


def runtime_dir() -> Path:
    """Return the configurable directory used for generated runtime artifacts."""
    return Path(os.getenv("ADE_RUNTIME_DIR", "output"))


def runtime_path(*parts: str | Path) -> Path:
    """Build a path below the configured runtime directory."""
    return runtime_dir().joinpath(*parts)
