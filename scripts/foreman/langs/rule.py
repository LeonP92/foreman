import posixpath
import re
from collections.abc import Sequence
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


def check(root: Path, rule: Rule, ignore: Sequence[str] = ()) -> dict:
    files = list_files(root, ignore)
    index = make_index(root, files)
    covered = [p for p in files if posixpath.splitext(p)[1] in rule["extensions"]]
    matches = resolved = 0
    examples = []
    for path in covered:
        for capture in _captures(read_text(root / path) or "", rule):
            matches += 1
            if _resolve(path, capture, index, rule):
                resolved += 1
            elif len(examples) < 5:
                examples.append({"import": capture, "path": path})
    return {
        "files": len(covered),
        "matches": matches,
        "resolved": resolved,
        # below half resolved, the graph is so sparse most files would look dead
        "ok": bool(covered) and matches > 0 and resolved / matches >= 0.5,
        "unresolved_examples": examples,
    }
