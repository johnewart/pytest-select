"""Record the current commit in the cache manifest after a successful index build."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pytest_select.ci.git import resolve_head
from pytest_select.ci.manifest import CacheManifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record a commit in the pytest-select cache manifest")
    parser.add_argument("--sha", default="HEAD", help="Commit SHA or HEAD")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("cache-metadata/pytest-select-manifest.json"),
    )
    parser.add_argument(
        "--index-db",
        default=".pytest-select/index.sqlite",
        help="Path to index DB (stored in manifest metadata)",
    )
    parser.add_argument("--cwd", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        full = resolve_head(args.sha, cwd=args.cwd)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    manifest = CacheManifest(args.manifest)
    manifest.record(full, index_db=args.index_db)
    print(f"recorded {full} in {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
