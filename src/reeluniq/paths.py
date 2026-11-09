"""Where the program keeps its working files, per platform (stdlib only)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def app_dir() -> Path:
    """The per-user folder of the program; not created here."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "reeluniq"


def data_dir() -> Path:
    """Uploads and results of the local web page; created on first use."""
    d = app_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d
