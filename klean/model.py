"""Data model for the scan index and the review plan.

The plan is the single source of truth that travels Scan -> Review -> Apply.
It serializes to plain JSON so a human can open it, eyeball it, and even hand-
edit an action before applying. Nothing here touches the filesystem.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path


class Action(str, Enum):
    KEEP = "keep"          # leave it where it is
    TRASH = "trash"        # move to quarantine (reversible "delete")
    ARCHIVE = "archive"    # move to external memory / archive destination
    MOVE = "move"          # organize into a subfolder of the target dir


class Confidence(str, Enum):
    HIGH = "high"      # mechanical & safe (junk, exact duplicate)
    MEDIUM = "medium"  # strong heuristic, glance before applying
    LOW = "low"        # suggestion only (organization, age-based archive)


@dataclass
class FileEntry:
    """A single scanned file with the metadata the rules need."""
    path: str            # absolute path
    name: str
    size: int
    mtime: float         # epoch seconds, last modified
    ext: str
    ftype: str           # image/video/document/... from config.type_for_ext
    is_dir: bool
    signature: str       # size + partial-content hash, for dup detection


@dataclass
class PlanItem:
    """A proposed action for one file. `approved` gates whether apply acts."""
    file: FileEntry
    action: Action = Action.KEEP
    dest: str | None = None        # for ARCHIVE/MOVE: destination directory
    reason: str = ""
    confidence: Confidence = Confidence.LOW
    group: str | None = None       # optional semantic grouping label
    approved: bool = False         # set during review; apply only acts if True

    def to_dict(self) -> dict:
        d = asdict(self)
        d["action"] = self.action.value
        d["confidence"] = self.confidence.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PlanItem":
        return cls(
            file=FileEntry(**d["file"]),
            action=Action(d["action"]),
            dest=d.get("dest"),
            reason=d.get("reason", ""),
            confidence=Confidence(d.get("confidence", "low")),
            group=d.get("group"),
            approved=d.get("approved", False),
        )


@dataclass
class Plan:
    """The full set of proposed actions for one scan of the target dir."""
    target: str
    created: str                          # ISO timestamp (set by caller)
    items: list[PlanItem] = field(default_factory=list)
    reviewed: bool = False

    def to_json(self) -> str:
        return json.dumps(
            {
                "target": self.target,
                "created": self.created,
                "reviewed": self.reviewed,
                "items": [it.to_dict() for it in self.items],
            },
            indent=2,
        )

    @classmethod
    def load(cls, path: Path) -> "Plan":
        d = json.loads(Path(path).read_text())
        plan = cls(target=d["target"], created=d["created"],
                   reviewed=d.get("reviewed", False))
        plan.items = [PlanItem.from_dict(i) for i in d["items"]]
        return plan

    def save(self, path: Path) -> None:
        Path(path).write_text(self.to_json())

    # --- convenience views -------------------------------------------------

    def by_action(self, action: Action) -> list[PlanItem]:
        return [it for it in self.items if it.action == action]

    def actionable(self) -> list[PlanItem]:
        return [it for it in self.items if it.action != Action.KEEP]
