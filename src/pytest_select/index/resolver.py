"""Import resolution relative to project root."""

from __future__ import annotations

import sys
from pathlib import Path


class ImportResolver:
    """Resolve dotted module names to project-relative file paths."""

    def __init__(self, root: Path, extra_paths: list[Path] | None = None) -> None:
        self.root = root.resolve()
        self._search_roots = [self.root]
        if extra_paths:
            self._search_roots.extend(p.resolve() for p in extra_paths)
        self._stdlib = (
            set(sys.stdlib_module_names)
            if hasattr(sys, "stdlib_module_names")
            else set()
        )

    def is_external(self, module: str | None) -> bool:
        if not module:
            return True
        top = module.split(".")[0]
        return top in self._stdlib or top in ("pytest", "_pytest")

    def resolve_module(
        self, module: str, level: int = 0, relative_to: Path | None = None
    ) -> str | None:
        """
        Return project-relative path (posix) for module, or None if external/unresolved.
        level > 0 is relative import from relative_to's package.
        """
        if level > 0 and relative_to is not None:
            pkg = self._package_for_file(relative_to)
            if pkg is None:
                return None
            parts = pkg.split(".") if pkg else []
            ups = level - 1
            if ups > len(parts):
                return None
            base_parts = parts[: len(parts) - ups] if ups else parts
            if module:
                full = ".".join([*base_parts, *module.split(".")])
            else:
                full = ".".join(base_parts)
        else:
            full = module or ""
            if self.is_external(full):
                return None

        return self._module_to_path(full)

    def _package_for_file(self, path: Path) -> str | None:
        rel = self._relative_path(path)
        if rel is None:
            return None
        parts = list(rel.with_suffix("").parts)
        if parts[-1] == "__init__":
            return ".".join(parts[:-1]) if len(parts) > 1 else ""
        if len(parts) > 1:
            return ".".join(parts[:-1])
        return ""

    def _relative_path(self, path: Path) -> Path | None:
        try:
            return path.resolve().relative_to(self.root)
        except ValueError:
            return None

    def _module_to_path(self, module: str) -> str | None:
        parts = module.split(".")
        for root in self._search_roots:
            # package/__init__.py
            pkg_init = root.joinpath(*parts, "__init__.py")
            if pkg_init.is_file():
                try:
                    return pkg_init.relative_to(self.root).as_posix()
                except ValueError:
                    continue
            # module.py
            mod_py = root.joinpath(*parts).with_suffix(".py")
            if mod_py.is_file():
                try:
                    return mod_py.relative_to(self.root).as_posix()
                except ValueError:
                    continue
            # nested package: try trimming to find longest match
            for i in range(len(parts), 0, -1):
                sub = parts[:i]
                candidate = root.joinpath(*sub).with_suffix(".py")
                if candidate.is_file():
                    try:
                        return candidate.relative_to(self.root).as_posix()
                    except ValueError:
                        continue
        return None

    def path_to_module(self, path: Path) -> str | None:
        rel = self._relative_path(path)
        if rel is None:
            return None
        parts = list(rel.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) if parts else None
