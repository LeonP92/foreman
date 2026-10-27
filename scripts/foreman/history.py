import posixpath
import shutil
import subprocess
from collections import Counter
from collections.abc import Sequence
from itertools import combinations
from pathlib import Path

from .files import NON_SOURCE_EXTENSIONS, is_ignored, list_files
from .metrics import percentiles
from .smells import THRESHOLDS

HISTORY_COMMITS = 500


def _empty(note: str) -> dict:
    return {
        "window": {"commits": 0, "first": None, "last": None},
        "churn": {},
        "recent_churn": {},
        "pairs": [],
        "note": note,
    }


def _commits(root: Path) -> tuple[list[tuple[str, int, list[str]]], str | None]:
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
            "--format=%x01%H %ct",
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
        head, _, rest = record.partition("\0")
        sha, stamp = head.split(" ")
        commits.append((sha, int(stamp), [p for p in rest.removeprefix("\n").split("\0") if p]))
    return commits, None


def analyse(root: Path, ignore: Sequence[str] = ()) -> dict:
    commits, note = _commits(root)
    if not commits:
        return _empty(note or "no commits")
    sources = sum(
        1
        for p in list_files(root, ignore)
        if posixpath.splitext(p)[1].lower() not in ("", *NON_SOURCE_EXTENSIONS)
    )
    # A sweep (format, rename, licence header) or a large squashed feature touches far more
    # files than a normal commit and says nothing about coupling.
    bulk = min(
        max(THRESHOLDS["bulk_commit_min_files"], THRESHOLDS["bulk_commit_share"] * sources),
        max(THRESHOLDS["bulk_commit_min_files"], percentiles([len(p) for *_, p in commits])["p90"]),
    )
    # relative to the newest commit, so an old checkout still has hotspots
    since = max(stamp for _, stamp, _ in commits) - THRESHOLDS["hotspot_window_days"] * 86400
    churn: Counter[str] = Counter()
    recent: Counter[str] = Counter()
    both: Counter[tuple[str, str]] = Counter()
    for _, stamp, paths in commits:
        if len(paths) > bulk:
            continue
        kept = sorted({p for p in paths if not is_ignored(p, ignore)})
        churn.update(kept)
        if stamp >= since:
            recent.update(kept)
        both.update(combinations(kept, 2))
    pairs = [
        {"a": a, "b": b, "both": n, "conf": round(n / min(churn[a], churn[b]), 2)}
        for (a, b), n in both.items()
        if n >= 2
    ]
    pairs.sort(key=lambda p: (-p["conf"], p["a"], p["b"]))
    window = {"commits": len(commits), "first": commits[-1][0], "last": commits[0][0]}
    return {
        "window": window,
        "churn": dict(sorted(churn.items())),
        "recent_churn": dict(sorted(recent.items())),
        "pairs": pairs,
        "note": None,
    }
