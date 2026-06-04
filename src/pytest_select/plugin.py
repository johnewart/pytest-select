"""pytest plugin hooks for indexing and diff-based selection."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pytest_select.db.queries import IndexDatabase
from pytest_select.index.builder import build_index_with_session
from pytest_select.select.explain import format_selection_details
from pytest_select.select.selector import (
    select_tests,
    write_select_report,
)


def _select_modes_active(config: pytest.Config) -> bool:
    return bool(
        config.getoption("--reindex") or config.getoption("--select-from-diff")
    )


def _select_preview_mode(config: pytest.Config) -> bool:
    return bool(
        config.getoption("--select-from-diff") and config.getoption("--select-print")
    )


def _collection_errors(config: pytest.Config) -> list[str]:
    tracker = config.pluginmanager.get_plugin("pytest_select_collection_tracker")
    if tracker is None:
        return getattr(config, "_pytest_select_collection_errors", [])
    return tracker.errors


class _CollectionErrorTracker:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        if report.failed and report.nodeid:
            self.errors.append(report.nodeid)


def _run_selection(config: pytest.Config) -> tuple[set[str], dict, int]:
    """Return (selected nodeids, report dict, indexed test count)."""
    root = Path(config.rootpath)
    diff_ref = config.getoption("--select-from-diff")
    db_path = config.getoption("--index-db")
    detailed = config.getoption("--select-print-detailed")
    selected, report = select_tests(
        diff_ref,
        db_path,
        root,
        safety_margin=config.getoption("--select-safety-margin"),
        fallback_percentile=config.getoption("--select-fallback-percentile"),
        fallback_full_on_wide=not config.getoption("--no-select-fallback-full-on-wide"),
        detailed=detailed,
    )
    db = IndexDatabase(db_path)
    indexed_count = len(db.all_test_nodeids())
    db.close()
    return selected, report, indexed_count


def _emit_select_preview(
    config: pytest.Config,
    selected: set[str],
    report: dict,
    *,
    indexed_count: int | None = None,
    collected_count: int | None = None,
) -> None:
    if report.get("error"):
        pytest.exit(f"pytest-select: {report['error']}", returncode=1)

    report_path = config.getoption("--select-report")
    if report_path:
        write_select_report(report_path, report)

    detailed = config.getoption("--select-print-detailed")
    if detailed:
        sys.stdout.write(format_selection_details(report))
    else:
        for nodeid in sorted(selected):
            print(nodeid)

    total = collected_count if collected_count is not None else indexed_count
    if total is not None:
        print(
            f"pytest-select: would run {len(selected)} of {total} "
            f"{'collected' if collected_count is not None else 'indexed'} tests",
            file=sys.stderr,
        )


def _warn_collection_errors(config: pytest.Config) -> None:
    errors = _collection_errors(config)
    if not errors:
        return
    tr = config.pluginmanager.get_plugin("terminalreporter")
    if tr is None:
        return
    samples = ", ".join(errors[:3])
    extra = f" (+{len(errors) - 3} more)" if len(errors) > 3 else ""
    tr.write_line(
        f"pytest-select: skipped {len(errors)} module(s) with collection errors "
        f"(optional deps?) e.g. {samples}{extra}",
        yellow=True,
    )


def _warn_uncollectable_selected(
    config: pytest.Config, selected: set[str], items: list[pytest.Item]
) -> None:
    collected = {item.nodeid for item in items}
    missing = selected - collected
    if not missing:
        return
    tr = config.pluginmanager.get_plugin("terminalreporter")
    if tr is None:
        return
    samples = ", ".join(sorted(missing)[:3])
    extra = f" (+{len(missing) - 3} more)" if len(missing) > 3 else ""
    tr.write_line(
        f"pytest-select: {len(missing)} selected test(s) could not be collected "
        f"(missing optional deps?) e.g. {samples}{extra}",
        yellow=True,
    )


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
        "--select-print",
        action="store_true",
        default=False,
        help="Print selected test nodeids (one per line) and exit without running tests",
    )
    group.addoption(
        "--select-print-detailed",
        action="store_true",
        default=False,
        help="With --select-print, show changed→affected→test reasoning chains",
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
        help="Do not expand to all tests under a changed conftest/__init__ tree",
    )
    group.addoption(
        "--select-fail-on-collection-errors",
        action="store_true",
        default=False,
        help=(
            "Fail when test modules cannot be imported during collection "
            "(default: continue and skip unimportable modules during --reindex / "
            "--select-from-diff)"
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "select_always: always include this test in diff-based selection",
    )
    config._pytest_select_collection_errors = []  # noqa: SLF001
    if config.getoption("--select-print-detailed") and not config.getoption(
        "--select-from-diff"
    ):
        pytest.exit("--select-print-detailed requires --select-from-diff", returncode=2)
    if config.getoption("--select-print-detailed") and not config.getoption(
        "--select-print"
    ):
        pytest.exit(
            "--select-print-detailed requires --select-print",
            returncode=2,
        )
    needs_collection = _select_modes_active(config) and not _select_preview_mode(config)
    if needs_collection and not config.getoption("--select-fail-on-collection-errors"):
        config.option.continue_on_collection_errors = True
        tracker = _CollectionErrorTracker()
        config.pluginmanager.register(
            tracker, name="pytest_select_collection_tracker"
        )


def pytest_cmdline_main(config: pytest.Config) -> int | None:
    """Run selection from the index only; skip collection for --select-print."""
    if not _select_preview_mode(config):
        return None
    if config.getoption("--reindex") or config.getoption("--collectonly"):
        return None
    selected, report, indexed_count = _run_selection(config)
    _emit_select_preview(
        config, selected, report, indexed_count=indexed_count
    )
    return 0


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--reindex"):
        root = Path(config.rootpath)
        db_path = config.getoption("--index-db")
        db, stats = build_index_with_session(root, db_path, items)
        stats.collection_errors = list(_collection_errors(config))
        db.close()
        tr = config.pluginmanager.get_plugin("terminalreporter")
        message = stats.format_message()
        if tr is not None:
            if stats.mapped == 0 and stats.collected > 0:
                tr.write_line(message, red=True, bold=True)
            else:
                tr.write_line(message)
        config._pytest_select_reindex_mode = True  # noqa: SLF001
        if stats.mapped == 0 and stats.collected > 0:
            pytest.exit(message, returncode=1)
        items.clear()
        return

    diff_ref = config.getoption("--select-from-diff")
    if not diff_ref:
        return

    if _select_preview_mode(config):
        return

    _warn_collection_errors(config)

    selected, report, indexed_count = _run_selection(config)

    if report.get("error"):
        pytest.exit(f"pytest-select: {report['error']}", returncode=1)

    report_path = config.getoption("--select-report")
    if report_path:
        write_select_report(report_path, report)

    always = set()
    for item in items:
        if item.get_closest_marker("select_always"):
            always.add(item.nodeid)

    selected |= always
    _warn_uncollectable_selected(config, selected, items)

    if config.getoption("--select-print-detailed") and report.get(
        "selection_details"
    ) is not None:
        for nid in always:
            entry = report["selection_details"].setdefault(
                nid,
                {"reasons": [], "affected_hits": [], "hit_chains": {}},
            )
            if "marked select_always" not in entry["reasons"]:
                entry["reasons"].insert(0, "marked select_always")
        report["selected_count"] = len(selected)
        report["selected"] = sorted(selected)

    if config.getoption("--select-print"):
        config._pytest_select_print_mode = True  # noqa: SLF001
        _emit_select_preview(
            config,
            selected,
            report,
            collected_count=len(items),
        )
        items.clear()
        return

    if not selected:
        return

    keep = [i for i in items if i.nodeid in selected]
    deselected = [i for i in items if i.nodeid not in selected]
    config.hook.pytest_deselected(items=deselected)
    items[:] = keep


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config
    if getattr(config, "_pytest_select_print_mode", False):
        session.exitstatus = 0
        return
    if getattr(config, "_pytest_select_reindex_mode", False):
        session.exitstatus = 0
