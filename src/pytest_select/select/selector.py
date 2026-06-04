"""Greedy set-cover test selection with impact/cost scoring."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pytest_select.db.queries import IndexDatabase
from pytest_select.select.diff import expand_affected_files, parse_git_diff
from pytest_select.select.explain import build_selection_details


def _greedy_set_cover(
    affected: set[str],
    candidates: set[str],
    coverage_map: dict[str, set[str]],
    scores: dict[str, tuple[float, float]],
) -> set[str]:
    """
    Pick tests until affected files are covered.
    score(t) = (|coverage ∩ affected| * impact(t)) / cost(t)
    """
    if not affected:
        return set()

    remaining = set(affected)
    selected: set[str] = set()
    available = set(candidates)

    while remaining and available:
        best: str | None = None
        best_score = -1.0

        for nodeid in available:
            cov = coverage_map.get(nodeid, set())
            hit = len(cov & remaining)
            if hit == 0:
                continue
            impact, cost = scores.get(nodeid, (50.0, 1.0))
            cost = max(cost, 0.1)
            s = (hit * (impact + 1.0)) / cost
            if s > best_score:
                best_score = s
                best = nodeid

        if best is None:
            break

        selected.add(best)
        available.discard(best)
        remaining -= coverage_map.get(best, set())

    # Uncovered affected files: add any candidate touching them
    if remaining:
        for nodeid in candidates:
            if nodeid in selected:
                continue
            if coverage_map.get(nodeid, set()) & remaining:
                selected.add(nodeid)
                remaining -= coverage_map.get(nodeid, set())
            if not remaining:
                break

    return selected


def _fallback_high_impact(
    all_scores: dict[str, tuple[float, float]],
    already: set[str],
    percentile: float,
) -> set[str]:
    """Include tests in top `percentile` impact percentile not already selected."""
    if percentile <= 0 or not all_scores:
        return set()
    threshold = 100.0 - percentile
    extra: set[str] = set()
    for nodeid, (impact, _) in all_scores.items():
        if nodeid in already:
            continue
        if impact >= threshold:
            extra.add(nodeid)
    return extra


def _nodeid_test_file(nodeid: str) -> str:
    return nodeid.split("::")[0].replace("\\", "/")


def _tests_in_scope(all_nodeids: set[str], scope_prefix: str) -> set[str]:
    norm = scope_prefix.replace("\\", "/")
    if not norm.endswith("/"):
        norm += "/"
    return {
        nodeid
        for nodeid in all_nodeids
        if _nodeid_test_file(nodeid).startswith(norm)
        or _nodeid_test_file(nodeid) == norm.rstrip("/")
    }


def _scoped_wide_blast_tests(all_nodeids: set[str], scopes: set[str]) -> set[str]:
    selected: set[str] = set()
    for scope in scopes:
        selected |= _tests_in_scope(all_nodeids, scope)
    return selected


def select_tests(
    diff_ref: str,
    db_path: str | Path,
    root: Path,
    *,
    safety_margin: int = 2,
    fallback_percentile: float = 0.0,
    fallback_full_on_wide: bool = True,
    detailed: bool = False,
) -> tuple[set[str], dict[str, Any]]:
    """
    Return (selected nodeids, report dict).
    Conftest/__init__ changes widen selection to all tests under that directory tree.
    """
    root = Path(root).resolve()
    db = IndexDatabase(db_path)
    db.init_schema()

    diff = parse_git_diff(diff_ref, root)
    report: dict[str, Any] = {
        "diff_ref": diff_ref,
        "changed_files": sorted(diff.changed_files),
        "changed_symbols": [list(x) for x in sorted(diff.changed_symbols)],
        "wide_blast_radius": diff.wide_blast_radius,
        "wide_blast_scopes": sorted(diff.wide_blast_scopes),
        "safety_margin": safety_margin,
    }

    all_nodeids = set(db.all_test_nodeids())
    if not all_nodeids:
        db.close()
        return set(), {**report, "error": "no tests in index; run --reindex first"}

    expansion_chains = db.explain_affected_chains(
        diff.changed_files, max_depth=safety_margin
    )

    wide_blast_tests: set[str] = set()
    if diff.wide_blast_scopes and fallback_full_on_wide:
        wide_blast_tests = _scoped_wide_blast_tests(
            all_nodeids, diff.wide_blast_scopes
        )
        report["wide_blast_test_count"] = len(wide_blast_tests)

    affected = expand_affected_files(diff, db, safety_margin=safety_margin)
    report["affected_files"] = sorted(affected)
    report["expansion_chains"] = {
        path: expansion_chains[path]
        for path in affected
        if path in expansion_chains
    }

    candidates = db.tests_touching_files(affected)
    if not candidates and affected:
        # Safety: no mapped tests — run tests in changed test paths + all under tests/
        for f in diff.changed_files:
            if f.startswith("tests/"):
                for nid in all_nodeids:
                    if (
                        nid.split("::")[0]
                        .replace("\\", "/")
                        .endswith(f.replace(".py", "").replace("/", "/") + ".py")
                        or f in nid
                    ):
                        candidates.add(nid)
        if not candidates:
            report["strategy"] = "full_suite_no_candidates"
            report["selected_count"] = len(all_nodeids)
            report["selected"] = sorted(all_nodeids)
            if detailed:
                report["selection_details"] = build_selection_details(
                    all_nodeids,
                    changed_files=diff.changed_files,
                    affected_files=affected,
                    expansion_chains=report["expansion_chains"],
                    coverage_map=db.test_coverage_map(all_nodeids),
                    fallback_tests=set(),
                    select_always_tests=set(),
                )
            db.close()
            return all_nodeids, report

    coverage_map = db.test_coverage_map(candidates)
    scores = db.test_scores(candidates)
    selected = _greedy_set_cover(affected, candidates, coverage_map, scores)
    selected |= wide_blast_tests

    fallback_tests: set[str] = set()
    if fallback_percentile > 0:
        all_scores = db.test_scores()
        fallback_tests = _fallback_high_impact(all_scores, selected, fallback_percentile)
        selected |= fallback_tests

    for f in diff.changed_files:
        for nid in all_nodeids:
            test_file = _nodeid_test_file(nid)
            if test_file == f or test_file.endswith("/" + f):
                selected.add(nid)

    if wide_blast_tests:
        report["strategy"] = "greedy_set_cover_with_scoped_blast"
    else:
        report["strategy"] = "greedy_set_cover"
    report["candidates_count"] = len(candidates)
    report["selected_count"] = len(selected)
    report["selected"] = sorted(selected)

    if detailed:
        full_coverage = db.test_coverage_map(selected)
        report["selection_details"] = build_selection_details(
            selected,
            changed_files=diff.changed_files,
            affected_files=affected,
            expansion_chains=report["expansion_chains"],
            coverage_map=full_coverage,
            fallback_tests=fallback_tests,
            select_always_tests=set(),
        )

    db.close()
    return selected, report


def write_select_report(path: str | Path, report: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(report, indent=2), encoding="utf-8")
