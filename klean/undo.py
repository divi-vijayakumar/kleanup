"""Stage 6 - Undo: reverse a run by moving every file back to its origin.

Reads the run's undo.json and walks the moves in reverse. Restores only when
the original location is free; otherwise reports a conflict rather than
clobbering whatever now sits there.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path


def undo_run(run_dir: Path) -> dict:
    log_path = run_dir / "undo.json"
    if not log_path.exists():
        return {"restored": 0, "errors": [f"no undo log in {run_dir}"]}

    log = json.loads(log_path.read_text())
    restored = 0
    errors: list[str] = []

    # Reverse order so suffixed collision-renames unwind cleanly.
    for move in reversed(log.get("moves", [])):
        src, dst = Path(move["src"]), Path(move["dst"])
        if not dst.exists():
            errors.append(f"missing (already gone?): {dst}")
            continue
        if src.exists():
            errors.append(f"original path occupied, skipped: {src}")
            continue
        try:
            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(src))
            restored += 1
            # Remove the destination dir if we just emptied it (e.g. a
            # Screenshots/ folder Klean created during apply).
            try:
                dst.parent.rmdir()
            except OSError:
                pass  # not empty or still needed — leave it
        except OSError as exc:
            errors.append(f"{dst}: {exc}")

    return {"restored": restored, "errors": errors}
