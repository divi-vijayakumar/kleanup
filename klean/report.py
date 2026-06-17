"""Human-readable summary of a plan, for the review surface.

Prints a grouped, color-free table to the terminal so the proposed actions are
scannable at a glance before anything is applied.
"""

from __future__ import annotations

from .model import Action, Plan, PlanItem

_ICON = {
    Action.KEEP: "  ",
    Action.TRASH: "🗑 ",
    Action.ARCHIVE: "📦",
    Action.MOVE: "📁",
}

_ORDER = [Action.TRASH, Action.ARCHIVE, Action.MOVE, Action.KEEP]


def _mb(b: int) -> float:
    return round(b / (1024 * 1024), 1)


def summary(plan: Plan) -> str:
    lines: list[str] = []
    total = len(plan.items)
    freed = sum(it.file.size for it in plan.items
                if it.action in (Action.TRASH, Action.ARCHIVE))
    lines.append(f"\nScan of {plan.target}")
    lines.append(f"{total} items · "
                 f"{_mb(freed)} MB would leave the Desktop\n")

    for action in _ORDER:
        items = plan.by_action(action)
        if not items:
            continue
        approved = sum(1 for it in items if it.approved)
        head = f"{_ICON[action]} {action.value.upper()}  ({len(items)}"
        if action != Action.KEEP:
            head += f", {approved} approved"
        head += ")"
        lines.append(head)
        if action == Action.KEEP:
            lines.append(f"    … {len(items)} files left in place\n")
            continue
        for it in _sorted(items):
            lines.append(_row(it))
        lines.append("")
    return "\n".join(lines)


def _sorted(items: list[PlanItem]) -> list[PlanItem]:
    # Biggest first within a group -- the high-impact items lead.
    return sorted(items, key=lambda it: -it.file.size)


def _row(it: PlanItem) -> str:
    name = it.file.name
    if len(name) > 42:
        name = name[:39] + "…"
    size = f"{_mb(it.file.size):>7} MB"
    mark = "✓" if it.approved else "·"
    conf = it.confidence.value[0].upper()
    dest = ""
    if it.dest:
        from pathlib import Path
        dest = f"  →  {Path(it.dest).name}/"
    return f"  {mark} [{conf}] {name:<43}{size}  {it.reason}{dest}"
