# GitHub Actions: commit-keyed index cache

pytest-select stores its SQLite index in Actions cache using **the full commit SHA** as part of the key. On a new commit, a small Python helper walks **git ancestry** and picks the **nearest commit** that already has a cache entry, restores that index, then runs **`pytest --reindex`** (incremental: only changed `.py` files are re-parsed).

## Installing pytest-select in CI

The package is not on PyPI yet. In workflow steps and the reusable workflow's `install-command` input, install from GitHub:

```yaml
install-command: >-
  pip install pytest
  "pytest-select @ git+https://github.com/johnewart/pytest-select.git@main"
```

Pin to a tag or commit for reproducible builds:

```yaml
install-command: pip install pytest "pytest-select @ git+https://github.com/johnewart/pytest-select.git@v0.1.0"
```

See [README — Installation](../README.md#installation) for `pyproject.toml`, uv, and Poetry examples.

## Cache keys

| Artifact | Path | Cache key |
|----------|------|-----------|
| Index DB | `.pytest-select/` (contains `index.sqlite`) | `pytest-select-index-<full-sha>` |
| Manifest | `cache-metadata/pytest-select-manifest.json` | `pytest-select-manifest-<full-sha>` |

The manifest lives **outside** `.pytest-select/` so restoring an ancestor index directory does not overwrite it.

The **manifest** lists every commit for which an index was successfully built. The resolver walks `git rev-list` from `HEAD` and returns the first SHA present in the manifest (or, optionally, in the GitHub Actions caches API).

## Commands

```bash
# After restoring a manifest file from cache:
pytest-select-cache-resolve \
  --head "$GITHUB_SHA" \
  --base "${{ github.event.pull_request.base.sha }}" \
  --manifest cache-metadata/pytest-select-manifest.json \
  --github-api \
  --github-output "$GITHUB_OUTPUT"

# Outputs (GITHUB_OUTPUT): cache_hit, cache_sha, cache_key, cache_source, head_sha

# After pytest --reindex:
pytest-select-cache-record \
  --sha "$GITHUB_SHA" \
  --manifest .pytest-select/cache-manifest.json
```

## Required checkout settings

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0   # required — shallow clones break ancestry walks on PRs
```

## Reusable workflow

This repository ships:

`.github/workflows/reusable-pytest-select-index.yml`

**Consumer** (install from GitHub — adjust `rev` / tag as needed):

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

See also: `.github/workflows/example-pytest-select-ci.yml` (PR selection + merge group full suite).

## How ancestry resolution works

1. Restore the newest available **manifest** cache (`restore-keys: pytest-select-manifest-`).
2. `pytest-select-cache-resolve` loads known SHAs from the manifest.
3. Run `git rev-list HEAD` (newest first). If `--base` is set, stop at `merge-base(base, head)` so PRs do not scan the entire default-branch history.
4. First matching SHA → exact cache key `pytest-select-index-<sha>`.
5. `actions/cache/restore` with that **exact** key (not prefix LRU — that is why we resolve in Python).
6. `pytest --reindex` updates changed files; record current SHA in manifest; save new caches.

### GitHub API fallback

With `--github-api`, if the manifest is empty the tool calls:

`GET /repos/{owner}/{repo}/actions/caches?key=pytest-select-index-`

and intersects returned keys with ancestry. Requires `permissions: actions: read` and `GITHUB_TOKEN`.

## Local debugging

```bash
git fetch --depth=100 origin main
pytest-select-cache-resolve --head HEAD --base origin/main --manifest .pytest-select/cache-manifest.json
```
