"""Optional LLM layer — semantic grouping of files into named folders.

This is the *only* part of Klean that can use an LLM, and it's strictly
additive: it upgrades some `keep` items into `move` suggestions with a
human-named destination folder. If no provider is available it does nothing and
the deterministic rules stand on their own.

Provider resolution (first available wins):
  1. Anthropic API   — if ANTHROPIC_API_KEY is set (raw HTTPS, no SDK dependency)
  2. system Claude   — if the `claude` CLI is on PATH
  3. none            — rules only

Model defaults to claude-opus-4-8; override with KLEAN_MODEL.
Everything fails soft: any error leaves the rule-based plan untouched.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.request

from . import config
from .model import Action, Confidence, Plan

DEFAULT_MODEL = os.environ.get("KLEAN_MODEL", "claude-opus-4-8")
API_URL = "https://api.anthropic.com/v1/messages"
MAX_FILES = 300  # cap names sent to the model in one pass


def provider() -> str | None:
    """Return the active provider: 'api', 'cli', or None."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "api"
    if shutil.which("claude"):
        return "cli"
    return None


def provider_label() -> str:
    p = provider()
    if p == "api":
        return f"Anthropic API ({DEFAULT_MODEL})"
    if p == "cli":
        return "system Claude CLI"
    return "none"


def _prompt(names: list[str]) -> str:
    listing = "\n".join(f"- {n}" for n in names)
    return (
        "You are organizing a cluttered desktop. Group the file names below "
        "into a small number of meaningful folders based on what each file "
        "appears to relate to (a project, topic, or purpose). Only group files "
        "that clearly belong together — leave unrelated one-off files out "
        "entirely. Give each group a short, filesystem-safe folder name (use "
        "only letters, numbers, spaces, and hyphens).\n\n"
        "Respond with ONLY a JSON object, no prose or markdown, shaped like:\n"
        '{"groups": [{"name": "Folder Name", "files": ["exact file name", ...]}]}\n\n'
        f"Files:\n{listing}"
    )


def _call_api(prompt: str) -> str:
    body = json.dumps({
        "model": DEFAULT_MODEL,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read())
    for block in data.get("content", []):
        if block.get("type") == "text":
            return block.get("text", "")
    return ""


def _call_cli(prompt: str) -> str:
    res = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True, text=True, timeout=180,
    )
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "claude CLI failed")
    return res.stdout


def _parse_groups(text: str) -> list[dict]:
    """Pull the {"groups": [...]} object out of the model's reply."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return []
    try:
        return json.loads(text[start:end + 1]).get("groups", [])
    except json.JSONDecodeError:
        return []


def _safe_folder(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9 _-]", "", name).strip()
    return name[:60]


def group_files(names: list[str]) -> tuple[list[dict], str | None]:
    """Return (groups, error). groups is [] when no provider or on failure."""
    p = provider()
    if not p:
        return [], "no provider (set ANTHROPIC_API_KEY or install the claude CLI)"
    try:
        text = _call_api(_prompt(names[:MAX_FILES])) if p == "api" \
            else _call_cli(_prompt(names[:MAX_FILES]))
    except Exception as exc:  # network, auth, parse, timeout — all fail soft
        return [], f"{p} error: {exc}"
    return _parse_groups(text), None


def enrich(plan: Plan, log=print) -> int:
    """Upgrade KEEP items into MOVE suggestions using LLM grouping.

    Returns the number of items newly assigned to a group. Only touches items
    the rules left as KEEP, so it never overrides a trash/archive decision.
    """
    cands = [it for it in plan.items
             if it.action == Action.KEEP and not it.file.is_dir]
    if not cands:
        return 0

    names = [it.file.name for it in cands]
    groups, err = group_files(names)
    if err:
        log(f"  smart grouping skipped: {err}")
        return 0
    if len(names) > MAX_FILES:
        log(f"  note: only the first {MAX_FILES} files were sent for grouping")

    by_name = {it.file.name: it for it in cands}
    assigned = 0
    for g in groups:
        folder = _safe_folder(g.get("name", ""))
        if not folder:
            continue
        for fn in g.get("files", []):
            it = by_name.get(fn)
            if it and it.action == Action.KEEP:
                it.action = Action.MOVE
                it.dest = str(config.TARGET_DIR / folder)
                it.group = folder
                it.reason = f"AI group: {folder}"
                it.confidence = Confidence.MEDIUM
                it.approved = False
                assigned += 1
    return assigned
