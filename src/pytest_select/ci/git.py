"""Git ancestry helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path


def rev_list(
    start: str,
    *,
    cwd: Path | None = None,
    max_count: int | None = None,
    first_parent: bool = False,
) -> list[str]:
    """Return commit SHAs reachable from start (start first), newest first."""
    args = ["git", "rev-list", start]
    if first_parent:
        args.insert(2, "--first-parent")
    if max_count is not None:
        args.extend(["-n", str(max_count)])
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]


def merge_base(ref_a: str, ref_b: str, *, cwd: Path | None = None) -> str | None:
    result = subprocess.run(
        ["git", "merge-base", ref_a, ref_b],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    out = result.stdout.strip()
    return out or None


def resolve_head(sha: str, *, cwd: Path | None = None) -> str:
    """Resolve HEAD or branch name to full SHA."""
    if sha.upper() in ("HEAD", "@{u}"):
        sha = "HEAD"
    result = subprocess.run(
        ["git", "rev-parse", sha],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()
