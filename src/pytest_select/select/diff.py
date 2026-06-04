"""Parse git diff into changed files and symbols."""

from __future__ import annotations

import ast
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DiffResult:
    changed_files: set[str] = field(default_factory=set)
    changed_symbols: set[tuple[str, str]] = field(default_factory=set)  # (file, qualname)
    wide_blast_radius: bool = False  # conftest / __init__ under tests


_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)


def _run_git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def parse_git_diff(diff_ref: str, root: Path) -> DiffResult:
    """
    diff_ref: revision range e.g. 'origin/main...HEAD' or 'main..HEAD'
    Returns posix paths relative to root.
    """
    root = root.resolve()
    out = DiffResult()

    names = _run_git(["diff", "--name-only", diff_ref], root).strip().splitlines()
    for name in names:
        if not name.endswith(".py"):
            continue
        posix = Path(name).as_posix()
        out.changed_files.add(posix)
        if "conftest.py" in posix or posix.endswith("__init__.py"):
            if posix.startswith("tests/") or "/tests/" in posix:
                out.wide_blast_radius = True

    # Line-level hunks for symbol mapping
    patch = _run_git(["diff", "-U0", diff_ref], root)
    current_file: str | None = None
    changed_lines: list[int] = []

    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            if current_file and changed_lines:
                _map_lines_to_symbols(root, current_file, changed_lines, out)
            path = line[6:].strip()
            if path == "/dev/null":
                current_file = None
                changed_lines = []
                continue
            current_file = Path(path).as_posix()
            changed_lines = []
            if current_file.endswith(".py"):
                out.changed_files.add(current_file)
        elif line.startswith("@@") and current_file:
            m = _HUNK_RE.match(line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) else 1
                changed_lines.extend(range(start, start + max(count, 1)))
        elif current_file and line.startswith("+") and not line.startswith("+++"):
            pass  # line numbers from hunk headers suffice for v1

    if current_file and changed_lines:
        _map_lines_to_symbols(root, current_file, changed_lines, out)

    return out


def _map_lines_to_symbols(
    root: Path, rel_file: str, lines: list[int], out: DiffResult
) -> None:
    path = root / rel_file
    if not path.is_file():
        return
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel_file)
    except (SyntaxError, OSError):
        return

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", start) or start
            if any(start <= ln <= end for ln in lines):
                qual = getattr(node, "name", "")
                # Build rough qualname by walking parents (simplified: name only for v1)
                out.changed_symbols.add((rel_file, qual))


def expand_affected_files(
    diff: DiffResult,
    db,
    safety_margin: int = 2,
) -> set[str]:
    """Changed files + reverse importers up to safety_margin depth."""
    affected = set(diff.changed_files)
    if affected:
        expanded = db.reverse_importers(affected, max_depth=safety_margin)
        affected |= expanded
    return affected
