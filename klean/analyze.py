"""Stage 2 - Analyze: turn the scan index into proposed actions.

Deliberately rule-based and deterministic. Each rule explains itself in the
`reason` field and carries a confidence so review can auto-surface only the
uncertain calls. Default for anything no rule touches is KEEP.

The LLM layer (semantic grouping / folder naming) plugs in after this as an
optional enhancement; the safe core never needs it.
"""

from __future__ import annotations

import time
from pathlib import Path

from . import config
from .model import Action, Confidence, FileEntry, Plan, PlanItem


def _age_days(mtime: float, now: float) -> float:
    return (now - mtime) / 86400.0


def analyze(entries: list[FileEntry], created: str,
            now: float | None = None, organize: bool = False) -> Plan:
    now = now or time.time()
    plan = Plan(target=str(config.TARGET_DIR), created=created)

    # Index helpers for cross-file rules.
    by_sig: dict[str, list[FileEntry]] = {}
    dir_names = {e.name for e in entries if e.is_dir}
    for e in entries:
        by_sig.setdefault(e.signature, []).append(e)

    # Track which signature we've already chosen to keep, so later duplicates
    # in the same group get trashed.
    dup_keeper_seen: set[str] = set()

    for e in entries:
        item = PlanItem(file=e)

        # 1. System junk -- always safe.
        if e.name in config.JUNK_NAMES:
            _set(item, Action.TRASH, Confidence.HIGH, "system junk file")
            plan.items.append(item)
            continue

        # 2. Exact duplicate (same size + content prefix). Keep one, trash rest.
        # Empty files all share a signature, so never dedupe on size 0.
        group = by_sig[e.signature]
        if not e.is_dir and e.size > 0 and len(group) > 1:
            if e.signature not in dup_keeper_seen:
                dup_keeper_seen.add(e.signature)  # this one is the keeper
                _set(item, Action.KEEP, Confidence.HIGH,
                     f"original (kept); {len(group) - 1} duplicate(s) found")
            else:
                keeper = group[0].name
                _set(item, Action.TRASH, Confidence.HIGH,
                     f"duplicate of '{keeper}'")
                plan.items.append(item)
                continue

        # 3. Archive (.zip etc.) whose extracted folder is also present.
        if e.ext.lower() == ".zip" and Path(e.name).stem in dir_names:
            _set(item, Action.ARCHIVE, Confidence.MEDIUM,
                 f"redundant: extracted folder '{Path(e.name).stem}' exists",
                 dest=str(config.DEFAULT_ARCHIVE_DIR))
            plan.items.append(item)
            continue

        # 4. Old installers.
        if e.ext.lower() in config.INSTALLER_EXTS and \
                _age_days(e.mtime, now) > config.INSTALLER_AGE_DAYS:
            _set(item, Action.TRASH, Confidence.MEDIUM,
                 f"installer, {int(_age_days(e.mtime, now))}d old "
                 "(likely already installed)")
            plan.items.append(item)
            continue

        # 5. Screenshots -> organize into a Screenshots folder.
        if not e.is_dir and e.name.startswith(config.SCREENSHOT_PREFIXES):
            _set(item, Action.MOVE, Confidence.MEDIUM,
                 "screenshot", dest=str(config.TARGET_DIR / "Screenshots"))
            plan.items.append(item)
            continue

        # 6. Large + old + untouched -> archive candidate.
        if (not e.is_dir and e.size >= config.ARCHIVE_SIZE_BYTES
                and _age_days(e.mtime, now) > config.ARCHIVE_AGE_DAYS):
            _set(item, Action.ARCHIVE, Confidence.LOW,
                 f"large ({_mb(e.size)} MB) & untouched "
                 f"{int(_age_days(e.mtime, now))}d",
                 dest=str(config.DEFAULT_ARCHIVE_DIR))
            plan.items.append(item)
            continue

        # 7. Organization suggestion by file type (low confidence). Off by
        # default because it touches nearly every file; enable with --organize.
        folder = config.TYPE_FOLDERS.get(e.ftype)
        if organize and folder and not e.is_dir:
            _set(item, Action.MOVE, Confidence.LOW,
                 f"organize {e.ftype} files",
                 dest=str(config.TARGET_DIR / folder))
            plan.items.append(item)
            continue

        # Default: leave it alone.
        _set(item, Action.KEEP, Confidence.HIGH, "no rule matched")
        plan.items.append(item)

    return plan


def _set(item: PlanItem, action: Action, conf: Confidence,
         reason: str, dest: str | None = None) -> None:
    item.action = action
    item.confidence = conf
    item.reason = reason
    item.dest = dest
    # High-confidence, safe actions are pre-approved so a fast path can apply
    # them; everything else stays unapproved until a human says so in review.
    item.approved = action == Action.KEEP


def _mb(b: int) -> int:
    return round(b / (1024 * 1024))
