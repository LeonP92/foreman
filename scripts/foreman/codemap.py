"""Whole-repo map: modules grouped by directory, import edges, and repo-wide smells."""

import posixpath
import shutil
import subprocess
from collections import Counter
from graphlib import TopologicalSorter
from pathlib import Path

from foreman import dupes, graph, history, metrics, render, smells
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


def _repo_name(root: Path) -> str:
    """The main checkout's folder, so a map of a temp worktree is still named for its repo."""
    git = shutil.which("git")
    common = (
        git
        and subprocess.run(
            [git, "rev-parse", "--path-format=absolute", "--git-common-dir"],
            check=False,
            cwd=root,
            capture_output=True,
            encoding="utf-8",
        ).stdout.strip()
    )
    return (
        Path(common).parent.name if common and Path(common).name == ".git" else root.resolve().name
    )


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
        smells.mentioned(root, files),
    )
    shown, dropped = smells.cap(found)
    counts: dict[str, Counter[str]] = {}
    for s in found:
        counts.setdefault(s["kind"], Counter())[s["severity"]] += 1
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
        "title": f"Codebase map: {_repo_name(root)}",
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
        "smells": shown,
        "dropped": dropped,
        "counts": {k: dict(c) for k, c in counts.items()},
        "unsupported": g["unsupported"],
    }


def _matching(smells: list[dict], entry: dict) -> list[int]:
    return [
        j
        for j, s in enumerate(smells)
        if s["kind"] == entry["kind"]
        and sorted(s["nodes"]) == sorted(entry["nodes"])
        and entry.get("title", s["title"]) == s["title"]
    ]


def dismiss(data: dict, triage: dict) -> dict:
    """The map without the smells triage dismissed; `dismissed` counts them per kind.

    `dismissed_smells` keeps what was removed, so re-running the same triage is a no-op.
    """
    entries = triage.get("dismissed") if isinstance(triage, dict) else None
    if not isinstance(entries, list):
        raise ValueError("triage: 'dismissed' must be a list")  # noqa: TRY004 - CLI maps bad input to ValueError
    drop: set[tuple[int, str]] = set()
    for i, e in enumerate(entries):
        if not (
            isinstance(e, dict)
            and isinstance(e.get("kind"), str)
            and isinstance(e.get("nodes"), list)
            and all(isinstance(n, str) for n in e["nodes"])
            and isinstance(e.get("reason"), str)
            and e["reason"].strip()
            and isinstance(e.get("title", ""), str)
        ):
            raise ValueError(
                f"triage dismissed #{i}: needs a string kind, a list of nodes and a reason"
                " (title optional)"
            )
        if e["kind"] not in render.MAP_SMELLS:
            raise ValueError(f"triage dismissed #{i}: unknown kind {e['kind']!r}")
        found = _matching(data["smells"], e)
        where = f"triage dismissed #{i}"
        if not found and _matching(data.get("dismissed_smells", []), e):
            continue
        if not found:
            raise ValueError(
                f"{where}: no listed {e['kind']} smell with nodes {sorted(e['nodes'])}"
                + (f" and title {e['title']!r}" if "title" in e else "")
            )
        # without a title, kind + nodes must pick one smell (a file's size and a function's)
        if len(found) > 1 and "title" not in e:
            titles = "; ".join(data["smells"][j]["title"] for j in found)
            raise ValueError(
                f"{where}: {len(found)} listed {e['kind']} smells match; add a title: {titles}"
            )
        drop.update((j, e["reason"]) for j in found)
    reasons = dict(drop)
    kept = [s for j, s in enumerate(data["smells"]) if j not in reasons]
    gone = [{**data["smells"][j], "reason": r} for j, r in sorted(reasons.items())]
    dismissed = Counter(data.get("dismissed", {}))
    dismissed.update(s["kind"] for s in gone)
    return {
        **data,
        "smells": kept,
        "dismissed": dict(sorted(dismissed.items())),
        "dismissed_smells": [*data.get("dismissed_smells", []), *gone],
    }
