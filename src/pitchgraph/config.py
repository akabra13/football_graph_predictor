"""Where data lives. By default: nowhere on this machine.

The project stores no data locally unless told to. Set PITCHGRAPH_DATA to a
directory to persist data there:

    Colab:  /content/drive/MyDrive/pitchgraph   (Google Drive, the normal home)
    USB:    E:/pitchgraph                        (later, if wanted)

With PITCHGRAPH_DATA unset, downloads are held in memory for the life of the
process and never written to disk, and anything that needs the Parquet lake
refuses to run rather than silently writing one to the laptop.
"""

from __future__ import annotations

import os
from pathlib import Path

DATA_ENV = "PITCHGRAPH_DATA"


def data_root() -> Path | None:
    """The configured data directory, or None for memory-only operation."""
    raw = os.environ.get(DATA_ENV, "").strip()
    return Path(raw).expanduser() if raw else None


def require_data_root() -> Path:
    """Data directory for work that must persist (the lake, reports)."""
    root = data_root()
    if root is None:
        raise RuntimeError(
            f"{DATA_ENV} is not set, and this project does not store data on the "
            "local machine by default. Run this in Colab with Google Drive mounted "
            f"(the notebook sets {DATA_ENV}), or point it at a USB drive."
        )
    return root


def lake_dir() -> Path:
    return require_data_root() / "lake"
