"""Build SQLite index from AST and pytest collection."""

from __future__ import annotations

import ast
import hashlib
import os
from pathlib import Path

from pytest_select.db.queries import IndexBuildStats, IndexDatabase
from pytest_select.index.graph import build_forward_neighbor_fn, forward_reachable
from pytest_select.index.resolver import ImportResolver
from pytest_select.score.cost import score_file_cost
from pytest_select.score.impact import compute_impact_percentiles


def _nodeid_file_part(nodeid: str) -> str:
    return nodeid.split("::")[0].replace("\\", "/")


def _resolved_file_index(root: Path, known_files: set[str]) -> dict[Path, str]:
    index: dict[Path, str] = {}
    for rel in known_files:
        try:
            index[(root / rel).resolve()] = rel
        except OSError:
            continue
    return index


def _match_known_file(rel: str, known_files: set[str]) -> str | None:
    if rel in known_files:
        return rel
    matches = [f for f in known_files if f == rel or f.endswith("/" + rel)]
    if len(matches) == 1:
        return matches[0]
    return None


def _rel_test_path(
    item,
    root: Path,
    known_files: set[str] | None = None,
    *,
    resolved_index: dict[Path, str] | None = None,
) -> str | None:
    """Resolve test module path relative to project root."""
    root = root.resolve()
    known_files = known_files or set()
    resolved_index = resolved_index or _resolved_file_index(root, known_files)

    for attr in ("path", "fspath"):
        raw = getattr(item, attr, None)
        if raw is None:
            continue
        try:
            abs_path = Path(str(raw)).resolve()
        except (ValueError, TypeError, OSError):
            continue
        try:
            return abs_path.relative_to(root).as_posix()
        except ValueError:
            mapped = resolved_index.get(abs_path)
            if mapped:
                return mapped

    nodeid = getattr(item, "nodeid", None)
    if nodeid:
        rel = _nodeid_file_part(nodeid)
        matched = _match_known_file(rel, known_files)
        if matched:
            return matched
        if (root / rel).is_file():
            return rel

    loc = getattr(item, "location", None)
    if loc:
        try:
            abs_path = Path(str(loc[0])).resolve()
        except (ValueError, TypeError, OSError):
            abs_path = None
        if abs_path is not None:
            try:
                return abs_path.relative_to(root).as_posix()
            except ValueError:
                mapped = resolved_index.get(abs_path)
                if mapped:
                    return mapped
    return None


def _item_debug_label(item) -> str:
    nodeid = getattr(item, "nodeid", None)
    if nodeid:
        return str(nodeid)
    for attr in ("path", "fspath"):
        raw = getattr(item, attr, None)
        if raw is not None:
            return str(raw)
    return repr(item)


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


def index_tests_from_items(
    db: IndexDatabase, root: Path, items: list
) -> IndexBuildStats:
    """Record collected tests and compute forward import closure per test file."""
    root = root.resolve()
    known_files = db.list_file_paths()
    resolved_index = _resolved_file_index(root, known_files)

    mapped: list[tuple[object, str]] = []
    unmapped_samples: list[str] = []
    for item in items:
        rel = _rel_test_path(
            item, root, known_files, resolved_index=resolved_index
        )
        if rel:
            mapped.append((item, rel))
        elif len(unmapped_samples) < 5:
            unmapped_samples.append(_item_debug_label(item))

    stats = IndexBuildStats(
        collected=len(items),
        mapped=len(mapped),
        unmapped_samples=unmapped_samples,
    )
    if not mapped:
        return stats

    db.clear_tests()
    neighbor_fn = build_forward_neighbor_fn(db._conn)

    by_file: dict[str, list] = {}
    for item, rel in mapped:
        by_file.setdefault(rel, []).append(item)

    file_costs: dict[str, float] = {}
    file_reach: dict[str, dict[str, int]] = {}

    for test_file in by_file:
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
    for item, rel in mapped:
        nodeid = item.nodeid
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
    for item, rel in mapped:
        nodeid = item.nodeid
        impact = percentiles.get(nodeid, 50.0)
        cost = max(file_costs.get(rel, 1.0), 0.1)
        files_reached = len(file_reach.get(rel, {}))
        db.insert_test_score(nodeid, impact, cost, files_reached)
    db.commit()
    return stats


def build_index_with_session(
    root: Path, db_path: str | Path, items: list
) -> tuple[IndexDatabase, IndexBuildStats]:
    """Reindex sources + tests when items are already collected."""
    root = Path(root).resolve()
    db = IndexDatabase(db_path)
    db.init_schema()
    resolver = ImportResolver(root)
    index_source_files(db, root, resolver)
    stats = index_tests_from_items(db, root, items)
    return db, stats
