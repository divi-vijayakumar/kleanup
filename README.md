# Klean

A safe, **review-then-act** cleaner for a cluttered Desktop (or any folder).

Klean never deletes or moves anything on its own. It *proposes* a plan, you
review it, and only your **approved** actions are applied — always with an
undo log.

```
scan  ──▶  review  ──▶  apply  ──▶  (undo)
proposes   you approve   executes    reverses
nothing    / adjust      approved    any run
touched                  only
```

## Why it's safe

- **Nothing is ever permanently deleted.** "Trash" means *move to a quarantine
  holding-area* under `~/.klean/quarantine`. You empty it yourself when sure.
- **Nothing happens without approval.** `scan` and `review` never touch files.
  `apply` acts only on items you marked approved.
- **Every run is reversible.** Each move is logged `src → dst`; `klean undo`
  walks it back. Collisions are suffixed, never overwritten.
- **All state lives outside the folder being cleaned** (`~/.klean`), so Klean
  never adds clutter to fix clutter.

## Install

```bash
pip install kleanup      # installs the `klean` command
```

Requires Python 3.10+. Works on macOS, Linux, and Windows.

From a local checkout instead: `pip install -e .`, or run without installing
with `python3 -m klean <command>`.

## Usage

```bash
klean ui                   # scan + open the web UI: pick actions, approve, apply, undo
klean scan                 # propose a plan for ~/Desktop (no changes)
klean scan --organize      # also propose sorting every file into type folders
klean scan --smart         # use an LLM to group related files into named folders
klean review               # print summary + open the web UI to approve visually
klean review --terminal    # approve in the terminal instead of the browser
klean review --approve-high  # auto-approve only the safe, high-confidence ones
klean apply                # execute approved actions (asks to confirm)
klean undo                 # reverse the most recent apply
klean status               # list recent runs
```

`klean ui` is the one-command path: it scans, prints the terminal summary, and
opens the browser where you do everything else.

### Reviewing

`klean ui` / `klean review` always print the grouped summary to the terminal,
then open a local web UI (`http://127.0.0.1:<port>`) with image **thumbnails**,
checkboxes, per-group "approve all", and a live "MB that leaves the Desktop"
counter. You can manage everything from the browser:

- **Change any file's action** with a per-row dropdown (keep / trash / archive /
  organize), and type a destination folder for archive/organize.
- **Apply** the approved actions and **Undo** the last run — both as buttons, no
  terminal round-trip.
- Every UI action also **prints its CLI equivalent** to the terminal, so the
  browser teaches you the command-line workflow.

Approve in whichever surface you prefer — both read and write the same
`plan.json`.

- `--terminal` — skip the UI, approve group-by-group in the terminal.
- `--no-browser` — start the UI server but don't auto-open the browser.

The UI is pure stdlib, binds only to `127.0.0.1`, makes no network calls except
the optional LLM grouping (below), and its thumbnail endpoint only serves image
files that resolve inside the scanned folder.

## Optional: LLM-powered grouping (`--smart`)

By default Klean is **100% deterministic and offline** — duplicate, junk, and
archive decisions need no LLM. `--smart` adds one thing on top: semantically
**grouping related files into named folders** (e.g. "these 11 are the app-store
assets → one folder"). It only ever upgrades `keep` items into `move`
suggestions; it never makes a delete decision.

Provider resolution (first available wins), so no setup is required to try it:

1. **Anthropic API** — if `ANTHROPIC_API_KEY` is set (uses raw HTTPS, no extra
   dependency). Model defaults to `claude-opus-4-8`; override with `KLEAN_MODEL`.
2. **System Claude** — if the `claude` CLI is on your `PATH`.
3. **Neither** — Klean prints a note and proceeds with rules only.

```bash
klean scan --smart      # or: klean ui --smart
```

Point it at any folder with `klean scan --target ~/Downloads`.

## The four actions

| Action | Meaning | Example rule |
|--------|---------|--------------|
| `keep`    | leave in place (default) | nothing matched |
| `trash`   | move to quarantine | system junk, exact duplicates, old installers |
| `archive` | move to external memory | redundant `.zip` whose folder exists; large + old + untouched files |
| `move`    | organize into a subfolder | screenshots → `Screenshots/`; (with `--organize`) by file type |

Confidence is shown per item: **[H]** mechanical & safe, **[M]** strong
heuristic, **[L]** suggestion only. `--approve-high` acts on **[H]** alone.

The archive destination defaults to `~/Archive` (override with `KLEAN_ARCHIVE`)
and can be changed per-item during `review`.

## Architecture

| Module | Stage | Responsibility |
|--------|-------|----------------|
| `scan.py`    | 1 Scan    | walk the folder, hash a content signature, build the index |
| `analyze.py` | 2 Analyze | deterministic rules → proposed action + reason + confidence |
| `model.py`   | —         | `Plan` / `PlanItem` data model, JSON (de)serialization |
| `report.py`  | 4 Review  | human-readable grouped summary |
| `execute.py` | 5 Apply   | move approved items, write `undo.json` |
| `undo.py`    | 6 Undo    | reverse a run from its log |
| `smart.py`   | 2b Enrich | optional LLM grouping (API or `claude` CLI), fails soft |
| `ui.py`      | 4 Review  | local web UI: thumbnails, per-row actions, apply/undo |
| `cli.py`     | —         | `scan` / `ui` / `review` / `apply` / `undo` / `status` |

The rules are intentionally deterministic and self-explaining. The optional LLM
layer (`smart.py`) runs *after* `analyze` and only upgrades `keep` items into
named `move` groups — it never changes the safety model.

## Configuration

Environment variables (see `klean/config.py`):

- `KLEAN_TARGET` — folder to clean (default `~/Desktop`)
- `KLEAN_HOME` — where plans/logs/quarantine live (default `~/.klean`)
- `KLEAN_ARCHIVE` — default archive destination (default `~/Archive`)
- `ANTHROPIC_API_KEY` — enables `--smart` grouping via the Anthropic API
- `KLEAN_MODEL` — model for `--smart` (default `claude-opus-4-8`)
