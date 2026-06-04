"""Cache manifest: maps commit SHAs to indexed database metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_VERSION = 1


@dataclass
class ManifestEntry:
    sha: str
    recorded_at: str
    index_db: str = ".pytest-select/index.sqlite"

    @classmethod
    def from_dict(cls, sha: str, data: dict[str, Any]) -> ManifestEntry:
        return cls(
            sha=sha,
            recorded_at=data.get("recorded_at", ""),
            index_db=data.get("index_db", ".pytest-select/index.sqlite"),
        )


class CacheManifest:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, ManifestEntry]:
        if not self.path.is_file():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("version") != MANIFEST_VERSION:
            return {}
        entries: dict[str, ManifestEntry] = {}
        for sha, raw in (data.get("entries") or {}).items():
            entries[sha] = ManifestEntry.from_dict(sha, raw)
        return entries

    def save(self, entries: dict[str, ManifestEntry]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": MANIFEST_VERSION,
            "entries": {
                sha: {
                    "recorded_at": e.recorded_at,
                    "index_db": e.index_db,
                }
                for sha, e in sorted(entries.items())
            },
        }
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def record(self, sha: str, index_db: str = ".pytest-select/index.sqlite") -> None:
        entries = self.load()
        entries[sha] = ManifestEntry(
            sha=sha,
            recorded_at=datetime.now(timezone.utc).isoformat(),
            index_db=index_db,
        )
        self.save(entries)

    def known_shas(self) -> set[str]:
        return set(self.load().keys())
