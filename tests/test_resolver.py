"""Import resolver tests."""

from pathlib import Path

from pytest_select.index.resolver import ImportResolver

from conftest import FIXTURE


def test_resolve_module_app_util():
    r = ImportResolver(FIXTURE)
    assert r.resolve_module("app.util") == "app/util.py"


def test_resolve_relative_import():
    r = ImportResolver(FIXTURE)
    source = FIXTURE / "app" / "service.py"
    assert r.resolve_module("util", level=1, relative_to=source) == "app/util.py"


def test_is_external_stdlib():
    r = ImportResolver(FIXTURE)
    assert r.is_external("os")
    assert not r.is_external("app.util")
