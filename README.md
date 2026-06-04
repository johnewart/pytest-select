# pytest-select

AST-indexed, SQLite-backed pytest test selection for merge-request CI and merge queues.

## Installation

pytest-select is not published to PyPI yet. Install from GitHub until a release is available.

### pip

```bash
# Latest from main
pip install "pytest-select @ git+https://github.com/johnewart/pytest-select.git@main"

# Pin to a tag or commit
pip install "pytest-select @ git+https://github.com/johnewart/pytest-select.git@v0.1.0"
pip install "pytest-select @ git+https://github.com/johnewart/pytest-select.git@abc1234"
```

For local development in a clone of this repo:

```bash
pip install -e ".[dev]"
```

### pyproject.toml

Add a [PEP 508 direct reference](https://packaging.python.org/en/latest/specifications/version-specifiers/#direct-references) under `[project]` dependencies:

```toml
[project]
dependencies = [
    "pytest>=7.0",
    "pytest-select @ git+https://github.com/johnewart/pytest-select.git@main",
]
```

Pin to a tag or commit instead of a branch when you want reproducible CI:

```toml
"pytest-select @ git+https://github.com/johnewart/pytest-select.git@v0.1.0"
```

**uv** — optional `[tool.uv.sources]` (works alongside the dependency line above):

```toml
[tool.uv.sources]
pytest-select = { git = "https://github.com/johnewart/pytest-select.git", rev = "main" }
```

**Poetry**:

```toml
[tool.poetry.dependencies]
pytest-select = { git = "https://github.com/johnewart/pytest-select.git", rev = "main" }
```

**pip-tools** (`requirements.in`):

```text
pytest-select @ git+https://github.com/johnewart/pytest-select.git@main
```

Then run `pip-compile` / `uv pip compile` as usual.

### GitHub Actions

Reference the **reusable index workflow** from this repository and pass an `install-command` that pulls the package from GitHub:

```yaml
jobs:
  index:
    uses: johnewart/pytest-select/.github/workflows/reusable-pytest-select-index.yml@main
    with:
      python-version: "3.12"
      base-ref: ${{ github.event.pull_request.base.sha || '' }}
      install-command: >-
        pip install pytest
        "pytest-select @ git+https://github.com/johnewart/pytest-select.git@main"
    secrets: inherit

  test-pr:
    needs: index
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: >-
          pip install pytest
          "pytest-select @ git+https://github.com/johnewart/pytest-select.git@main"
      - uses: actions/cache/restore@v4
        with:
          path: .pytest-select
          key: pytest-select-index-${{ github.sha }}
      - run: |
          pytest \
            --select-from-diff="${{ github.event.pull_request.base.sha }}...${{ github.sha }}" \
            --index-db=.pytest-select/index.sqlite
```

If you vendor a copy of pytest-select inside your repo (e.g. `vendor/pytest-select/`), point `install-command` at that path instead:

```yaml
install-command: pip install pytest ./vendor/pytest-select
```

See also:

- Reusable workflow: [`.github/workflows/reusable-pytest-select-index.yml`](.github/workflows/reusable-pytest-select-index.yml)
- Full example pipeline: [`.github/workflows/example-pytest-select-ci.yml`](.github/workflows/example-pytest-select-ci.yml)
- Cache and ancestry resolver: [`docs/github-actions-cache.md`](docs/github-actions-cache.md)

## Quick start

If you cloned this repo for development, install in editable mode:

```bash
pip install -e ".[dev]"
```

If you are consuming pytest-select in another project, see [Installation](#installation) for GitHub / `pyproject.toml` setup.

```bash
# Build / refresh the dependency index (cache in CI)
pytest --reindex --index-db=.pytest-select/index.sqlite

# MR: run tests affected by diff vs main
pytest --select-from-diff=origin/main...HEAD --index-db=.pytest-select/index.sqlite

# Optional JSON report for CI annotations
pytest --select-from-diff=origin/main...HEAD --select-report=selected.json

# Preview which tests would run (stdout: one nodeid per line)
pytest --select-from-diff=origin/main...HEAD --select-print

# Same, with reasoning chains (changed files, reverse-import expansion, per-test why)
pytest --select-from-diff=origin/main...HEAD --select-print --select-print-detailed
```

## Development

Install dev dependencies (includes pytest, ruff, and pyrefly):

```bash
pip install -e ".[dev]"
```

Run the test suite, linter, formatter, and type checker:

```bash
pytest
ruff check src tests
ruff format src tests
pyrefly check
```

CI runs these checks on every pull request via [`.github/workflows/lint.yml`](.github/workflows/lint.yml).

## Architecture

1. **Index** — Parse Python ASTs, build import dependency graph, collect tests, compute per-test file reachability → SQLite.
2. **Select** — Git diff → changed files → reverse importer expansion → greedy set cover using impact/cost scores.
3. **Safety** — Over-approximate deps; widen on `conftest.py` / `__init__.py` changes; optional fallback sampling.

## CLI options

| Option | Description |
|--------|-------------|
| `--reindex` | Build or refresh the SQLite index, then exit |
| `--index-db PATH` | Index database path (default: `.pytest-select/index.sqlite`) |
| `--select-from-diff REF` | Git revision range (e.g. `origin/main...HEAD`) |
| `--select-print` | Print selected test nodeids (one per line) and exit |
| `--select-print-detailed` | With `--select-print`, show changed→affected→test chains |
| `--select-report PATH` | Write JSON report of selection |
| `--select-safety-margin N` | Reverse-dep expansion depth (default: 2) |
| `--select-fallback-percentile P` | Include top P% impact tests as safety net (default: 0) |
| `--select-fallback-full-on-wide` | Run full suite if conftest/init changed |
| `--select-fail-on-collection-errors` | Fail when test modules cannot be imported (default: skip them) |

### Optional dependency groups

Projects that split heavy ML or service dependencies into optional groups (e.g. `dev` vs `ml`) often have test modules that cannot be imported in a lean CI environment. During `--reindex` and `--select-from-diff`, pytest-select **automatically enables** pytest's continue-on-collection-errors behavior: importable tests are indexed or selected, and modules that fail collection (missing `presidio_analyzer`, `spacy`, etc.) are skipped with a warning.

Reindex on a machine **with** the optional group installed to include those tests in the index; selection on a machine **without** them still works for the rest of the suite. Use `--select-fail-on-collection-errors` to restore strict failure when any test module cannot be imported.

## CI example

### GitHub Actions (commit-keyed cache)

Install from GitHub (see [Installation](#installation)), then use the **reusable workflow** and ancestry resolver so PRs restore the nearest parent index and only incrementally reindex:

- Workflow: [`.github/workflows/reusable-pytest-select-index.yml`](.github/workflows/reusable-pytest-select-index.yml)
- Example pipeline: [`.github/workflows/example-pytest-select-ci.yml`](.github/workflows/example-pytest-select-ci.yml)
- Docs: [`docs/github-actions-cache.md`](docs/github-actions-cache.md)

```bash
# Resolve which cache key to restore (run after restoring manifest cache)
pytest-select-cache-resolve \
  --head "$GITHUB_SHA" \
  --base "${PR_BASE_SHA}" \
  --manifest cache-metadata/pytest-select-manifest.json \
  --github-api \
  --github-output "$GITHUB_OUTPUT"
```

### Generic CI

```yaml
# Job 1: index (cached artifact)
- run: pytest --reindex --index-db=$CI_CACHE/test-index.sqlite -q

# Job 2: MR validation
- run: |
    pytest \
      --select-from-diff=$CI_MERGE_REQUEST_DIFF_BASE_SHA...HEAD \
      --index-db=$CI_CACHE/test-index.sqlite \
      --select-report=selected.json
```

## v1 scope

- File-level import graph
- Reverse importers (configurable depth)
- Static cost from expensive-module imports
- Impact = reachable file count from test module
- Greedy set cover for minimal safe subset
