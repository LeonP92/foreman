"""Whole-repo map: modules grouped by directory, import edges, and repo-wide smells."""

import posixpath
from collections import Counter
from graphlib import TopologicalSorter
from pathlib import Path

from foreman import dupes, graph, history, metrics, smells
from foreman.files import list_files
from foreman.langs import go_package


def _groups(nodes: list[dict]) -> dict[str, str]:
    """Node id -> group: the first `depth` dir parts, deepening while everything shares one."""
    folders = {n["id"]: smells.folder_parts(n) for n in nodes}
    deepest = max((len(f) for f in folders.values()), default=0)
    depth = 1
    while True:
        group_of = {i: "/".join(f[:depth]) or "." for i, f in folders.items()}
        if len(set(group_of.values())) > 1 or depth >= deepest:
            return group_of
        depth += 1


def _edge_kind(edge: dict, cyclic: set[tuple[str, str]], layers: list[dict]) -> str:
    if smells.forbidden_by(edge, layers):
        return "forbidden"
    return "cycle" if (edge["from"], edge["to"]) in cyclic else "import"


def _layers(group_ids: list[str], links: set[tuple[str, str]]) -> dict[str, int]:
    """Group -> layer: cycles condensed, then longest path down to a sink; 0 is the top row."""
    comp = {g: g for g in group_ids}
    for scc in graph.cycles([{"from": a, "to": b, "type_only": False} for a, b in sorted(links)]):
        comp.update(dict.fromkeys(scc, scc[0]))
    below: dict[str, set[str]] = {c: set() for c in comp.values()}
    for a, b in links:
        if comp[a] != comp[b]:
            below[comp[a]].add(comp[b])
    height: dict[str, int] = {}
    for c in TopologicalSorter(below).static_order():
        height[c] = 1 + max((height[d] for d in below[c]), default=-1)
    top = max(height.values(), default=0)
    return {g: top - height[comp[g]] for g in group_ids}


# Package edge kinds, least to most severe.
SEVERITY = ("import", "cycle", "forbidden")


def _packages(edges: list[dict], kinds: list[str], group_of: dict, rank: dict) -> list[dict]:
    """Group pairs: import count, the most severe kind behind them, direction in (layer, id) order."""
    pairs: dict[tuple[str, str], dict] = {}
    for e, kind in zip(edges, kinds, strict=True):
        a, b = group_of[e["from"]], group_of[e["to"]]
        if a == b:
            continue
        up = rank[a] > rank[b]
        # Only runtime, allowed imports shape the order, so one of them flowing up is a back edge
        # inside a group cycle.
        if kind == "import" and up and not e["type_only"]:
            kind = "cycle"
        pair = pairs.setdefault(
            (a, b),
            {"from": a, "to": b, "imports": 0, "kind": "import", "dir": "up" if up else "down"},
        )
        pair["imports"] += 1
        pair["kind"] = max(pair["kind"], kind, key=SEVERITY.index)
    return [pairs[k] for k in sorted(pairs)]


def build(root: Path, config: dict) -> dict:
    ignore = config["repo"]["ignore"]
    layers = config.get("rules", {}).get("layers", [])
    g = graph.build(root, None, ignore, config["graph"])
    measured = metrics.measure(root, ignore)
    files = list_files(root, ignore)
    found = smells.detect(
        g,
        history.analyse(root, ignore),
        measured,
        dupes.find(root, ignore),
        layers,
        smells.entry_points(root, files, config["audit"]["entry_points"]),
        smells.facades(root, files),
    )
    lines: Counter[str] = Counter()
    for f in measured["files"]:
        lines[go_package(f["path"]) if f["path"].endswith(".go") else f["path"]] += f["lines"]
    langs = smells.map_nodes(g, measured)
    group_of = _groups([{"id": i, "lang": lang} for i, lang in langs.items()])
    member = {n: i for i, c in enumerate(g["cycles"]) for n in c}
    cyclic = {
        (e["from"], e["to"])
        for e in g["edges"]
        if not e["type_only"] and member.get(e["from"], -1) == member.get(e["to"], -2)
    }
    group_ids = sorted(set(group_of.values()))
    kinds = [_edge_kind(e, cyclic, layers) for e in g["edges"]]
    # Forbidden edges break the order by definition and type-only ones don't load at runtime
    # (smells ignore their cycles too), so neither shapes it.
    layer = _layers(
        group_ids,
        {
            (group_of[e["from"]], group_of[e["to"]])
            for e, kind in zip(g["edges"], kinds, strict=True)
            if kind != "forbidden"
            and not e["type_only"]
            and group_of[e["from"]] != group_of[e["to"]]
        },
    )
    rank = {gid: (layer[gid], gid) for gid in group_ids}
    return {
        "kind": "map",
        "title": f"Codebase map: {root.resolve().name}",
        "notes": "Function sizes are measured for Python only.",
        "groups": [
            {
                "id": gid,
                "label": gid,
                "layer": layer[gid],
                "nodes": [i for i in sorted(group_of) if group_of[i] == gid],
            }
            for gid in group_ids
        ],
        "nodes": [
            {
                "id": i,
                "label": posixpath.basename(i) or i,
                "group": group_of[i],
                "lang": lang,
                "lines": lines[i],
            }
            for i, lang in langs.items()
        ],
        "edges": [
            {"from": e["from"], "to": e["to"], "kind": kind}
            for e, kind in zip(g["edges"], kinds, strict=True)
        ],
        "packages": _packages(g["edges"], kinds, group_of, rank),
        "smells": found,
        "unsupported": g["unsupported"],
    }
