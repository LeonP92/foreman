"""Repo-wide structural smells from the import graph, git history, sizes and duplicates."""

import ast
import fnmatch
import json
import posixpath
import re
import tomllib
from collections.abc import Collection, Iterable, Sequence
from pathlib import Path
from typing import TypedDict

from foreman.files import NON_SOURCE_EXTENSIONS, is_ignored, read_text
from foreman.langs import go_package
from foreman.metrics import percentiles

THRESHOLDS: dict[str, int | float] = {
    "hub_floor": 8,
    "cochange_min_both": 5,
    "cochange_min_conf": 0.6,
    "cochange_medium_conf": 0.8,
    "hotspot_min_churn": 5,
    "oversize_file_median_ratio": 3,
    "oversize_file_floor": 300,
    "oversize_function_floor": 60,
    "duplicate_medium_lines": 20,
    "duplicate_medium_locations": 3,
}
MAX_PER_KIND = 20
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
# __init__.py is imported implicitly with its package, so no edge ever points at it
ENTRY_NAMES = frozenset(
    ["__init__.py", "__main__.py", "main.py", "cli.py", "manage.py", "conftest.py", "setup.py"]
)
ENTRY_GLOBS = ("index.*", "*.config.*")
# Files a framework loads by path, so nothing imports them; `[audit] entry_points` adds more.
PATH_LOADED_GLOBS = ("**/migrations/**", "**/alembic/versions/**")
TEST_DIRS = frozenset(["test", "tests", "__tests__", "spec"])


class Smell(TypedDict):
    kind: str
    severity: str
    nodes: list[str]
    title: str
    evidence: str


def _subject(path: str) -> str:
    stem = posixpath.splitext(posixpath.basename(path))[0]
    stem = stem.removeprefix("test_")
    for suffix in ("_test", ".test", ".spec"):
        stem = stem.removesuffix(suffix)
    return stem


def _is_test(path: str) -> bool:
    stem = posixpath.splitext(posixpath.basename(path))[0]
    return _subject(path) != stem or not TEST_DIRS.isdisjoint(path.split("/")[:-1])


def folder_parts(node: dict) -> list[str]:
    """Directory parts of a graph node (a Go node is already its package directory)."""
    folder = node["id"] if node["lang"] == "go" else posixpath.dirname(node["id"])
    return [] if folder in ("", ".") else folder.split("/")


def map_nodes(graph: dict, metrics: dict) -> dict[str, str]:
    """Node id -> language: graph nodes, plus measured files in languages with no import graph."""
    nodes = {n["id"]: n["lang"] for n in graph["nodes"]}
    for f in metrics["files"]:
        # same rule as the graph's `unsupported`: extension-less files (LICENSE) are not source
        ext = posixpath.splitext(f["path"])[1]
        if ext and _node_of(f["path"], nodes.keys()) is None:
            nodes[f["path"]] = ext
    return dict(sorted(nodes.items()))


def _node_of(path: str, ids: Collection[str]) -> str | None:
    node = go_package(path) if path.endswith(".go") else path
    return node if node in ids else None


# (magnitude, severity, nodes, title, evidence); magnitude orders smells within a severity
Found = tuple[float, str, list[str], str, str]


def _ranked(kind: str, found: list[Found]) -> list[Smell]:
    found.sort(key=lambda f: (SEVERITY_RANK[f[1]], -f[0], f[2]))
    return [
        {"kind": kind, "severity": sev, "nodes": nodes, "title": title, "evidence": evidence}
        for _, sev, nodes, title, evidence in found[:MAX_PER_KIND]
    ]


def _cycles(graph: dict) -> list[Found]:
    by_id = {n["id"]: n for n in graph["nodes"]}
    found = []
    for members in graph["cycles"]:
        dirs = sorted({(folder_parts(by_id[m]) or ["."])[0] for m in members})
        evidence = (
            f"{len(members)} modules import each other at runtime "
            f"across {len(dirs)} top-level dir(s): {', '.join(dirs)}"
        )
        severity = "high" if len(dirs) >= 2 else "medium"
        found.append(
            (len(members), severity, members, f"Import cycle of {len(members)} modules", evidence)
        )
    return found


def forbidden_by(edge: dict, layers: Sequence[dict]) -> dict | None:
    """The first `[rules] layers` entry this edge crosses, unless its target is excepted."""

    # `id + "/"` lets `core/**` cover a Go package whose id is the directory `core`
    def under(node: str, glob: str) -> bool:
        return is_ignored(node, [glob]) or is_ignored(node + "/", [glob])

    for r in layers:
        if (
            under(edge["from"], r["from"])
            and under(edge["to"], r["to"])
            and not any(under(edge["to"], g) for g in r.get("except", ()))
        ):
            return r
    return None


def _layering(graph: dict, layers: Sequence[dict]) -> list[Found]:
    found = []
    for e in graph["edges"]:
        if rule := forbidden_by(e, layers):
            title = f"Forbidden import into {rule['to']}"
            evidence = (
                f"`{e['from']}` imports `{e['to']}`; {rule['from']} must not import {rule['to']}"
            )
            found.append((0, "high", [e["from"], e["to"]], title, evidence))
    return found


def _hubs(graph: dict, entry_points: frozenset[str], facades: frozenset[str]) -> list[Found]:
    near: dict[str, set[str]] = {n["id"]: set() for n in graph["nodes"]}
    for e in graph["edges"]:
        near[e["from"]].add(e["to"])
        near[e["to"]].add(e["from"])
    p95 = percentiles([len(v) for v in near.values()])["p95"]
    floor = THRESHOLDS["hub_floor"]
    return [
        (
            len(v),
            "low" if n in entry_points or _is_entry(n) else "medium",
            [n],
            f"Hub: {n}",
            f"{len(v)} neighbours; repo p95 is {p95}, floor {floor}",
        )
        for n, v in near.items()
        if len(v) >= max(floor, p95)
        and not _is_test(n)
        and posixpath.basename(n) != "conftest.py"
        and n not in facades
    ]


def _cochange(ids: Collection[str], graph: dict, history: dict) -> list[Found]:
    linked = {(e["from"], e["to"]) for e in graph["edges"]}
    found = []
    for p in history["pairs"]:
        a, b = _node_of(p["a"], ids), _node_of(p["b"], ids)
        if (
            a is None
            or b is None
            or a == b
            or p["both"] < THRESHOLDS["cochange_min_both"]
            or p["conf"] < THRESHOLDS["cochange_min_conf"]
            or (a, b) in linked
            or (b, a) in linked
            or (_is_test(p["a"]) and _is_test(p["b"]))
            or (_subject(p["a"]) == _subject(p["b"]) and _is_test(p["a"]) != _is_test(p["b"]))
        ):
            continue
        severity = "medium" if p["conf"] >= THRESHOLDS["cochange_medium_conf"] else "low"
        title = f"Hidden coupling: {p['a']} and {p['b']}"
        evidence = (
            f"changed together in {p['both']} commits (confidence {p['conf']}); "
            "neither imports the other"
        )
        found.append((p["conf"] * 1000 + p["both"], severity, sorted([a, b]), title, evidence))
    return found


def _hotspots(ids: Collection[str], history: dict, metrics: dict) -> list[Found]:
    churn = history["churn"]
    measured = [f for f in metrics["files"] if f["path"] in churn]
    min_churn = max(
        THRESHOLDS["hotspot_min_churn"], percentiles([churn[f["path"]] for f in measured])["p90"]
    )
    lines_p75 = metrics["stats"]["file_lines"]["p75"]
    found = []
    for f in measured:
        node, changes = _node_of(f["path"], ids), churn[f["path"]]
        if node and changes >= min_churn and f["lines"] >= lines_p75:
            evidence = (
                f"changed in {changes} commits (threshold {min_churn}); "
                f"{f['lines']} lines (repo p75 is {lines_p75})"
            )
            found.append(
                (changes * f["lines"], "medium", [node], f"Hotspot: {f['path']}", evidence)
            )
    return found


def _oversize(ids: Collection[str], metrics: dict) -> list[Found]:
    fs, fn = metrics["stats"]["file_lines"], metrics["stats"]["function_lines"]
    found: list[Found] = []
    for f in metrics["files"]:
        node, n = _node_of(f["path"], ids), f["lines"]
        if (
            node
            and n > fs["p95"]
            and n >= THRESHOLDS["oversize_file_median_ratio"] * fs["median"]
            and n >= THRESHOLDS["oversize_file_floor"]
        ):
            evidence = f"{n} lines; repo p95 is {fs['p95']}, median {fs['median']}"
            found.append((n, "low", [node], f"Large file: {f['path']}", evidence))
    for f in metrics["functions"]:
        node, n = _node_of(f["path"], ids), f["lines"]
        if node and n > fn["p95"] and n >= THRESHOLDS["oversize_function_floor"]:
            title = f"Long function: `{f['name']}` in {f['path']}"
            evidence = f"{n} lines; repo p95 is {fn['p95']} (function sizes: Python only)"
            found.append((n, "low", [node], title, evidence))
    return found


def _duplicates(ids: Collection[str], dupes: dict) -> list[Found]:
    found = []
    for b in dupes["blocks"]:
        locs = b["locations"]
        nodes = sorted({n for loc in locs if (n := _node_of(loc["path"], ids))})
        if not nodes:
            continue
        medium = (
            b["lines"] >= THRESHOLDS["duplicate_medium_lines"]
            or len(locs) >= THRESHOLDS["duplicate_medium_locations"]
        )
        where = ", ".join(f"{loc['path']}:{loc['start']}-{loc['end']}" for loc in locs)
        evidence = f"{b['lines']} lines repeated in {len(locs)} places: {where}"
        title = f"Duplicate block of {b['lines']} lines"
        found.append((b["lines"], "medium" if medium else "low", nodes, title, evidence))
    return found


def _is_entry(node: str) -> bool:
    name = posixpath.basename(node)
    return name in ENTRY_NAMES or any(fnmatch.fnmatchcase(name, g) for g in ENTRY_GLOBS)


def _deadcode(graph: dict, entry_points: frozenset[str]) -> list[Found]:
    imported = {e["to"] for e in graph["edges"]}
    evidence = "imported by 0 modules; not a test or a known entry point"
    return [
        (0, "low", [n["id"]], f"Possibly unused: {n['id']}", evidence)
        for n in graph["nodes"]
        if n["id"] not in imported
        and n["id"] not in entry_points
        and not _is_test(n["id"])
        and not _is_entry(n["id"])
    ]


def detect(
    graph: dict,
    history: dict,
    metrics: dict,
    dupes: dict,
    layers: Sequence[dict],
    entry_points: frozenset[str] = frozenset(),
    facades: frozenset[str] = frozenset(),
) -> list[Smell]:
    ids = map_nodes(graph, metrics).keys()
    return [
        *_ranked("cycle", _cycles(graph)),
        *_ranked("layering", _layering(graph, layers)),
        *_ranked("hub", _hubs(graph, entry_points, facades)),
        *_ranked("cochange", _cochange(ids, graph, history)),
        *_ranked("hotspot", _hotspots(ids, history, metrics)),
        *_ranked("oversize", _oversize(ids, metrics)),
        *_ranked("duplicate", _duplicates(ids, dupes)),
        *_ranked("deadcode", _deadcode(graph, entry_points)),
    ]


def _load(path: Path, parse) -> dict:
    text = read_text(path)
    try:
        data = parse(text) if text is not None else {}
    except ValueError:  # json.JSONDecodeError and tomllib.TOMLDecodeError
        return {}
    return data if isinstance(data, dict) else {}


def _strings(value) -> Iterable[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [v for v in value.values() if isinstance(v, str)]
    return []


def _runs_as_main(text: str) -> bool:
    """A module-level `if __name__ == "__main__":` block."""
    if "__main__" not in text:
        return False
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    return any(
        isinstance(node, ast.If) and ast.unparse(node.test) == "__name__ == '__main__'"
        for node in tree.body
    )


def _only_imports(tree: ast.Module) -> bool:
    return all(
        isinstance(node, ast.Import | ast.ImportFrom)
        or (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
        or (isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) == "__all__")
        for node in tree.body
    )


def facades(root: Path, files: Sequence[str]) -> frozenset[str]:
    """Package `__init__.py` files whose body only re-exports (imports, `__all__`, a docstring)."""
    found = set()
    for path in files:
        if posixpath.basename(path) == "__init__.py":
            try:
                if _only_imports(ast.parse(read_text(root / path) or "")):
                    found.add(path)
            except SyntaxError:
                pass
    return frozenset(found)


def entry_points(root: Path, files: Sequence[str], globs: Sequence[str] = ()) -> frozenset[str]:
    """Nodes a manifest or `package main` names as a program start, or a framework loads by path."""
    found = set()
    globs = [*PATH_LOADED_GLOBS, *globs]
    for path in files:
        folder, name = posixpath.split(path)
        if name.endswith(".ini"):
            # alembic.ini style: the migration scripts live in <script_location>/versions
            location = re.search(
                r"^script_location\s*=\s*(\S+)", read_text(root / path) or "", re.MULTILINE
            )
            if location:
                where = posixpath.join(folder, location[1].removeprefix("%(here)s/"))
                globs.append(posixpath.join(where, "versions", "*.py"))
        elif name == "package.json":
            data = _load(root / path, json.loads)
            for target in [*_strings(data.get("main")), *_strings(data.get("bin"))]:
                found.add(posixpath.normpath(posixpath.join(folder, target)))
        elif name == "pyproject.toml":
            project = _load(root / path, tomllib.loads).get("project")
            scripts = project.get("scripts") if isinstance(project, dict) else None
            for target in _strings(scripts):
                module = target.split(":")[0].strip().replace(".", "/")
                for base in (folder, posixpath.join(folder, "src")):
                    found.update(
                        posixpath.join(base, module + suffix) for suffix in (".py", "/__init__.py")
                    )
        elif posixpath.splitext(name)[1] not in NON_SOURCE_EXTENSIONS:
            text = read_text(root / path) or ""
            if text.startswith("#!") or (name.endswith(".py") and _runs_as_main(text)):
                found.add(path)
            elif (
                name.endswith(".go")
                and not name.endswith("_test.go")
                and re.search(r"^package\s+main\b", text, re.MULTILINE)
            ):
                found.add(go_package(path))
    found.update(go_package(f) if f.endswith(".go") else f for f in files if is_ignored(f, globs))
    return frozenset(found) & frozenset(
        [*files, *(go_package(f) for f in files if f.endswith(".go"))]
    )
