import posixpath
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypedDict

from foreman.files import NON_SOURCE_EXTENSIONS, language, list_files, read_text
from foreman.langs import go, go_package, javascript, make_index, python, rule
from foreman.langs.rule import Rule

BUILTINS = {"python": python, "javascript": javascript, "go": go}


class Graph(TypedDict):
    nodes: list[dict]
    edges: list[dict]
    cycles: list[list[str]]
    skipped: list[dict]
    unsupported: dict[str, int]
    missing: list[str]


def cycles(edges: Sequence[Mapping]) -> list[list[str]]:
    """Strongly connected components of size > 1 over runtime edges (iterative Tarjan)."""
    graph: dict[str, list[str]] = {}
    for e in edges:
        if not e["type_only"]:
            graph.setdefault(e["from"], []).append(e["to"])
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    result = []
    for start, start_successors in graph.items():
        if start in index:
            continue
        index[start] = low[start] = len(index)
        stack.append(start)
        on_stack.add(start)
        work = [(start, iter(start_successors))]
        while work:
            v, successors = work[-1]
            for w in successors:
                if w not in index:
                    index[w] = low[w] = len(index)
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(graph.get(w, ()))))
                    break
                if w in on_stack:
                    low[v] = min(low[v], index[w])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[v])
                if low[v] == index[v]:
                    component = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        component.append(w)
                        if w == v:
                            break
                    if len(component) > 1:
                        result.append(sorted(component))
    return sorted(result)


def build(
    root: Path,
    paths: Sequence[str] | None = None,
    ignore: Sequence[str] = (),
    rules: Mapping[str, Rule] | None = None,
) -> Graph:
    rules = rules or {}
    files = list_files(root, ignore)
    index = make_index(root, files)
    rule_by_ext = {ext: name for name, r in rules.items() for ext in r["extensions"]}
    scope = None if paths is None else set(paths)
    nodes: dict[str, str] = {}
    edges: dict[tuple[str, str], bool] = {}
    scope_nodes: set[str] = set()
    skipped = []
    unsupported: Counter[str] = Counter()
    for path in files:
        in_scope = scope is None or path in scope
        suffix = posixpath.splitext(path)[1]
        lang = language(path) or rule_by_ext.get(suffix)
        if lang is None:
            if in_scope and suffix and suffix not in NON_SOURCE_EXTENSIONS:
                unsupported[suffix] += 1
            continue
        source = go_package(path) if lang == "go" else path
        nodes[source] = lang
        if in_scope:
            scope_nodes.add(source)
        text = read_text(root / path)
        if text is None:
            if in_scope:
                skipped.append({"path": path, "reason": "not UTF-8 text"})
            continue
        try:
            if lang in BUILTINS:
                found = BUILTINS[lang].imports(path, text, index)
            else:
                found = rule.imports(path, text, index, rules[lang])
        except SyntaxError as exc:
            if in_scope:
                skipped.append({"path": path, "reason": f"syntax error: {exc.msg}"})
            continue
        for target, type_only in found:
            if target != source:
                edges[source, target] = edges.get((source, target), True) and type_only
    all_edges = [{"from": a, "to": b, "type_only": t} for (a, b), t in sorted(edges.items())]
    edge_list = [e for e in all_edges if e["from"] in scope_nodes or e["to"] in scope_nodes]
    kept = scope_nodes | {e["from"] for e in edge_list} | {e["to"] for e in edge_list}
    return {
        "nodes": [{"id": n, "lang": nodes[n]} for n in sorted(kept)],
        "edges": edge_list,
        # whole-graph cycles, so a scoped view still sees loops through nodes outside it
        "cycles": [c for c in cycles(all_edges) if scope_nodes.intersection(c)],
        "skipped": skipped,
        "unsupported": dict(unsupported),
        # deleted, ignored or misspelt paths; silently dropping them looks like an empty change
        "missing": sorted(set(paths or ()) - set(files)),
    }
