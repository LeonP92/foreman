"""Whole-repo map: modules grouped by directory, import edges, and repo-wide smells."""

import posixpath
from collections import Counter
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


def build(root: Path, config: dict) -> dict:
    ignore = config["repo"]["ignore"]
    layers = config.get("rules", {}).get("layers", [])
    g = graph.build(root, None, ignore, config["graph"])
    measured = metrics.measure(root, ignore)
    found = smells.detect(
        g,
        history.analyse(root, ignore),
        measured,
        dupes.find(root, ignore),
        layers,
        smells.entry_points(root, list_files(root, ignore)),
    )
    lines: Counter[str] = Counter()
    for f in measured["files"]:
        lines[go_package(f["path"]) if f["path"].endswith(".go") else f["path"]] += f["lines"]
    group_of = _groups(g["nodes"])
    member = {n: i for i, c in enumerate(g["cycles"]) for n in c}
    cyclic = {
        (e["from"], e["to"])
        for e in g["edges"]
        if not e["type_only"] and member.get(e["from"], -1) == member.get(e["to"], -2)
    }
    unsupported = g["unsupported"]
    notes = "Function sizes are measured for Python only."
    if unsupported:
        notes += f" Not graphed (no import rule): {', '.join(sorted(unsupported))}."
    return {
        "kind": "map",
        "title": f"Codebase map: {root.resolve().name}",
        "notes": notes,
        "groups": [
            {"id": gid, "label": gid, "nodes": [i for i in sorted(group_of) if group_of[i] == gid]}
            for gid in sorted(set(group_of.values()))
        ],
        "nodes": [
            {
                "id": n["id"],
                "label": posixpath.basename(n["id"]) or n["id"],
                "group": group_of[n["id"]],
                "lines": lines[n["id"]],
            }
            for n in g["nodes"]
        ],
        "edges": [
            {"from": e["from"], "to": e["to"], "kind": _edge_kind(e, cyclic, layers)}
            for e in g["edges"]
        ],
        "smells": found,
        "unsupported": unsupported,
    }
