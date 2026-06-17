"""Central configuration: paths, thresholds, and classification patterns.

Everything Klean writes lives under KLEAN_HOME (default ~/.klean) so the tool
never pollutes the directory it is cleaning. Each run gets its own folder so
plans, logs, and the quarantine holding-area are fully auditable and reversible.
"""

from __future__ import annotations

import os
from pathlib import Path

# --- Locations -------------------------------------------------------------

# The directory we clean. Override with KLEAN_TARGET for testing.
TARGET_DIR = Path(os.environ.get("KLEAN_TARGET", Path.home() / "Desktop"))

# Where Klean keeps its own state (plans, undo logs, quarantine).
KLEAN_HOME = Path(os.environ.get("KLEAN_HOME", Path.home() / ".klean"))
RUNS_DIR = KLEAN_HOME / "runs"

# "Deleted" files are moved here, never unlinked. The user empties it manually.
QUARANTINE_DIR = KLEAN_HOME / "quarantine"

# Default destination for the "archive / external memory" action. The actual
# destination is confirmed per-item during review and may be overridden.
DEFAULT_ARCHIVE_DIR = Path(
    os.environ.get("KLEAN_ARCHIVE", Path.home() / "Archive")
)

# --- Rule thresholds -------------------------------------------------------

# Files larger than this AND older than ARCHIVE_AGE_DAYS are archive candidates.
ARCHIVE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
ARCHIVE_AGE_DAYS = 180

# Installers older than this are trash candidates (low confidence, needs review).
INSTALLER_AGE_DAYS = 30

# Only the first 1 MB is hashed for the dup signature; combined with exact file
# size this is a strong, fast duplicate test that avoids reading huge videos in
# full. Bump if you have many distinct files sharing their first megabyte.
HASH_PREFIX_BYTES = 1 * 1024 * 1024

# --- Classification patterns ----------------------------------------------

# System cruft that is always safe to remove.
JUNK_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini", "Icon\r"}

INSTALLER_EXTS = {".dmg", ".pkg", ".exe", ".msi"}

SCREENSHOT_PREFIXES = ("Screenshot", "Screen Shot", "CleanShot", "Simulator Screenshot")

# File-type -> organize-into-folder name, used for the low-confidence
# "organization" suggestions.
TYPE_FOLDERS = {
    "image": "Images",
    "video": "Videos",
    "audio": "Audio",
    "document": "Documents",
    "archive": "Archives",
    "code": "Code",
    "data": "Data",
}

EXT_TO_TYPE = {
    # images
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
    ".webp": "image", ".heic": "image", ".tiff": "image", ".bmp": "image",
    ".svg": "image",
    # video
    ".mov": "video", ".mp4": "video", ".m4v": "video", ".avi": "video",
    ".mkv": "video", ".webm": "video",
    # audio
    ".mp3": "audio", ".wav": "audio", ".m4a": "audio", ".aac": "audio",
    ".flac": "audio",
    # documents
    ".pdf": "document", ".doc": "document", ".docx": "document",
    ".xls": "data", ".xlsx": "data", ".csv": "data", ".tsv": "data",
    ".ppt": "document", ".pptx": "document", ".pages": "document",
    ".key": "document", ".numbers": "data", ".txt": "document",
    ".md": "document", ".rtf": "document",
    # archives
    ".zip": "archive", ".tar": "archive", ".gz": "archive", ".tgz": "archive",
    ".rar": "archive", ".7z": "archive", ".dmg": "archive",
    # code
    ".py": "code", ".js": "code", ".ts": "code", ".json": "data",
    ".html": "code", ".css": "code", ".sh": "code",
}


def type_for_ext(ext: str) -> str:
    return EXT_TO_TYPE.get(ext.lower(), "other")
