"""Stage 5 - Execute: apply approved actions and record an undo log.

Safety contract:
  * Only items with approved=True are touched.
  * "Delete" means MOVE to the quarantine holding-area, never unlink. The user
    empties quarantine manually when they are sure.
  * Every move is recorded src->dst in undo.json so the whole run reverses.
  * Name collisions at the destination are resolved by suffixing, never
    overwriting.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import config
from .model import Action, Plan, PlanItem


def _unique_dest(dest_dir: Path, name: str) -> Path:
    """Return a non-colliding path inside dest_dir for `name`."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    candidate = dest_dir / name
    if not candidate.exists():
        return candidate
    stem, suffix = Path(name).stem, Path(name).suffix
    i = 1
    while True:
        candidate = dest_dir / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def _destination(item: PlanItem, run_quarantine: Path) -> Path:
    if item.action == Action.TRASH:
        return _unique_dest(run_quarantine, item.file.name)
    # ARCHIVE / MOVE both carry an explicit dest directory.
    dest_dir = Path(item.dest).expanduser()
    return _unique_dest(dest_dir, item.file.name)


def apply_plan(plan: Plan, run_dir: Path) -> dict:
    """Execute every approved, non-KEEP item. Returns a summary dict."""
    run_quarantine = config.QUARANTINE_DIR / run_dir.name
    moves: list[dict] = []
    errors: list[dict] = []

    for item in plan.items:
        if item.action == Action.KEEP or not item.approved:
            continue
        src = Path(item.file.path)
        if not src.exists():
            errors.append({"file": str(src), "error": "no longer exists"})
            continue
        try:
            dst = _destination(item, run_quarantine)
            shutil.move(str(src), str(dst))
            moves.append({
                "action": item.action.value,
                "src": str(src),
                "dst": str(dst),
            })
        except OSError as exc:
            errors.append({"file": str(src), "error": str(exc)})

    undo_log = {"run": run_dir.name, "moves": moves, "errors": errors}
    (run_dir / "undo.json").write_text(json.dumps(undo_log, indent=2))
    return {
        "moved": len(moves),
        "errors": len(errors),
        "quarantine": str(run_quarantine),
    }
