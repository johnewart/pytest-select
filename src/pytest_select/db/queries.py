"""SQLite queries for the test selection index."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class IndexDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> IndexDatabase:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def init_schema(self) -> None:
        ddl = _SCHEMA_PATH.read_text(encoding="utf-8")
        self._conn.executescript(ddl)
        self._conn.commit()

    def clear_all(self) -> None:
        for table in (
            "test_scores",
            "test_coverage",
            "tests",
            "deps",
            "symbols",
            "files",
            "test_runs",
        ):
            self._conn.execute(f"DELETE FROM {table}")
        self._conn.commit()

    def upsert_file(self, path: str, mtime: float, sha256: str) -> None:
        self._conn.execute(
            "INSERT INTO files (path, mtime, sha256) VALUES (?, ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET mtime=excluded.mtime, sha256=excluded.sha256",
            (path, mtime, sha256),
        )

    def get_file_sha(self, path: str) -> str | None:
        row = self._conn.execute(
            "SELECT sha256 FROM files WHERE path = ?", (path,)
        ).fetchone()
        return row["sha256"] if row else None

    def insert_dep(
        self,
        source_file: str,
        target_file: str,
        edge_kind: str,
        line: int | None = None,
        source_symbol: str | None = None,
        target_symbol: str | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO deps (source_file, source_symbol, target_file, target_symbol, edge_kind, line) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (source_file, source_symbol, target_file, target_symbol, edge_kind, line),
        )

    def clear_deps_for_file(self, source_file: str) -> None:
        self._conn.execute("DELETE FROM deps WHERE source_file = ?", (source_file,))

    def insert_test(
        self, nodeid: str, file_path: str, name: str, markers: dict | None = None
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO tests (nodeid, file_path, name, markers) VALUES (?, ?, ?, ?)",
            (nodeid, file_path, name, json.dumps(markers or {})),
        )

    def clear_tests(self) -> None:
        self._conn.execute("DELETE FROM test_coverage")
        self._conn.execute("DELETE FROM test_scores")
        self._conn.execute("DELETE FROM tests")

    def insert_test_coverage(
        self,
        test_nodeid: str,
        file_path: str,
        symbol_qualname: str = "",
        depth: int = 0,
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO test_coverage (test_nodeid, file_path, symbol_qualname, depth) "
            "VALUES (?, ?, ?, ?)",
            (test_nodeid, file_path, symbol_qualname, depth),
        )

    def insert_test_score(
        self,
        test_nodeid: str,
        impact: float,
        cost: float,
        files_reached: int,
        symbols_reached: int = 0,
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO test_scores (test_nodeid, impact, cost, files_reached, symbols_reached) "
            "VALUES (?, ?, ?, ?, ?)",
            (test_nodeid, impact, cost, files_reached, symbols_reached),
        )

    def all_test_nodeids(self) -> list[str]:
        rows = self._conn.execute("SELECT nodeid FROM tests ORDER BY nodeid").fetchall()
        return [r["nodeid"] for r in rows]

    def tests_touching_files(self, files: Iterable[str]) -> set[str]:
        file_set = set(files)
        if not file_set:
            return set()
        placeholders = ",".join("?" * len(file_set))
        rows = self._conn.execute(
            f"SELECT DISTINCT test_nodeid FROM test_coverage WHERE file_path IN ({placeholders})",
            list(file_set),
        ).fetchall()
        return {r["test_nodeid"] for r in rows}

    def test_coverage_map(
        self, nodeids: Iterable[str] | None = None
    ) -> dict[str, set[str]]:
        if nodeids is None:
            rows = self._conn.execute(
                "SELECT test_nodeid, file_path FROM test_coverage"
            ).fetchall()
        else:
            ids = list(nodeids)
            if not ids:
                return {}
            placeholders = ",".join("?" * len(ids))
            rows = self._conn.execute(
                f"SELECT test_nodeid, file_path FROM test_coverage WHERE test_nodeid IN ({placeholders})",
                ids,
            ).fetchall()
        result: dict[str, set[str]] = {}
        for r in rows:
            result.setdefault(r["test_nodeid"], set()).add(r["file_path"])
        return result

    def test_scores(
        self, nodeids: Iterable[str] | None = None
    ) -> dict[str, tuple[float, float]]:
        if nodeids is None:
            rows = self._conn.execute(
                "SELECT test_nodeid, impact, cost FROM test_scores"
            ).fetchall()
        else:
            ids = list(nodeids)
            if not ids:
                return {}
            placeholders = ",".join("?" * len(ids))
            rows = self._conn.execute(
                f"SELECT test_nodeid, impact, cost FROM test_scores WHERE test_nodeid IN ({placeholders})",
                ids,
            ).fetchall()
        return {r["test_nodeid"]: (r["impact"], r["cost"]) for r in rows}

    def reverse_importers(
        self, target_files: Iterable[str], max_depth: int = 2
    ) -> set[str]:
        """BFS reverse walk: files that import (depend on) target_files."""
        frontier = set(target_files)
        seen = set(frontier)
        for _ in range(max_depth):
            if not frontier:
                break
            placeholders = ",".join("?" * len(frontier))
            rows = self._conn.execute(
                f"SELECT DISTINCT source_file FROM deps WHERE target_file IN ({placeholders}) "
                "AND edge_kind = 'import'",
                list(frontier),
            ).fetchall()
            next_frontier: set[str] = set()
            for r in rows:
                src = r["source_file"]
                if src not in seen:
                    seen.add(src)
                    next_frontier.add(src)
            frontier = next_frontier
        return seen

    def commit(self) -> None:
        self._conn.commit()
