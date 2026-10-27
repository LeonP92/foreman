import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path

from foreman.files import read_text


@dataclass(frozen=True)
class RepoIndex:
    root: Path
    files: frozenset[str]
    go_module: str | None
    go_packages: frozenset[str]
    python_roots: tuple[str, ...]
    # per-build cache of package `__init__.py` re-exports, filled by the Python language
    python_reexports: dict[str, dict[str, str]] = field(default_factory=dict, compare=False)


def make_index(root: Path, files: list[str]) -> RepoIndex:
    go_mod = root / "go.mod"
    # shortcut: only the root go.mod is read; multi-module repos resolve just that module
    match = go_mod.is_file() and re.search(
        r"^module\s+(\S+)", read_text(go_mod) or "", re.MULTILINE
    )
    return RepoIndex(
        root=root,
        files=frozenset(files),
        go_module=match.group(1) if match else None,
        go_packages=frozenset(go_package(f) for f in files if f.endswith(".go")),
        python_roots=_python_roots(files),
    )


def _python_roots(files: list[str]) -> tuple[str, ...]:
    """Repo root, `src`, and every non-package dir that directly holds a package."""
    packages = {posixpath.dirname(f) for f in files if posixpath.basename(f) == "__init__.py"}
    roots = {posixpath.dirname(p) for p in packages} - packages
    return tuple(sorted(roots | {"", "src"}, key=lambda r: (len(r), r)))


def go_package(path: str) -> str:
    return path.rpartition("/")[0] or "."
