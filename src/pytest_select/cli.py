"""Standalone CLI to build index without running tests."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def index_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build pytest-select SQLite index")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root")
    parser.add_argument(
        "--index-db",
        type=Path,
        default=Path(".pytest-select/index.sqlite"),
        help="Index database path",
    )
    args = parser.parse_args(argv)

    import pytest

    root = args.root.resolve()
    db_path = args.index_db
    # Run collection via pytest API
    config = pytest.Config.fromdictargs(
        {"testpaths": [str(root)]},
        ["--collect-only", "-q", str(root)],
    )
    config.rootpath = root
    config.invocation_params.dir = str(root)
    session = pytest.Session.from_config(config)
    session.perform_collect()

    from pytest_select.index.builder import build_index_with_session

    build_index_with_session(root, db_path, session.items)
    print(f"Indexed {len(session.items)} tests -> {db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(index_main())
