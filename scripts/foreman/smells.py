"""Repo-wide structural smells from the import graph, git history, sizes and duplicates."""

import ast
import fnmatch
import json
import posixpath
import re
import tomllib
from collections import Counter
from collections.abc import Collection, Iterable, Sequence
from pathlib import Path
from typing import TypedDict

from foreman.files import NON_SOURCE_EXTENSIONS, is_ignored, language, read_text
from foreman.langs import go_package
from foreman.metrics import percentiles

THRESHOLDS: dict[str, int | float] = {
    "hub_floor": 8,
    "hub_fanout_floor": 5,
    "hub_fanin_floor": 3,
    "cochange_min_both": 5,
    "cochange_min_conf": 0.6,
    "cochange_medium_conf": 0.8,
    "hotspot_min_churn": 5,
    "hotspot_window_days": 365,
    "oversize_file_median_ratio": 3,
    "oversize_file_floor": 300,
    "oversize_function_floor": 60,
    "duplicate_medium_lines": 20,
    "duplicate_medium_locations": 3,
    "duplicate_min_lines": 12,
    "bulk_commit_min_files": 10,
    "bulk_commit_share": 0.2,
}
MAX_PER_KIND = 20
TRIAGE_BUDGET = 60
# A team chose these boundaries, so every break is listed.
UNCAPPED = frozenset(["cycle", "layering"])
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
# __init__.py is imported implicitly with its package, so no edge ever points at it
ENTRY_NAMES = frozenset(
    ["__init__.py", "__main__.py", "main.py", "cli.py", "manage.py", "conftest.py", "setup.py"]
)
ENTRY_GLOBS = ("index.*", "*.config.*")
# Files a framework loads by path, so nothing imports them; `[audit] entry_points` adds more.
PATH_LOADED_GLOBS = ("**/migrations/**", "**/alembic/versions/**")
TEST_DIRS = frozenset(["test", "tests", "__tests__", "spec"])
TEST_PREFIXES = ("test_", "spec_")
TEST_SUFFIXES = ("_test", ".test", ".spec", "_spec")
# A class may just be named so (`PricingSpec`): these mark a test only in a test folder or
# beside the subject they strip to.
CLASS_TEST_SUFFIXES = ("Tests", "Test", "Spec")


class Smell(TypedDict):
    kind: str
    severity: str
    nodes: list[str]
    title: str
    evidence: str


def _in_test_dir(path: str) -> bool:
    # case-insensitive: Swift keeps tests in `Tests/`, some Java layouts in `Test/`
    return not TEST_DIRS.isdisjoint(part.lower() for part in path.split("/")[:-1])


def _subject(path: str, stems: Collection[str]) -> str:
    """The file stem without test markers: `test_cart`, `cart.spec`, `CartTest` -> the subject.

    `stems` holds the repo's file stems, so `CartTest` strips only when `Cart` exists.
    """
    stem = posixpath.splitext(posixpath.basename(path))[0]
    for prefix in TEST_PREFIXES:
        stem = stem.removeprefix(prefix)
    for suffix in TEST_SUFFIXES:
        stem = stem.removesuffix(suffix)
    for suffix in CLASS_TEST_SUFFIXES:
        bare = stem.removesuffix(suffix)
        if bare != stem and (_in_test_dir(path) or bare in stems):
            return bare
    return stem


def _is_test(path: str, stems: Collection[str]) -> bool:
    stem = posixpath.splitext(posixpath.basename(path))[0]
    return _subject(path, stems) != stem or _in_test_dir(path)


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
        for _, sev, nodes, title, evidence in found
    ]


def cap(found: list[Smell]) -> tuple[list[Smell], dict[str, dict[str, int]]]:
    """The first MAX_PER_KIND smells of each capped kind, and per kind and severity how many
    were dropped."""
    seen: Counter[str] = Counter()
    shown = []
    dropped: dict[str, Counter[str]] = {}
    for s in found:
        seen[s["kind"]] += 1
        if s["kind"] in UNCAPPED or seen[s["kind"]] <= MAX_PER_KIND:
            shown.append(s)
        else:
            dropped.setdefault(s["kind"], Counter())[s["severity"]] += 1
    return shown, {k: dict(c) for k, c in dropped.items()}


# kinds whose smell is one import edge, so `nodes` is [from, to]
EDGE_KINDS = frozenset(["layering"])


def triage_order(
    shown: list[Smell], counts: dict[str, dict[str, int]], group_of: dict[str, str]
) -> tuple[list[dict], dict[str, int]]:
    """Triage items within the budget, in order, and per kind how many smells are left untriaged.

    An item is one node set with all its smells, or for an edge kind every edge from one group
    to another. Every high item comes first; then the rest round-robin across kinds, items with
    more smells first within a severity, so one big kind can't starve the others.
    """
    items: dict[tuple[str, ...], dict] = {}
    for position, s in enumerate(shown):
        entry = {k: s[k] for k in ("kind", "severity", "title")}
        if s["kind"] in EDGE_KINDS:
            start, end = s["nodes"]
            ends = {"from": group_of[start], "to": group_of[end]}
            item = items.setdefault((s["kind"], ends["from"], ends["to"]), {**ends, "smells": []})
            entry.update({"from": start, "to": end})
        else:
            key = tuple(sorted(s["nodes"]))
            item = items.setdefault(key, {"nodes": list(key), "smells": []})
        item["smells"].append(entry)
        # the map lists each kind worst and biggest first, so the first worst smell leads
        if (rank := (SEVERITY_RANK[s["severity"]], position)) < item.get("rank", (3, 0)):
            item.update(rank=rank, kind=s["kind"], severity=s["severity"])
    ordered = sorted(items.values(), key=lambda i: (i["rank"][0], -len(i["smells"]), i["rank"]))
    picked = [i for i in ordered if i["severity"] == "high"]
    queues: dict[str, list[dict]] = {}
    for i in ordered:
        if i["severity"] != "high":
            queues.setdefault(i["kind"], []).append(i)
    while len(picked) < TRIAGE_BUDGET and any(queues.values()):
        for queue in queues.values():
            if queue and len(picked) < TRIAGE_BUDGET:
                picked.append(queue.pop(0))
    triaged = Counter(s["kind"] for i in picked for s in i["smells"])
    left = {k: n for k, sev in counts.items() if (n := sum(sev.values()) - triaged[k])}
    return [{k: v for k, v in i.items() if k != "rank"} for i in picked], dict(sorted(left.items()))


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


def _hubs(
    graph: dict, entry_points: frozenset[str], facades: frozenset[str], stems: frozenset[str]
) -> list[Found]:
    out: dict[str, set[str]] = {
        n["id"]: set() for n in graph["nodes"] if not _is_test(n["id"], stems)
    }
    into: dict[str, set[str]] = {n: set() for n in out}
    # type-only imports don't load at runtime, so a change doesn't ripple through them
    for e in graph["edges"]:
        if not e["type_only"] and e["from"] in out and e["to"] in out:
            out[e["from"]].add(e["to"])
            into[e["to"]].add(e["from"])
    near = {n: out[n] | into[n] for n in out}
    # fan-out keeps a stable definitions module that everything imports from being a hub;
    # fan-in keeps a composition root (a page, a route table) that nothing imports from being one
    min_out = max(
        THRESHOLDS["hub_fanout_floor"], percentiles([len(v) for v in out.values()])["p95"]
    )
    min_near = max(THRESHOLDS["hub_floor"], percentiles([len(v) for v in near.values()])["p95"])
    return [
        (
            len(near[n]),
            "low" if n in entry_points or _is_entry(n) else "medium",
            [n],
            f"Hub: {n}",
            (
                f"imports {len(out[n])} modules (threshold {min_out}); "
                f"imported by {len(into[n])} (floor {THRESHOLDS['hub_fanin_floor']}); "
                f"{len(near[n])} neighbours (threshold {min_near})"
            ),
        )
        for n in out
        if len(out[n]) >= min_out
        and len(into[n]) >= THRESHOLDS["hub_fanin_floor"]
        and len(near[n]) >= min_near
        and posixpath.basename(n) != "conftest.py"
        and n not in facades
    ]


def _cochange(
    ids: Collection[str], graph: dict, history: dict, stems: frozenset[str]
) -> list[Found]:
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
            # tests change with the code they cover; that is normal, not hidden coupling
            or _is_test(p["a"], stems)
            or _is_test(p["b"], stems)
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


def _hotspots(
    ids: Collection[str], history: dict, metrics: dict, stems: frozenset[str]
) -> list[Found]:
    churn = history["recent_churn"]
    measured = [
        f for f in metrics["files"] if f["path"] in churn and not _is_test(f["path"], stems)
    ]
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


def _oversize(ids: Collection[str], metrics: dict, stems: frozenset[str]) -> list[Found]:
    fs, fn = metrics["stats"]["file_lines"], metrics["stats"]["function_lines"]
    found: list[Found] = []
    for f in metrics["files"]:
        node, n = _node_of(f["path"], ids), f["lines"]
        if (
            node
            and not _is_test(f["path"], stems)
            and n > fs["p95"]
            and n >= THRESHOLDS["oversize_file_median_ratio"] * fs["median"]
            and n >= THRESHOLDS["oversize_file_floor"]
        ):
            evidence = f"{n} lines; repo p95 is {fs['p95']}, median {fs['median']}"
            found.append((n, "low", [node], f"Large file: {f['path']}", evidence))
    for f in metrics["functions"]:
        node, n = _node_of(f["path"], ids), f["lines"]
        if (
            node
            and not _is_test(f["path"], stems)
            and n > fn["p95"]
            and n >= THRESHOLDS["oversize_function_floor"]
        ):
            title = f"Long function: `{f['name']}` in {f['path']}"
            evidence = f"{n} lines; repo p95 is {fn['p95']} (function sizes: Python only)"
            found.append((n, "low", [node], title, evidence))
    return found


def _duplicates(ids: Collection[str], dupes: dict, stems: frozenset[str]) -> list[Found]:
    """One smell per set of files sharing duplicate blocks, so a long copy isn't several smells."""
    by_nodes: dict[tuple[str, ...], list[tuple[int, list[dict]]]] = {}
    for b in dupes["blocks"]:
        locs = [loc for loc in b["locations"] if not _is_test(loc["path"], stems)]
        nodes = tuple(sorted({n for loc in locs if (n := _node_of(loc["path"], ids))}))
        if len(locs) > 1 and nodes:
            by_nodes.setdefault(nodes, []).append((b["lines"], locs))
    found = []
    for nodes, blocks in by_nodes.items():
        lines = sum(n for n, _ in blocks)
        places = max(len(locs) for _, locs in blocks)
        medium = (
            lines >= THRESHOLDS["duplicate_medium_lines"]
            or places >= THRESHOLDS["duplicate_medium_locations"]
        )
        where = "; ".join(
            ", ".join(f"{loc['path']}:{loc['start']}-{loc['end']}" for loc in locs)
            for _, locs in blocks
        )
        evidence = f"{lines} lines in {len(blocks)} block(s), in up to {places} places: {where}"
        title = f"Duplicate code: {lines} lines"
        found.append((lines, "medium" if medium else "low", list(nodes), title, evidence))
    return found


def _is_entry(node: str) -> bool:
    name = posixpath.basename(node)
    return name in ENTRY_NAMES or any(fnmatch.fnmatchcase(name, g) for g in ENTRY_GLOBS)


def _deadcode(
    graph: dict, entry_points: frozenset[str], mentioned: frozenset[str], stems: frozenset[str]
) -> list[Found]:
    imported = {e["to"] for e in graph["edges"]}
    evidence = "imported by 0 modules and named in no other file; not a test or a known entry point"
    return [
        (0, "low", [n["id"]], f"Possibly unused: {n['id']}", evidence)
        for n in graph["nodes"]
        if n["id"] not in imported
        and n["id"] not in entry_points
        and n["id"] not in mentioned
        and not _is_test(n["id"], stems)
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
    mentioned: frozenset[str] = frozenset(),
) -> list[Smell]:
    ids = map_nodes(graph, metrics).keys()
    stems = frozenset(posixpath.splitext(posixpath.basename(i))[0] for i in ids)
    found = [
        *_ranked("cycle", _cycles(graph)),
        *_ranked("layering", _layering(graph, layers)),
        *_ranked("hub", _hubs(graph, entry_points, facades, stems)),
        *_ranked("cochange", _cochange(ids, graph, history, stems)),
        *_ranked("hotspot", _hotspots(ids, history, metrics, stems)),
        *_ranked("oversize", _oversize(ids, metrics, stems)),
        *_ranked("duplicate", _duplicates(ids, dupes, stems)),
        *_ranked("deadcode", _deadcode(graph, entry_points, mentioned, stems)),
    ]
    # a [graph.*] rule may cover config or infra files; those are still never smells
    return [
        s
        for s in found
        if not any(posixpath.splitext(n)[1].lower() in NON_SOURCE_EXTENSIONS for n in s["nodes"])
    ]


_NAME = re.compile(r"[\w-]+(?:\.[\w-]+)*")


def mentioned(root: Path, files: Sequence[str]) -> frozenset[str]:
    """Files whose name appears in another tracked text file; a bare stem only if it is unique."""
    # One pass: each name remembers the one file it came from, or "" once a second file has it.
    seen: dict[str, str] = {}
    for path in files:
        tokens = set(_NAME.findall(read_text(root / path) or ""))
        for token in tokens | {part for t in tokens for part in t.split(".")}:
            seen[token] = path if seen.get(token, path) == path else ""
    # a path mention always holds the file name, so the name covers both
    stems = Counter(
        posixpath.splitext(posixpath.basename(f))[0]
        for f in files
        if posixpath.splitext(f)[1].lower() not in ("", *NON_SOURCE_EXTENSIONS)
    )

    def names(f: str) -> list[str]:
        name = posixpath.basename(f)
        stem = posixpath.splitext(name)[0]
        return [name, stem] if stems[stem] == 1 else [name]

    return frozenset(f for f in files if any(seen.get(n, f) != f for n in names(f)))


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


# what a JS/TS barrel or a Ruby autoload index may hold besides re-exports
_JS_REEXPORT = re.compile(
    r"""//[^\n]*|/\*.*?\*/|\bexport\s+(?:type\s+)?(?:\*(?:\s+as\s+\w+)?|\{[^}]*\})"""
    r"""\s*from\s*['"][^'"]+['"]\s*;?""",
    re.DOTALL,
)
_RUBY_AUTOLOAD = re.compile(
    r"""^\s*(?:#.*|module\s+[\w:]+|end|autoload\s*\(?\s*:\w+\s*,\s*['"][^'"]+['"]\s*\)?)?\s*$""",
    re.MULTILINE,
)


def _is_facade(root: Path, path: str) -> bool:
    name = posixpath.basename(path)
    if name == "__init__.py":
        try:
            return _only_imports(ast.parse(read_text(root / path) or ""))
        except SyntaxError:
            return False
    if language(path) == "javascript":
        text = read_text(root / path) or ""
        return "export" in text and not _JS_REEXPORT.sub("", text).strip()
    if name.endswith(".rb"):
        text = read_text(root / path) or ""
        return "autoload" in text and not _RUBY_AUTOLOAD.sub("", text).strip()
    return False


def facades(root: Path, files: Sequence[str]) -> frozenset[str]:
    """Files whose body only re-exports: a package `__init__.py` (imports, `__all__`, a
    docstring), a JS/TS barrel (`export … from`, `export *`), a Ruby autoload-only index."""
    return frozenset(p for p in files if _is_facade(root, p))


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
        elif posixpath.splitext(name)[1].lower() not in NON_SOURCE_EXTENSIONS:
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
