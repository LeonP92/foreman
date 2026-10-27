import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path

from foreman.files import source_texts
from foreman.smells import THRESHOLDS

DUPE_WINDOW = int(THRESHOLDS["duplicate_min_lines"])
# Languages where `#` starts a comment; elsewhere (C/C++ preprocessor) `#` lines are code.
_HASH_COMMENT_EXTENSIONS = frozenset(
    [".py", ".pyi", ".rb", ".sh", ".bash", ".zsh", ".fish", ".pl", ".r"]
)
_NOISE = re.compile(r"^([\s{}()\[\];,]*|(import|from|using|package|#\s*include|#\s*import)\b.*)$")


def _normalised(path: str, text: str) -> list[tuple[int, str]]:
    comments = ("#", "//") if Path(path).suffix.lower() in _HASH_COMMENT_EXTENSIONS else ("//",)
    lines = []
    for number, raw in enumerate(text.split("\n"), 1):
        line = " ".join(raw.split())
        if line and not line.startswith(comments):
            lines.append((number, line))
    return lines


def _non_overlapping(locs: list[tuple[str, int]]) -> list[tuple[str, int]]:
    kept: list[tuple[str, int]] = []
    for path, k in sorted(locs):
        if not kept or kept[-1][0] != path or k >= kept[-1][1] + DUPE_WINDOW:
            kept.append((path, k))
    return kept


def find(root: Path, ignore: Sequence[str] = ()) -> dict:
    lines = {p: _normalised(p, t) for p, t in source_texts(root, ignore).items()}
    def windows():
        for path, norm in lines.items():
            for k in range(len(norm) - DUPE_WINDOW + 1):
                yield path, k, tuple(text for _, text in norm[k : k + DUPE_WINDOW])

    # count hashes first, so only windows seen twice ever get a location list
    seen = Counter(hash(window) for _, _, window in windows())
    groups = defaultdict(list)
    for path, k, window in windows():
        if seen[hash(window)] > 1:
            groups[window].append((path, k))
    locs = {}
    for members in groups.values():
        kept = _non_overlapping(members)
        if len(kept) > 1:
            for member in kept:
                locs[member] = frozenset(kept)

    blocks = {}
    for (path, k), group in sorted(locs.items()):
        before = locs.get((path, k - 1))
        if before and frozenset((p, i + 1) for p, i in before) == group:
            continue
        run, tail = 1, group
        while (nxt := locs.get((path, k + run))) and frozenset((p, i + 1) for p, i in tail) == nxt:
            tail = nxt
            run += 1
        size = run + DUPE_WINDOW - 1
        noisy = sum(1 for _, t in lines[path][k : k + size] if _NOISE.match(t))
        if noisy * 2 > size:
            continue
        blocks[group] = size
    result = []
    for group, size in blocks.items():
        locations = [
            {"path": p, "start": lines[p][i][0], "end": lines[p][i + size - 1][0]}
            for p, i in sorted(group)
        ]
        result.append({"lines": size, "locations": locations})
    result.sort(key=lambda b: (-b["lines"], b["locations"][0]["path"], b["locations"][0]["start"]))
    return {"blocks": result}
