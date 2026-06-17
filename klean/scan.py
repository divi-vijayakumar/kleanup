"""Stage 1 - Scan: walk the target directory and build a metadata index.

Pure observation. Reads file stats and a cheap content signature; never writes,
moves, or deletes anything.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from . import config
from .model import FileEntry


def _signature(path: Path, size: int, is_dir: bool) -> str:
    """A fast, strong-enough fingerprint for duplicate detection.

    Combines the exact size with a hash of the first HASH_PREFIX_BYTES so we
    don't read multi-hundred-MB videos in full. Two files matching on both are
    treated as duplicates. Directories get a size-only signature (never
    deduped against files).
    """
    if is_dir:
        return f"dir:{path.name}"
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            h.update(f.read(config.HASH_PREFIX_BYTES))
    except OSError:
        return f"size:{size}:unreadable"
    return f"{size}:{h.hexdigest()}"


def scan(target: Path | None = None) -> list[FileEntry]:
    """Return one FileEntry per top-level item in the target directory.

    Top-level only: we classify whole folders as units rather than recursing,
    which is the right granularity for desktop tidying.
    """
    target = Path(target or config.TARGET_DIR).expanduser()
    entries: list[FileEntry] = []

    for p in sorted(target.iterdir()):
        # Skip the macOS folder-settings sentinel except real junk we target.
        name = p.name
        if name == ".localized":
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        is_dir = p.is_dir()
        ext = "" if is_dir else p.suffix
        size = _dir_size(p) if is_dir else st.st_size
        entries.append(
            FileEntry(
                path=str(p),
                name=name,
                size=size,
                mtime=st.st_mtime,
                ext=ext,
                ftype="folder" if is_dir else config.type_for_ext(ext),
                is_dir=is_dir,
                signature=_signature(p, size, is_dir),
            )
        )
    return entries


def _dir_size(path: Path) -> int:
    """Best-effort recursive size of a directory (for reporting only)."""
    total = 0
    try:
        for child in path.rglob("*"):
            try:
                if child.is_file():
                    total += child.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return total
