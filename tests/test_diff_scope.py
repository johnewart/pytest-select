"""Tests for scoped conftest blast and early select-print."""

from __future__ import annotations

import subprocess
import sys
import time

from pytest_select.select.diff import _wide_blast_scope
from pytest_select.select.selector import _scoped_wide_blast_tests, _tests_in_scope


def test_wide_blast_scope_subdir_conftest():
    assert _wide_blast_scope("tests/fidesplus/conftest.py") == "tests/fidesplus/"


def test_wide_blast_scope_root_conftest():
    assert _wide_blast_scope("tests/conftest.py") == "tests/"


def test_wide_blast_scope_ignores_source_conftest():
    assert _wide_blast_scope("src/pkg/conftest.py") is None


def test_tests_in_scope_prefix():
    nodeids = {
        "tests/fidesplus/api/test_x.py::test_a",
        "tests/fides/api/test_y.py::test_b",
    }
    scoped = _tests_in_scope(nodeids, "tests/fidesplus/")
    assert scoped == {"tests/fidesplus/api/test_x.py::test_a"}


def test_scoped_wide_blast_merges_scopes():
    nodeids = {
        "tests/a/test_x.py::test_one",
        "tests/b/test_y.py::test_two",
        "tests/c/test_z.py::test_three",
    }
    selected = _scoped_wide_blast_tests(nodeids, {"tests/a/", "tests/b/"})
    assert selected == {
        "tests/a/test_x.py::test_one",
        "tests/b/test_y.py::test_two",
    }


def test_select_print_skips_collection(tmp_path):
    import shutil

    from conftest import FIXTURE
    from test_selector import _build_index, _git_init_commit

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

    start = time.monotonic()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--select-from-diff=HEAD~1...HEAD",
            f"--index-db={db_path}",
            "--select-print",
            "--select-print-detailed",
            "-q",
        ],
        cwd=work,
        capture_output=True,
        text=True,
    )
    elapsed = time.monotonic() - start

    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert elapsed < 5, f"select-print took {elapsed:.1f}s; expected index-only path"
    assert "collecting" not in proc.stdout.lower()
    assert "strategy=" in proc.stdout
    assert "pytest-select: would run" in proc.stderr
