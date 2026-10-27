import fnmatch
import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

SKIP_DIRS = frozenset(
    [
        ".git",
        "node_modules",
        "dist",
        "build",
        ".venv",
        "venv",
        "vendor",
        "__pycache__",
        ".next",
        "coverage",
        "target",
    ]
)
LANGUAGES = {
    ".py": "python",
    ".ts": "javascript",
    ".tsx": "javascript",
    ".mts": "javascript",
    ".cts": "javascript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
}


def _git_files(root: Path) -> list[str] | None:
    git = shutil.which("git")
    if git is None:
        return None
    result = subprocess.run(
        [git, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        check=False,
        cwd=root,
        capture_output=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        return None
    return [p for p in result.stdout.split("\0") if p and (root / p).is_file()]


def _walk_files(root: Path) -> list[str]:
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            found.append((Path(dirpath) / name).relative_to(root).as_posix())
    return found


def list_files(root: Path, ignore: Sequence[str] = ()) -> list[str]:
    paths = _git_files(root)
    if paths is None:
        paths = _walk_files(root)
    return sorted(
        p
        for p in paths
        if not any(fnmatch.fnmatchcase(p, g) or fnmatch.fnmatchcase("/" + p, g) for g in ignore)
    )


def language(path: str) -> str | None:
    return LANGUAGES.get(Path(path).suffix)


def read_text(path: Path) -> str | None:
    data = path.read_bytes()
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeDecodeError:
        return None
