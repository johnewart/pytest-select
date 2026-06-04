"""Human-readable selection explanations for --select-print-detailed."""

from __future__ import annotations

from typing import Any


def _format_chain(changed_files: set[str], chain: list[str]) -> str:
    if not chain:
        return ""
    if len(chain) == 1:
        if chain[0] in changed_files:
            return f"{chain[0]} (changed in git diff)"
        return chain[0]
    parts: list[str] = []
    for i, path in enumerate(chain):
        if i == 0:
            label = "changed in git diff" if path in changed_files else "seed"
            parts.append(f"{path} ({label})")
        else:
            prev = chain[i - 1]
            parts.append(f"{path} (imports {prev})")
    return " → ".join(parts)


def build_selection_details(
    selected: set[str],
    *,
    changed_files: set[str],
    affected_files: set[str],
    expansion_chains: dict[str, list[str]],
    coverage_map: dict[str, set[str]],
    fallback_tests: set[str],
    select_always_tests: set[str],
) -> dict[str, dict[str, Any]]:
    details: dict[str, dict[str, Any]] = {}
    for nodeid in sorted(selected):
        test_file = nodeid.split("::")[0].replace("\\", "/")
        hits = sorted(coverage_map.get(nodeid, set()) & affected_files)
        reasons: list[str] = []
        if nodeid in select_always_tests:
            reasons.append("marked select_always")
        if test_file in changed_files:
            reasons.append(f"test file changed ({test_file})")
        if nodeid in fallback_tests:
            reasons.append("fallback high-impact percentile")
        if hits:
            reasons.append(f"covers {len(hits)} affected file(s)")
        if not reasons:
            reasons.append("selected by set-cover / safety rule")

        details[nodeid] = {
            "reasons": reasons,
            "affected_hits": hits,
            "hit_chains": {
                path: expansion_chains.get(path, [path]) for path in hits
            },
        }
    return details


def format_selection_details(report: dict[str, Any]) -> str:
    lines: list[str] = []
    strategy = report.get("strategy", "unknown")
    lines.append(f"pytest-select: strategy={strategy}")
    lines.append(f"diff: {report.get('diff_ref', '')}")
    if report.get("error"):
        lines.append(f"error: {report['error']}")
        return "\n".join(lines)

    changed = list(report.get("changed_files", []))
    affected = list(report.get("affected_files", []))
    chains: dict[str, list[str]] = report.get("expansion_chains", {})
    changed_set = set(changed)

    lines.append("")
    lines.append(f"Git changed ({len(changed)}):")
    for path in changed:
        lines.append(f"  {path}")

    if strategy == "full_suite_no_candidates":
        lines.append("")
        lines.append(
            "Expanded to full suite: no indexed tests mapped to affected files."
        )
        lines.append(
            f"Selected all {report.get('selected_count', 0)} indexed/collected tests."
        )
        return "\n".join(lines) + "\n"

    scopes = report.get("wide_blast_scopes") or []
    if scopes and strategy == "greedy_set_cover_with_scoped_blast":
        lines.append("")
        lines.append(
            f"Scoped wide blast ({len(scopes)} conftest/__init__ path(s) changed):"
        )
        for scope in scopes:
            count = report.get("wide_blast_test_count", "?")
            lines.append(f"  {scope}*  (includes all tests under this tree)")
        if report.get("wide_blast_test_count") is not None:
            lines.append(
                f"  → {report['wide_blast_test_count']} tests from scoped blast"
            )

    lines.append("")
    lines.append(
        f"Affected files ({len(affected)}; reverse-import expansion depth "
        f"{report.get('safety_margin', 2)}):"
    )
    for path in affected:
        chain = chains.get(path, [path])
        lines.append(f"  {_format_chain(changed_set, chain)}")

    details: dict[str, dict[str, Any]] = report.get("selection_details", {})
    lines.append("")
    lines.append(
        f"Selected {report.get('selected_count', len(details))} tests "
        f"({report.get('candidates_count', '?')} candidates):"
    )
    lines.append("")

    for nodeid, info in details.items():
        lines.append(nodeid)
        for reason in info.get("reasons", []):
            lines.append(f"  • {reason}")
        for path in info.get("affected_hits", []):
            chain = info.get("hit_chains", {}).get(path, [path])
            lines.append(f"  • via {_format_chain(changed_set, chain)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
