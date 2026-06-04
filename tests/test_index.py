"""Index builder tests."""

from __future__ import annotations

import pytest

from pytest_select.db.queries import IndexDatabase
from pytest_select.index.builder import build_index_with_session, index_source_files
from pytest_select.index.resolver import ImportResolver

from conftest import FIXTURE


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
