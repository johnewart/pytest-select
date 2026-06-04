"""pytest plugin hooks for indexing and diff-based selection."""

from __future__ import annotations

from pathlib import Path

import pytest

from pytest_select.index.builder import build_index_with_session
from pytest_select.select.selector import select_tests, write_select_report


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("select", "pytest-select: diff-based test selection")
    group.addoption(
        "--select-from-diff",
        action="store",
        default=None,
        metavar="REF",
        help="Git revision range (e.g. origin/main...HEAD) to select affected tests",
    )
    group.addoption(
        "--index-db",
        action="store",
        default=".pytest-select/index.sqlite",
        help="Path to SQLite index database",
    )
    group.addoption(
        "--reindex",
        action="store_true",
        default=False,
        help="Build or refresh the index, then exit without running tests",
    )
    group.addoption(
        "--select-report",
        action="store",
        default=None,
        metavar="PATH",
        help="Write JSON selection report to PATH",
    )
    group.addoption(
        "--select-safety-margin",
        action="store",
        type=int,
        default=2,
        help="Reverse dependency expansion depth (default: 2)",
    )
    group.addoption(
        "--select-fallback-percentile",
        action="store",
        type=float,
        default=0.0,
        help="Also run tests in top N%% impact percentile (e.g. 10)",
    )
    group.addoption(
        "--no-select-fallback-full-on-wide",
        action="store_true",
        default=False,
        help="Do not expand to full suite when conftest/__init__ under tests/ changed",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "select_always: always include this test in diff-based selection",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--reindex"):
        root = Path(config.rootpath)
        db_path = config.getoption("--index-db")
        db, stats = build_index_with_session(root, db_path, items)
        db.close()
        tr = config.pluginmanager.get_plugin("terminalreporter")
        message = stats.format_message()
        if tr is not None:
            if stats.mapped == 0 and stats.collected > 0:
                tr.write_line(message, red=True, bold=True)
            else:
                tr.write_line(message)
        if stats.mapped == 0 and stats.collected > 0:
            pytest.exit(message, returncode=1)
        items.clear()
        return

    diff_ref = config.getoption("--select-from-diff")
    if not diff_ref:
        return

    root = Path(config.rootpath)
    db_path = config.getoption("--index-db")
    selected, report = select_tests(
        diff_ref,
        db_path,
        root,
        safety_margin=config.getoption("--select-safety-margin"),
        fallback_percentile=config.getoption("--select-fallback-percentile"),
        fallback_full_on_wide=not config.getoption("--no-select-fallback-full-on-wide"),
    )

    report_path = config.getoption("--select-report")
    if report_path:
        write_select_report(report_path, report)

    always = set()
    for item in items:
        if item.get_closest_marker("select_always"):
            always.add(item.nodeid)

    selected |= always
    if not selected:
        return

    keep = [i for i in items if i.nodeid in selected]
    deselected = [i for i in items if i.nodeid not in selected]
    config.hook.pytest_deselected(items=deselected)
    items[:] = keep
