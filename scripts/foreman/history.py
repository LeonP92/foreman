import shutil
import subprocess
from collections import Counter
from collections.abc import Sequence
from itertools import combinations
from pathlib import Path

from .files import is_ignored

HISTORY_COMMITS = 500
BULK_COMMIT_FILES = 30


def _empty(note: str) -> dict:
    return {
        "window": {"commits": 0, "first": None, "last": None},
        "churn": {},
        "pairs": [],
        "note": note,
    }


def _commits(root: Path) -> tuple[list[tuple[str, list[str]]], str | None]:
    git = shutil.which("git")
    if git is None:
        return [], "git not found"
    result = subprocess.run(
        [
            git,
            "log",
            "--no-merges",
            "-n",
            str(HISTORY_COMMITS),
            "-z",
            "--format=%x01%H",
            "--name-only",
            "--relative",
        ],
        check=False,
        cwd=root,
        capture_output=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        return [], "not a git repository or no commits"
    commits = []
    for record in result.stdout.split("\x01")[1:]:
        sha, _, rest = record.partition("\0")
        commits.append((sha, [p for p in rest.removeprefix("\n").split("\0") if p]))
    return commits, None


def analyse(root: Path, ignore: Sequence[str] = ()) -> dict:
    commits, note = _commits(root)
    if not commits:
        return _empty(note or "no commits")
    churn: Counter[str] = Counter()
    both: Counter[tuple[str, str]] = Counter()
    for _, paths in commits:
        if len(paths) > BULK_COMMIT_FILES:
            continue
        kept = sorted({p for p in paths if not is_ignored(p, ignore)})
        churn.update(kept)
        both.update(combinations(kept, 2))
    pairs = [
        {"a": a, "b": b, "both": n, "conf": round(n / min(churn[a], churn[b]), 2)}
        for (a, b), n in both.items()
        if n >= 2
    ]
    pairs.sort(key=lambda p: (-p["conf"], p["a"], p["b"]))
    window = {"commits": len(commits), "first": commits[-1][0], "last": commits[0][0]}
    return {"window": window, "churn": dict(sorted(churn.items())), "pairs": pairs, "note": None}
