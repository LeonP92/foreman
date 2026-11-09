import functools
import os
import re
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
NON_SOURCE_EXTENSIONS = frozenset(
    [
        ".md",
        ".rst",
        ".txt",
        ".json",
        ".jsonc",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".lock",
        ".csv",
        ".tsv",
        ".xml",
        ".html",
        ".htm",
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".svg",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".webp",
        ".pdf",
        ".sql",
        ".tf",
        ".tfvars",
        ".env",
        ".example",
        ".sample",
        ".gitignore",
        ".gitattributes",
        ".editorconfig",
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
        errors="surrogateescape",
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


@functools.cache
def _glob_re(glob: str) -> re.Pattern:
    """Gitignore-style: `*` and `?` stay in one folder, `**` crosses folders, no `/` = any depth."""
    out = "" if "/" in glob else "(?:.*/)?"
    for tok in re.findall(
        r"/\*\*$|\*\*/|\*\*|\*|\?|\[!?[^]]*\]|.", glob.removeprefix("/"), re.DOTALL
    ):
        out += {
            "/**": "(?:/.*)?",
            "**/": "(?:.*/)?",
            "**": ".*",
            "*": "[^/]*",
            "?": "[^/]",
        }.get(tok) or (
            "[" + tok[1:-1].replace("!", "^", 1) + "]" if tok[:1] == "[" else re.escape(tok)
        )
    return re.compile(out)


def is_ignored(path: str, ignore: Sequence[str]) -> bool:
    return any(_glob_re(g).fullmatch(path) for g in ignore)


def is_utf8(path: str) -> bool:
    try:
        path.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def list_files(root: Path, ignore: Sequence[str] = ()) -> list[str]:
    paths = _git_files(root)
    if paths is None:
        paths = _walk_files(root)
    # a name that isn't UTF-8 decodes with surrogates; it can't be reported, so it is skipped
    return sorted(p for p in paths if is_utf8(p) and not is_ignored(p, ignore))


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


def source_texts(root: Path, ignore: Sequence[str] = ()) -> dict[str, str]:
    texts = {}
    for path in list_files(root, ignore):
        if Path(path).suffix in NON_SOURCE_EXTENSIONS:
            continue
        text = read_text(root / path)
        if text is not None:
            texts[path] = text
    return texts
