"""List GitHub Actions caches (optional fallback when manifest is missing)."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterator

_CACHE_KEY_RE = re.compile(r"^pytest-select-index-([0-9a-f]{40})$")


def list_index_cache_shas(
    repo: str,
    token: str,
    *,
    key_prefix: str = "pytest-select-index-",
    per_page: int = 100,
) -> set[str]:
    """
    Return full SHAs extracted from cache keys ``pytest-select-index-<sha>``.
    Requires ``repo`` as ``owner/name`` and a token with ``actions:read``.
    """
    shas: set[str] = set()
    page = 1
    while True:
        q = urllib.parse.urlencode(
            {"key": key_prefix, "per_page": per_page, "page": page}
        )
        url = f"https://api.github.com/repos/{repo}/actions/caches?{q}"
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError:
            break
        for entry in body.get("actions_caches", []):
            key = entry.get("key", "")
            m = _CACHE_KEY_RE.match(key)
            if m:
                shas.add(m.group(1))
        total = body.get("total_count", 0)
        if page * per_page >= total:
            break
        page += 1
    return shas


def repo_from_env() -> str | None:
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo and "/" in repo:
        return repo
    name = os.environ.get("GITHUB_REPOSITORY_NAME")
    if owner and name:
        return f"{owner}/{name}"
    return None
