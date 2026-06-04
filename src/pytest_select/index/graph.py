"""Graph BFS utilities for forward reachability from test files."""

from __future__ import annotations

from collections import deque
from typing import Callable


def forward_reachable(
    start_files: set[str],
    neighbors: Callable[[str], set[str]],
    max_depth: int = 50,
) -> dict[str, int]:
    """
    BFS from start_files following forward deps (imports).
    Returns file -> minimum depth from any start.
    """
    depths: dict[str, int] = {}
    queue: deque[tuple[str, int]] = deque()
    for f in start_files:
        depths[f] = 0
        queue.append((f, 0))

    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for nxt in neighbors(current):
            nd = depth + 1
            if nxt not in depths or nd < depths[nxt]:
                depths[nxt] = nd
                queue.append((nxt, nd))
    return depths


def build_forward_neighbor_fn(conn) -> Callable[[str], set[str]]:
    """Return callable: file -> set of target files it imports."""

    def neighbors(source_file: str) -> set[str]:
        rows = conn.execute(
            "SELECT DISTINCT target_file FROM deps WHERE source_file = ? AND edge_kind = 'import'",
            (source_file,),
        ).fetchall()
        return {r[0] for r in rows}

    return neighbors
