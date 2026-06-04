"""Find the nearest ancestor commit that has a pytest-select index cache."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from pytest_select.ci.git import merge_base, resolve_head, rev_list
from pytest_select.ci.github_api import list_index_cache_shas, repo_from_env
from pytest_select.ci.manifest import CacheManifest

CACHE_KEY_PREFIX = "pytest-select-index-"


@dataclass
class CacheResolution:
    hit: bool
    head_sha: str
    cache_sha: str | None
    cache_key: str | None
    source: str  # manifest | github-api | none

    def as_github_output(self) -> dict[str, str]:
        return {
            "cache_hit": "true" if self.hit else "false",
            "cache_sha": self.cache_sha or "",
            "cache_key": self.cache_key or "",
            "cache_source": self.source,
            "head_sha": self.head_sha,
        }


def find_nearest_cached_ancestor(
    head: str,
    available_shas: set[str],
    *,
    cwd: Path | None = None,
    base: str | None = None,
    first_parent: bool = False,
    max_commits: int | None = 5000,
) -> str | None:
    """
    Walk ancestry from head (inclusive) and return the first SHA present in available_shas.
    If base is set, only consider commits after merge-base(base, head) on the path to head.
    """
    if not available_shas:
        return None
    head_full = resolve_head(head, cwd=cwd)
    if head_full in available_shas:
        return head_full
    commits = rev_list(
        head_full,
        cwd=cwd,
        max_count=max_commits,
        first_parent=first_parent,
    )
    if base:
        mb = merge_base(base, head_full, cwd=cwd)
        if mb:
            try:
                boundary = commits.index(mb)
                commits = commits[:boundary]
            except ValueError:
                pass
    for sha in commits:
        if sha in available_shas:
            return sha
    return None


def resolve_cache(
    head: str,
    manifest_path: Path,
    *,
    cwd: Path | None = None,
    base: str | None = None,
    use_github_api: bool = False,
    github_token: str | None = None,
    github_repo: str | None = None,
    first_parent: bool = False,
) -> CacheResolution:
    head_full = resolve_head(head, cwd=cwd)
    manifest = CacheManifest(manifest_path)
    available = manifest.known_shas()
    source = "manifest"

    if not available and use_github_api:
        token = github_token or os.environ.get("GITHUB_TOKEN")
        repo = github_repo or repo_from_env()
        if token and repo:
            available = list_index_cache_shas(repo, token)
            source = "github-api"

    hit_sha = find_nearest_cached_ancestor(
        head_full,
        available,
        cwd=cwd,
        base=base,
        first_parent=first_parent,
    )
    if hit_sha:
        return CacheResolution(
            hit=True,
            head_sha=head_full,
            cache_sha=hit_sha,
            cache_key=f"{CACHE_KEY_PREFIX}{hit_sha}",
            source=source,
        )
    return CacheResolution(
        hit=False,
        head_sha=head_full,
        cache_sha=None,
        cache_key=None,
        source="none",
    )


def _write_github_output(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for k, v in values.items():
            if "\n" in v:
                delim = f"pyselect_{k}"
                f.write(f"{k}<<{delim}\n{v}\n{delim}\n")
            else:
                f.write(f"{k}={v}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Find nearest ancestor commit with a pytest-select index cache",
    )
    parser.add_argument(
        "--head",
        default="HEAD",
        help="Commit to start from (default: HEAD)",
    )
    parser.add_argument(
        "--base",
        default=None,
        help="Optional base ref; only search commits on the path from merge-base(base, head) to head",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("cache-metadata/pytest-select-manifest.json"),
        help="Path to cache manifest JSON",
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        default=None,
        help="Git repository root (default: current directory)",
    )
    parser.add_argument(
        "--first-parent",
        action="store_true",
        help="Walk only first-parent chain (matches typical mainline CI)",
    )
    parser.add_argument(
        "--github-api",
        action="store_true",
        help="If manifest is empty, query GitHub Actions caches API",
    )
    parser.add_argument(
        "--github-output",
        type=Path,
        default=None,
        help="Append key=value outputs for GitHub Actions (GITHUB_OUTPUT)",
    )
    parser.add_argument(
        "--format",
        choices=("text", "github"),
        default="text",
        help="text: human lines; github: key=value on stdout for GITHUB_OUTPUT",
    )
    args = parser.parse_args(argv)

    try:
        result = resolve_cache(
            args.head,
            args.manifest,
            cwd=args.cwd,
            base=args.base,
            use_github_api=args.github_api,
            first_parent=args.first_parent,
        )
    except subprocess.CalledProcessError as e:  # type: ignore[name-defined]
        print(f"git error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    outputs = result.as_github_output()
    if args.github_output:
        _write_github_output(args.github_output, outputs)
    if args.format == "github":
        for k, v in outputs.items():
            print(f"{k}={v}")
    else:
        if result.hit:
            print(f"cache_hit=true cache_sha={result.cache_sha} cache_key={result.cache_key}")
        else:
            print("cache_hit=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
