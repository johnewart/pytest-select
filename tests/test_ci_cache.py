"""CI cache manifest and ancestry resolution tests."""

from __future__ import annotations

import json
from pathlib import Path

from pytest_select.ci.manifest import CacheManifest, MANIFEST_VERSION
from pytest_select.ci.resolve import find_nearest_cached_ancestor


def test_manifest_record_and_load(tmp_path):
    path = tmp_path / "manifest.json"
    m = CacheManifest(path)
    m.record("a" * 40)
    loaded = m.load()
    assert len(loaded) == 1
    assert "a" * 40 in loaded


def test_find_nearest_cached_ancestor_picks_closest(tmp_path, monkeypatch):
    shas = ["cccc", "bbbb", "aaaa"]
    available = {"bbbb", "dddd"}

    monkeypatch.setattr(
        "pytest_select.ci.resolve.resolve_head",
        lambda head, cwd=None: "cccc",
    )
    monkeypatch.setattr(
        "pytest_select.ci.resolve.rev_list",
        lambda start, cwd=None, max_count=None, first_parent=False: shas,
    )

    hit = find_nearest_cached_ancestor("HEAD", available, cwd=tmp_path)
    assert hit == "bbbb"


def test_find_nearest_includes_head_when_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "pytest_select.ci.resolve.resolve_head",
        lambda head, cwd=None: "headsha",
    )
    monkeypatch.setattr(
        "pytest_select.ci.resolve.rev_list",
        lambda *a, **k: ["headsha", "parent"],
    )
    hit = find_nearest_cached_ancestor("HEAD", {"headsha"})
    assert hit == "headsha"


def test_manifest_version_guard(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"version": 999, "entries": {}}), encoding="utf-8")
    assert CacheManifest(path).known_shas() == set()
