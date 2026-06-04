# pytest-select

AST-indexed, SQLite-backed pytest test selection for merge-request CI and merge queues.

## Quick start

```bash
pip install -e ".[dev]"

# Build / refresh the dependency index (cache in CI)
pytest --reindex --index-db=.pytest-select/index.sqlite

# MR: run tests affected by diff vs main
pytest --select-from-diff=origin/main...HEAD --index-db=.pytest-select/index.sqlite

# Optional JSON report for CI annotations
pytest --select-from-diff=origin/main...HEAD --select-report=selected.json
```

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
| `--select-report PATH` | Write JSON report of selection |
| `--select-safety-margin N` | Reverse-dep expansion depth (default: 2) |
| `--select-fallback-percentile P` | Include top P% impact tests as safety net (default: 0) |
| `--select-fallback-full-on-wide` | Run full suite if conftest/init changed |

## CI example

### GitHub Actions (commit-keyed cache)

Use the **reusable workflow** and ancestry resolver so PRs restore the nearest parent index and only incrementally reindex:

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
