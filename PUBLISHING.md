# Publishing `kleanup` to PyPI

The package is distributed on PyPI as **`kleanup`** (the installed command is
still `klean`). Once published, anyone can install it with:

```bash
pip install kleanup
```

## One-time setup

1. **Create accounts** (free):
   - PyPI: https://pypi.org/account/register/
   - TestPyPI (for rehearsals): https://test.pypi.org/account/register/
2. **Create an API token** on each: Account settings → API tokens → "Add API
   token" (scope: entire account for the first upload). Copy it — it's shown
   once.
3. **Install the build tooling** (ideally in a throwaway venv so it doesn't
   touch your system Python):
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install build twine
   ```

## Before the first upload — edit two things

- `pyproject.toml` → `[project.urls]`: change the `velvee/kleanup` placeholders
  to your real repository URL.
- `pyproject.toml` → `authors`: confirm the name/email is how you want it shown.

## Build

From the project root:

```bash
rm -rf dist build *.egg-info
python3 -m build          # produces dist/kleanup-0.1.0.tar.gz and .whl
twine check dist/*        # validates the metadata renders on PyPI
```

## Rehearse on TestPyPI (recommended)

```bash
twine upload --repository testpypi dist/*
# then, in a fresh venv, confirm it installs and runs:
pip install --index-url https://test.pypi.org/simple/ kleanup
klean --help
```

## Publish to the real PyPI

```bash
twine upload dist/*
```

Paste the API token when prompted (username `__token__`). Within a minute:

```bash
pip install kleanup
```

## Releasing updates

1. Bump `version` in `pyproject.toml` (PyPI rejects re-uploading the same
   version).
2. Rebuild and re-upload:
   ```bash
   rm -rf dist && python3 -m build && twine upload dist/*
   ```

## What end users get

`pip install kleanup` puts a `klean` command on their PATH. They then run
`klean scan` / `klean review` / `klean apply` / `klean undo` exactly as
documented in the README. No extra dependencies are pulled in — the tool is
pure standard library.
