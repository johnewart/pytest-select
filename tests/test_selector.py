"""Selection engine tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from conftest import FIXTURE
from pytest_select.db.queries import IndexDatabase
from pytest_select.index.builder import build_index_with_session
from pytest_select.select.selector import select_tests


def _git_init_commit(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial", "--author", "test <test@test.com>"],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t.com",
        },
    )


def _build_index(db_path, root=FIXTURE):
    import sys

    sys.path.insert(0, str(root))
    from helpers import collect_items

    items = collect_items(root)
    build_index_with_session(root, db_path, items)


def test_select_tests_util_change(tmp_path):
    repo = FIXTURE
    db_path = tmp_path / "index.sqlite"
    _build_index(db_path)

    # Simulate diff by using working tree vs empty tree — use HEAD~0 trick:
    # Commit baseline, change util, diff HEAD
    work = tmp_path / "work"
    import shutil

    shutil.copytree(repo, work)
    _git_init_commit(work)
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
    _build_index(tmp_path / "index2.sqlite", work)

    selected, report = select_tests("HEAD~1...HEAD", tmp_path / "index2.sqlite", work)
    assert report["changed_files"]
    nodeids = selected
    assert any("test_util" in n or "test_service" in n for n in nodeids)


def test_reverse_importers(tmp_path):
    db_path = tmp_path / "index.sqlite"
    _build_index(db_path)
    db = IndexDatabase(db_path)
    rev = db.reverse_importers({"app/util.py"}, max_depth=2)
    assert "app/service.py" in rev
    db.close()


def test_select_print_lists_nodeids(tmp_path):
    import shutil
    import sys

    work = tmp_path / "work"
    shutil.copytree(FIXTURE, work)
    _git_init_commit(work)
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
    db_path = tmp_path / "index.sqlite"
    _build_index(db_path, work)

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
    assert proc.returncode == 0, proc.stderr
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines
    assert any("test_util" in ln or "test_service" in ln for ln in lines)
