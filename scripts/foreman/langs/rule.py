import posixpath
import re
from collections.abc import Iterator, Sequence
from itertools import islice
from pathlib import Path
from typing import TypedDict

from foreman.files import list_files, read_text
from foreman.langs import RepoIndex, make_index

BUILTINS = frozenset(["python", "javascript", "go"])
KEYS = ("extensions", "pattern", "resolve")


class Rule(TypedDict):
    extensions: list[str]
    pattern: str
    resolve: list[str]


def validate(name: str, rule: dict) -> list[str]:
    if not isinstance(rule, dict):
        return ["must be a table"]
    errors = [f"missing key {key!r}" for key in KEYS if key not in rule]
    errors += [f"unknown key {key!r}" for key in rule if key not in KEYS]
    if name in BUILTINS:
        errors.append(f"{name!r} is a built-in language")
    for key in ("extensions", "resolve"):
        value = rule.get(key, [""])
        if not (isinstance(value, list) and value and all(isinstance(v, str) for v in value)):
            errors.append(f"{key} must be a non-empty list of strings")
    if not isinstance(rule.get("pattern", ""), str):
        errors.append("pattern must be a string")
    elif "pattern" in rule:
        try:
            if re.compile(rule["pattern"]).groups < 1:
                errors.append("pattern has no group 1")
        except re.error as exc:
            errors.append(f"pattern does not compile: {exc}")
    return errors


def _resolve(path: str, capture: str, index: RepoIndex, rule: Rule) -> str | None:
    values = {
        "{dir}": posixpath.dirname(path) or ".",
        "{1}": capture,
        "{1|path}": capture.replace("::", "/").replace(".", "/"),
    }
    for template in rule["resolve"]:
        candidate = template
        for placeholder, value in values.items():
            candidate = candidate.replace(placeholder, value)
        # index membership also drops anything normalising outside the repo
        candidate = posixpath.normpath(candidate)
        if candidate in index.files:
            return candidate
    return None


def _captures(text: str, rule: Rule) -> list[str]:
    return [m.group(1) for m in re.finditer(rule["pattern"], text, re.MULTILINE)]


def imports(path: str, text: str, index: RepoIndex, rule: Rule) -> list[tuple[str, bool]]:
    found = [_resolve(path, capture, index, rule) for capture in _captures(text, rule)]
    return [(target, False) for target in found if target]


# The first literal word of a pattern (`require_relative`, `import`); `\s`, `\w` are skipped.
# shortcut: a named group `(?P<x>...)` before the keyword yields the group name; fine for the
# import patterns setup writes.
_KEYWORD = re.compile(r"(?<![\\\w])[A-Za-z_]\w+")


def _unmatched(text: str, rule: Rule) -> Iterator[str]:
    """Lines holding the pattern's keyword as a word that the pattern doesn't match."""
    keyword = _KEYWORD.search(rule["pattern"])
    if keyword is None:
        return
    word = re.compile(rf"\b{keyword[0]}\b")
    for line in text.split("\n"):
        if word.search(line) and not re.search(rule["pattern"], line, re.MULTILINE):
            yield line.strip()


def check(root: Path, rule: Rule, ignore: Sequence[str] = ()) -> dict:
    files = list_files(root, ignore)
    index = make_index(root, files)
    stems = {posixpath.splitext(posixpath.basename(p))[0] for p in files}
    covered = [p for p in files if posixpath.splitext(p)[1] in rule["extensions"]]
    matches = resolved = 0
    examples = []
    externals = []
    unmatched = []
    for path in covered:
        text = read_text(root / path) or ""
        for capture in _captures(text, rule):
            matches += 1
            if _resolve(path, capture, index, rule):
                resolved += 1
            # A capture no part of which names a repo file (`json`, `java.util.List`) is a library
            # import. Any repo path a capture spells ends in a file stem, so checking segments
            # covers relative paths too; a missing relative file can still land here, so
            # `external_examples` shows what was counted.
            elif stems.isdisjoint(re.split(r"[./:]+", capture)):
                externals.append({"import": capture, "path": path})
            elif len(examples) < 5:
                examples.append({"import": capture, "path": path})
        lines = islice(_unmatched(text, rule), 5 - len(unmatched))
        unmatched += [{"line": line, "path": path} for line in lines]
    internal = matches - len(externals)
    return {
        "files": len(covered),
        "matches": matches,
        "resolved": resolved,
        "external": len(externals),
        "external_examples": externals[:5],
        # below half resolved, the graph is so sparse most files would look dead
        "ok": bool(covered) and internal > 0 and resolved / internal >= 0.5,
        "unresolved_examples": examples,
        "unmatched_examples": unmatched,
    }
