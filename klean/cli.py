"""Klean command-line interface.

    klean scan       walk the Desktop, propose a plan (nothing is touched)
    klean review     interactively approve / adjust the proposed actions
    klean apply      execute only the approved actions, with an undo log
    klean undo       reverse the last run
    klean status     show recent runs

Workflow: scan -> review -> apply. Undo is always available afterwards.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import config, report
from .analyze import analyze
from .execute import apply_plan
from .model import Action, Confidence, Plan
from .scan import scan as scan_dir
from .undo import undo_run


# --- run-dir helpers -------------------------------------------------------

def _new_run_dir() -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    d = config.RUNS_DIR / ts
    d.mkdir(parents=True, exist_ok=True)
    return d


def _latest_run() -> Path | None:
    if not config.RUNS_DIR.exists():
        return None
    runs = sorted(p for p in config.RUNS_DIR.iterdir() if p.is_dir())
    return runs[-1] if runs else None


def _resolve_run(arg: str | None) -> Path | None:
    if arg:
        d = config.RUNS_DIR / arg
        return d if d.exists() else None
    return _latest_run()


# --- commands --------------------------------------------------------------

def _build_plan(args):
    """Scan + analyze (+ optional smart grouping) → a saved plan in a run dir."""
    target = Path(args.target).expanduser() if args.target else config.TARGET_DIR
    print(f"Scanning {target} …")
    entries = scan_dir(target)
    plan = analyze(entries, created=datetime.now().isoformat(),
                   organize=args.organize)
    if getattr(args, "smart", False):
        _maybe_smart(plan)
    run_dir = _new_run_dir()
    plan.save(run_dir / "plan.json")
    (run_dir / "report.txt").write_text(report.summary(plan))
    return plan, run_dir


def _maybe_smart(plan) -> None:
    from . import smart
    p = smart.provider()
    if not p:
        print("  --smart: no LLM provider found "
              "(set ANTHROPIC_API_KEY or install the `claude` CLI); using rules only.")
        return
    print(f"  Smart grouping via {smart.provider_label()} …")
    n = smart.enrich(plan)
    print(f"  AI proposed grouping for {n} file(s).")


def cmd_scan(args) -> int:
    plan, run_dir = _build_plan(args)
    print(report.summary(plan))
    print(f"Plan saved to {run_dir / 'plan.json'}")
    print("Next:  klean review   (then  klean apply)")
    return 0


def cmd_ui(args) -> int:
    plan, run_dir = _build_plan(args)
    print(report.summary(plan))
    from . import ui
    ui.serve(run_dir / "plan.json", Path(plan.target).expanduser(), run_dir,
             open_browser=not args.no_browser)
    return 0


def cmd_review(args) -> int:
    run_dir = _resolve_run(args.run)
    if not run_dir:
        print("No scan found. Run `klean scan` first.", file=sys.stderr)
        return 1
    plan = Plan.load(run_dir / "plan.json")
    actionable = plan.actionable()
    if not actionable:
        print("Nothing proposed — Desktop looks clean.")
        return 0

    print(report.summary(plan))

    if args.approve_high:
        n = 0
        for it in actionable:
            if it.confidence == Confidence.HIGH:
                it.approved = True
                n += 1
        plan.reviewed = True
        plan.save(run_dir / "plan.json")
        print(f"Auto-approved {n} high-confidence action(s). "
              "Review the rest or run `klean apply`.")
        return 0

    # Default: open the visual review UI (the terminal summary above stays
    # visible). Use --terminal to approve entirely in the terminal instead.
    if not args.terminal:
        from . import ui
        ui.serve(run_dir / "plan.json",
                 Path(plan.target).expanduser(),
                 run_dir,
                 open_browser=not args.no_browser)
        approved = sum(1 for it in Plan.load(run_dir / "plan.json").items
                       if it.approved and it.action != Action.KEEP)
        print(f"{approved} action(s) approved. Run `klean apply`.")
        return 0

    print("\nReview each group. [a]pprove all · [n]one · [i]ndividually · [s]kip\n")
    for action in (Action.TRASH, Action.ARCHIVE, Action.MOVE):
        group = plan.by_action(action)
        if not group:
            continue
        choice = _ask(f"{action.value.upper()} — {len(group)} item(s). "
                      "[a]ll / [n]one / [i]ndividually / [s]kip: ",
                      ["a", "n", "i", "s"], default="i")
        if choice == "s":
            continue
        if choice == "a":
            for it in group:
                it.approved = True
        elif choice == "n":
            for it in group:
                it.approved = False
        else:  # individually
            for it in group:
                _review_one(it, action)

    plan.reviewed = True
    plan.save(run_dir / "plan.json")
    approved = sum(1 for it in plan.items if it.approved and it.action != Action.KEEP)
    print(f"\nReviewed. {approved} action(s) approved. Run `klean apply`.")
    return 0


def _review_one(it, action) -> None:
    dest = f"  ->  {it.dest}" if it.dest else ""
    print(f"\n  {it.file.name}  ({report._mb(it.file.size)} MB)")
    print(f"  {it.reason}{dest}")
    if action == Action.ARCHIVE:
        c = _ask("  [y]es archive / [d]estination / [n]o: ", ["y", "d", "n"], "n")
        if c == "d":
            new = input("    destination dir: ").strip()
            if new:
                it.dest = str(Path(new).expanduser())
            it.approved = True
        else:
            it.approved = c == "y"
    else:
        c = _ask("  [y]es / [n]o: ", ["y", "n"], "n")
        it.approved = c == "y"


def cmd_apply(args) -> int:
    run_dir = _resolve_run(args.run)
    if not run_dir:
        print("No scan found. Run `klean scan` first.", file=sys.stderr)
        return 1
    plan = Plan.load(run_dir / "plan.json")
    approved = [it for it in plan.items
                if it.approved and it.action != Action.KEEP]
    if not approved:
        print("No approved actions. Run `klean review` first.", file=sys.stderr)
        return 1

    print(f"Applying {len(approved)} approved action(s):")
    for it in approved:
        print(f"  {it.action.value:<8} {it.file.name}")
    if not args.yes:
        if _ask("\nProceed? [y/N]: ", ["y", "n"], "n") != "y":
            print("Aborted.")
            return 0

    result = apply_plan(plan, run_dir)
    print(f"\nMoved {result['moved']} item(s). Errors: {result['errors']}.")
    print(f"Trashed files are quarantined in {result['quarantine']}")
    print("Undo anytime with `klean undo`.")
    return 0


def cmd_undo(args) -> int:
    run_dir = _resolve_run(args.run)
    if not run_dir:
        print("No run to undo.", file=sys.stderr)
        return 1
    result = undo_run(run_dir)
    print(f"Restored {result['restored']} item(s).")
    for err in result["errors"]:
        print(f"  ! {err}")
    return 0


def cmd_status(args) -> int:
    if not config.RUNS_DIR.exists():
        print("No runs yet. Start with `klean scan`.")
        return 0
    runs = sorted(p for p in config.RUNS_DIR.iterdir() if p.is_dir())
    if not runs:
        print("No runs yet. Start with `klean scan`.")
        return 0
    print(f"{len(runs)} run(s) under {config.RUNS_DIR}:\n")
    for r in runs[-10:]:
        plan_p = r / "plan.json"
        applied = (r / "undo.json").exists()
        tag = "applied" if applied else "pending"
        n = len(Plan.load(plan_p).actionable()) if plan_p.exists() else 0
        print(f"  {r.name}   {n} proposed   [{tag}]")
    return 0


# --- argument parsing ------------------------------------------------------

def _ask(prompt: str, choices: list[str], default: str) -> str:
    try:
        raw = input(prompt).strip().lower()
    except EOFError:
        return default
    return raw if raw in choices else default


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="klean",
                                description="Review-then-act Desktop cleaner.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="propose a cleanup plan (no changes)")
    s.add_argument("--target", help="directory to scan (default: ~/Desktop)")
    s.add_argument("--organize", action="store_true",
                   help="also propose moving every file into type folders")
    s.add_argument("--smart", action="store_true",
                   help="use an LLM to group related files into named folders")
    s.set_defaults(func=cmd_scan)

    w = sub.add_parser("ui", help="scan and open the web review/apply UI")
    w.add_argument("--target", help="directory to scan (default: ~/Desktop)")
    w.add_argument("--organize", action="store_true",
                   help="also propose moving every file into type folders")
    w.add_argument("--smart", action="store_true",
                   help="use an LLM to group related files into named folders")
    w.add_argument("--no-browser", action="store_true",
                   help="start the UI server but don't auto-open the browser")
    w.set_defaults(func=cmd_ui)

    r = sub.add_parser("review", help="approve/adjust proposed actions")
    r.add_argument("--run", help="run id (default: latest)")
    r.add_argument("--approve-high", action="store_true",
                   help="auto-approve high-confidence actions, no prompts")
    r.add_argument("--terminal", action="store_true",
                   help="review in the terminal instead of the web UI")
    r.add_argument("--no-browser", action="store_true",
                   help="start the review UI but don't auto-open the browser")
    r.set_defaults(func=cmd_review)

    a = sub.add_parser("apply", help="execute approved actions")
    a.add_argument("--run", help="run id (default: latest)")
    a.add_argument("--yes", action="store_true", help="skip confirmation")
    a.set_defaults(func=cmd_apply)

    u = sub.add_parser("undo", help="reverse a run")
    u.add_argument("--run", help="run id (default: latest)")
    u.set_defaults(func=cmd_undo)

    st = sub.add_parser("status", help="show recent runs")
    st.set_defaults(func=cmd_status)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
