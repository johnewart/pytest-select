"""Build SQLite index from AST and pytest collection."""

from __future__ import annotations

import ast
import hashlib
import os
from pathlib import Path

from pytest_select.db.queries import IndexDatabase
from pytest_select.index.graph import build_forward_neighbor_fn, forward_reachable
from pytest_select.index.resolver import ImportResolver
from pytest_select.score.cost import score_file_cost
from pytest_select.score.impact import compute_impact_percentiles


def _rel_test_path(item, root: Path) -> str | None:
    """Resolve test module path relative to project root."""
    root = root.resolve()
    for attr in ("path", "fspath"):
        raw = getattr(item, attr, None)
        if raw is None:
            continue
        try:
            return Path(str(raw)).resolve().relative_to(root).as_posix()
        except (ValueError, TypeError):
            pass
    nodeid = getattr(item, "nodeid", None)
    if nodeid:
        rel = nodeid.split("::")[0].replace("\\", "/")
        if (root / rel).is_file():
            return rel
    loc = getattr(item, "location", None)
    if loc:
        try:
            return Path(str(loc[0])).resolve().relative_to(root).as_posix()
        except (ValueError, TypeError):
            pass
    return None


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_py_files(root: Path, ignore_dirs: set[str] | None = None) -> list[Path]:
    ignore = ignore_dirs or {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest-select",
        "node_modules",
        ".tox",
        "dist",
        "build",
    }
    result: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ignore]
        for name in filenames:
            if name.endswith(".py"):
                result.append(Path(dirpath) / name)
    return result


def _extract_imports(
    tree: ast.AST, source_path: Path, resolver: ImportResolver
) -> list[tuple[str, str, int]]:
    """Return list of (target_file, edge_kind, line)."""
    edges: list[tuple[str, str, int]] = []
    rel_source = source_path

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = resolver.resolve_module(alias.name)
                if target:
                    edges.append((target, "import", node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue
            target = resolver.resolve_module(
                node.module or "", level=node.level, relative_to=rel_source
            )
            if target:
                edges.append((target, "import", node.lineno))
    return edges


def index_source_files(db: IndexDatabase, root: Path, resolver: ImportResolver) -> None:
    root = root.resolve()
    for path in _iter_py_files(root):
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            tree = ast.parse(text, filename=rel)
        except SyntaxError:
            continue

        mtime = path.stat().st_mtime
        sha = _file_hash(path)
        existing = db.get_file_sha(rel)
        if existing == sha:
            continue

        db.clear_deps_for_file(rel)
        db.upsert_file(rel, mtime, sha)
        for target, kind, line in _extract_imports(tree, path, resolver):
            db.insert_dep(rel, target, kind, line=line)

    db.commit()


def index_tests_from_items(db: IndexDatabase, root: Path, items: list) -> None:
    """Record collected tests and compute forward import closure per test file."""
    db.clear_tests()
    root = root.resolve()
    neighbor_fn = build_forward_neighbor_fn(db._conn)

    # Group items by test file
    by_file: dict[str, list] = {}
    for item in items:
        rel = _rel_test_path(item, root)
        if not rel:
            continue
        by_file.setdefault(rel, []).append(item)

    file_costs: dict[str, float] = {}
    file_reach: dict[str, dict[str, int]] = {}

    for test_file, _file_items in by_file.items():
        path = root / test_file
        if path.is_file():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=test_file)
                file_costs[test_file] = score_file_cost(tree)
            except (SyntaxError, OSError):
                file_costs[test_file] = 1.0
        else:
            file_costs[test_file] = 1.0

        reach = forward_reachable({test_file}, neighbor_fn)
        file_reach[test_file] = reach

    raw_impacts: dict[str, float] = {}
    for item in items:
        nodeid = item.nodeid
        rel = _rel_test_path(item, root)
        if not rel:
            continue
        name = str(getattr(item, "name", nodeid.split("::")[-1]))
        markers = {}
        try:
            for m in item.iter_markers():
                markers.setdefault(m.name, []).append(m.args)
        except Exception:
            pass
        db.insert_test(nodeid, rel, name, markers)

        reach = file_reach.get(rel, {rel: 0})
        for fp, depth in reach.items():
            db.insert_test_coverage(nodeid, fp, depth=depth)
        raw_impacts[nodeid] = float(len(reach))

    percentiles = compute_impact_percentiles(raw_impacts)
    for item in items:
        nodeid = item.nodeid
        rel = _rel_test_path(item, root)
        if not rel:
            continue
        impact = percentiles.get(nodeid, 50.0)
        cost = max(file_costs.get(rel, 1.0), 0.1)
        files_reached = len(file_reach.get(rel, {}))
        db.insert_test_score(nodeid, impact, cost, files_reached)
    db.commit()


def build_index_with_session(
    root: Path, db_path: str | Path, items: list
) -> IndexDatabase:
    """Reindex sources + tests when items are already collected."""
    root = Path(root).resolve()
    db = IndexDatabase(db_path)
    db.init_schema()
    resolver = ImportResolver(root)
    index_source_files(db, root, resolver)
    index_tests_from_items(db, root, items)
    return db
