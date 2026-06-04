"""Shared test helpers."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


def collect_items(root: Path) -> list:
    root = root.resolve()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    items = []
    for ln in proc.stdout.splitlines():
        ln = ln.strip()
        if "::" not in ln:
            continue
        rel_file = ln.split("::")[0]
        name = ln.split("::")[-1]
        items.append(
            SimpleNamespace(
                nodeid=ln,
                name=name,
                path=root / rel_file,
                fspath=root / rel_file,
            )
        )
    if not items:
        raise RuntimeError(f"no tests collected under {root}: {proc.stdout!r}")
    return items
