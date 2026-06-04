"""Tests for optional-dependency collection error handling."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from conftest import OPTIONAL_DEPS_FIXTURE
from pytest_select.db.queries import IndexBuildStats, IndexDatabase
from pytest_select.index.builder import build_index_with_session


def _collect_items_allow_errors(root: Path) -> list:
    from types import SimpleNamespace

    root = root.resolve()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--continue-on-collection-errors",
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert proc.returncode in (0, 1), proc.stderr + proc.stdout
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
    return items


def test_format_message_reports_collection_errors():
    stats = IndexBuildStats(
        collected=1,
        mapped=1,
        collection_errors=["tests/test_ml.py"],
    )
    msg = stats.format_message()
    assert "skipped 1 module(s)" in msg
    assert "test_ml.py" in msg


def test_reindex_skips_unimportable_modules(tmp_path):
    db_path = tmp_path / "index.sqlite"
    items = _collect_items_allow_errors(OPTIONAL_DEPS_FIXTURE)
    assert len(items) == 1
    assert "test_util" in items[0].nodeid

    _, stats = build_index_with_session(OPTIONAL_DEPS_FIXTURE, db_path, items)
    stats.collection_errors = ["tests/test_ml.py"]
    assert stats.mapped == 1

    db = IndexDatabase(db_path)
    nodeids = db.all_test_nodeids()
    assert len(nodeids) == 1
    assert "test_util" in nodeids[0]
    db.close()


def test_reindex_cli_continues_with_missing_deps(tmp_path):
    db_path = tmp_path / "index.sqlite"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--reindex",
            f"--index-db={db_path}",
            "-q",
        ],
        cwd=OPTIONAL_DEPS_FIXTURE,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "indexed 1 test" in proc.stdout
    assert "collection errors" in proc.stdout.lower() or "skipped" in proc.stdout.lower()

    db = IndexDatabase(db_path)
    assert len(db.all_test_nodeids()) == 1
    db.close()


def test_select_print_with_missing_deps(tmp_path):
    import shutil

    work = tmp_path / "work"
    shutil.copytree(OPTIONAL_DEPS_FIXTURE, work)
    subprocess.run(["git", "init"], cwd=work, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=work, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial", "--author", "test <test@test.com>"],
        cwd=work,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t.com",
        },
    )

    db_path = tmp_path / "index.sqlite"
    reindex = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--reindex",
            f"--index-db={db_path}",
            "-q",
        ],
        cwd=work,
        capture_output=True,
        text=True,
    )
    assert reindex.returncode == 0, reindex.stderr + reindex.stdout

    util = work / "app" / "util.py"
    util.write_text(
        'def greet(name: str) -> str:\n    return f"hi {name}"\n',
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "app/util.py"], cwd=work, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "change util", "--author", "test <test@test.com>"],
        cwd=work,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t.com",
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--select-from-diff=HEAD~1...HEAD",
            f"--index-db={db_path}",
            "--select-print",
            "-q",
        ],
        cwd=work,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip() and "::" in ln]
    assert any("test_util" in ln for ln in lines)
