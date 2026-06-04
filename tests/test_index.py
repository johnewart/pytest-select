"""Index builder tests."""

from __future__ import annotations

from types import SimpleNamespace

from conftest import FIXTURE
from pytest_select.db.queries import IndexDatabase
from pytest_select.index.builder import (
    _rel_test_path,
    _resolved_file_index,
    build_index_with_session,
    index_source_files,
    index_tests_from_items,
)
from pytest_select.index.resolver import ImportResolver


def test_index_source_files_creates_import_edges(tmp_path):
    db_path = tmp_path / "index.sqlite"
    db = IndexDatabase(db_path)
    db.init_schema()
    resolver = ImportResolver(FIXTURE)
    index_source_files(db, FIXTURE, resolver)
    rows = db._conn.execute(
        "SELECT source_file, target_file FROM deps WHERE edge_kind = 'import'"
    ).fetchall()
    paths = {(r[0], r[1]) for r in rows}
    assert ("app/service.py", "app/util.py") in paths


def test_build_index_with_session_collects_tests(tmp_path):
    db_path = tmp_path / "index.sqlite"
    from helpers import collect_items

    items = collect_items(FIXTURE)
    build_index_with_session(FIXTURE, db_path, items)
    db = IndexDatabase(db_path)
    nodeids = db.all_test_nodeids()
    assert len(nodeids) == 2
    assert any("test_util" in n for n in nodeids)
    assert any("test_service" in n for n in nodeids)
    db.close()


def test_test_coverage_links_service_test(tmp_path):
    db_path = tmp_path / "index.sqlite"
    from helpers import collect_items

    items = collect_items(FIXTURE)
    build_index_with_session(FIXTURE, db_path, items)
    db = IndexDatabase(db_path)
    service_tests = [n for n in db.all_test_nodeids() if "test_service" in n]
    assert service_tests
    cov = db.test_coverage_map(service_tests)
    files = cov[service_tests[0]]
    assert "app/service.py" in files
    assert "app/util.py" in files
    db.close()


def test_rel_test_path_matches_nodeid_against_indexed_files(tmp_path):
    (tmp_path / "pkg" / "tests").mkdir(parents=True)
    test_file = tmp_path / "pkg" / "tests" / "test_x.py"
    test_file.write_text("def test_a(): pass\n")
    known = {"pkg/tests/test_x.py"}
    item = SimpleNamespace(
        nodeid="pkg/tests/test_x.py::test_a",
        path=None,
        fspath=None,
        location=None,
    )
    assert _rel_test_path(item, tmp_path, known) == "pkg/tests/test_x.py"


def test_rel_test_path_resolves_absolute_path_via_file_index(tmp_path):
    test_file = tmp_path / "tests" / "test_x.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_a(): pass\n")
    known = {"tests/test_x.py"}
    resolved = _resolved_file_index(tmp_path, known)
    item = SimpleNamespace(
        nodeid="tests/test_x.py::test_a",
        path=test_file.resolve(),
        fspath=None,
        location=None,
    )
    wrong_root = tmp_path / "other"
    wrong_root.mkdir()
    assert (
        _rel_test_path(item, wrong_root, known, resolved_index=resolved)
        == "tests/test_x.py"
    )


def test_index_tests_does_not_clear_when_nothing_maps(tmp_path):
    db_path = tmp_path / "index.sqlite"
    from helpers import collect_items

    items = collect_items(FIXTURE)
    build_index_with_session(FIXTURE, db_path, items)
    db = IndexDatabase(db_path)
    before = len(db.all_test_nodeids())

    bad_item = SimpleNamespace(
        nodeid="nowhere/test.py::test_x",
        path=None,
        fspath=None,
        location=None,
    )
    stats = index_tests_from_items(db, FIXTURE, [bad_item])
    assert stats.mapped == 0
    assert len(db.all_test_nodeids()) == before
    db.close()
