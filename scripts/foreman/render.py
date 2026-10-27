"""Validate report data and render it into a self-contained HTML template."""

import html
import json
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"

# a node's status, and the sections its summary may have
STATUSES = {"added", "changed", "removed", "affected"}
EDGE_KINDS = {"import", "call", "impl", "cycle", "forbidden"}
SMELL_SEVERITIES = {"low", "medium", "high"}
# Structural smells only; line-level findings belong in the review report.
# kind -> (min nodes, max nodes)
DIAGRAM_SMELLS = {"scatter": (3, None), "twin": (2, 2), "hub": (1, 1)}
HUB_MIN_NEIGHBOURS = 5
# Item fields that must be strings when present; type errors stop validation before the rules.
_STRING_FIELDS = {
    "nodes": ("id", "label", "sub", "lane", "status"),
    "edges": ("from", "to", "kind", "label"),
    "smells": ("kind", "severity", "title", "evidence", "suggestion"),
}


def _is_str_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _shape_problems(data: dict) -> list[str]:
    errs = [
        f"missing top-level key '{k}'"
        for k in ("title", "lanes", "nodes", "edges")
        if k not in data
    ]
    if errs:
        return errs
    if not isinstance(data["title"], str):
        errs.append("'title' must be a string")
    if not _is_str_list(data["lanes"]):
        errs.append("'lanes' must be a list of strings")
    for key, fields in _STRING_FIELDS.items():
        items = data.get(key, [])
        if not isinstance(items, list):
            errs.append(f"'{key}' must be a list")
            continue
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                errs.append(f"{key} #{i}: must be an object")
                continue
            errs += [
                f"{key} #{i}: '{f}' must be a string"
                for f in fields
                if not isinstance(item.get(f, ""), str)
            ]
            if key == "smells" and not _is_str_list(item.get("nodes", [])):
                errs.append(f"smells #{i}: 'nodes' must be a list of node ids")
            if key == "nodes":
                summary = item.get("summary", {})
                if not isinstance(summary, dict) or not all(
                    isinstance(v, list) for v in summary.values()
                ):
                    errs.append(f"nodes #{i}: 'summary' must be an object of lists")
    return errs


def _diagram(data: dict) -> list[str]:
    errs = _shape_problems(data)
    if errs:
        return errs
    if not data["nodes"]:
        errs.append("nodes must not be empty")
    ids = set()
    for n in data["nodes"]:
        nid = n.get("id")
        if not nid or nid in ids:
            errs.append(f"node id missing or duplicated: {nid!r}")
        ids.add(nid)
        if n.get("lane") not in data["lanes"]:
            errs.append(f"node {nid}: lane {n.get('lane')!r} not in lanes")
        if n.get("status") not in STATUSES:
            errs.append(f"node {nid}: status must be one of {sorted(STATUSES)}")
        if not n.get("label"):
            errs.append(f"node {nid}: missing label")
        extra = set(n.get("summary", {})) - STATUSES
        if extra:
            errs.append(f"node {nid}: unknown summary keys {sorted(extra)}")
        if n.get("status") != "affected" and not n.get("summary"):
            errs.append(f"node {nid}: changed nodes need a summary")
        for entries in n.get("summary", {}).values():
            for e in entries:
                if not (isinstance(e, str) or (isinstance(e, dict) and {"old", "new"} <= e.keys())):
                    errs.append(
                        f"node {nid}: summary entry must be a string or {{old, new[, note]}}: {e!r}"
                    )
    for e in data["edges"]:
        name = f"edge {e.get('from')}->{e.get('to')}"
        if e.get("from") not in ids or e.get("to") not in ids:
            errs.append(f"{name}: unknown node")
        if e.get("kind") not in EDGE_KINDS:
            errs.append(f"{name}: kind must be one of {sorted(EDGE_KINDS)}")
    used_lanes = {n.get("lane") for n in data["nodes"]}
    errs += [
        f"lane {lane!r} has no nodes (drop it)" for lane in data["lanes"] if lane not in used_lanes
    ]
    touched = {e.get(k) for e in data["edges"] for k in ("from", "to")}
    # changed files nothing imports (a migration) may stand alone in their lane
    errs += [
        f"node {n.get('id')}: has no edges (drop it or connect it)"
        for n in data["nodes"]
        if n.get("status") == "affected" and n.get("id") not in touched
    ]
    return errs + _smell_problems(data.get("smells", []), ids, data["edges"])


def _smell_problems(smells: list, ids: set, edges: list) -> list[str]:
    errs = []
    for i, s in enumerate(smells):
        name = f"smell #{i} ({s.get('title') or s.get('kind')!r})"
        kind = s.get("kind")
        if kind not in DIAGRAM_SMELLS:
            errs.append(f"{name}: kind must be one of {sorted(DIAGRAM_SMELLS)}")
            continue
        if s.get("severity") not in SMELL_SEVERITIES:
            errs.append(f"{name}: severity must be one of {sorted(SMELL_SEVERITIES)}")
        for key in ("title", "evidence"):
            if not str(s.get(key, "")).strip():
                errs.append(f"{name}: missing {key} (no evidence, no smell)")
        nodes = set(s.get("nodes") or [])
        unknown = sorted(nodes - ids)
        if unknown:
            errs.append(f"{name}: unknown nodes {unknown}")
        lo, hi = DIAGRAM_SMELLS[kind]
        if len(nodes) < lo or (hi is not None and len(nodes) > hi):
            want = f"exactly {lo}" if lo == hi else f"at least {lo}"
            errs.append(f"{name}: {kind} needs {want} distinct nodes, got {len(nodes)}")
        if kind == "hub" and len(nodes) == 1 and not unknown:
            (hub,) = nodes
            near = {
                e.get("to") if e.get("from") == hub else e.get("from")
                for e in edges
                if hub in (e.get("from"), e.get("to"))
            } - {hub}
            if len(near) < HUB_MIN_NEIGHBOURS:
                errs.append(
                    f"{name}: hub has {len(near)} neighbours in the graph; "
                    f"needs at least {HUB_MIN_NEIGHBOURS}"
                )
    return errs


def validate(data: dict) -> list[str]:
    """Problems in diagram data; a map comes from `map` itself and is not re-checked."""
    kind = data.get("kind", "diagram")
    if kind not in ("diagram", "map"):
        return [f"kind must be one of ['diagram', 'map'], got {kind!r}"]
    return _diagram(data) if kind == "diagram" else []


def write(data: dict, out: Path) -> Path:
    kind = data.get("kind", "diagram")
    errs = validate(data)
    if errs:
        raise ValueError(f"invalid {kind}: {len(errs)} problems\n" + "\n".join(errs))
    template = (
        (TEMPLATES / f"{kind}.html")
        .read_text(encoding="utf-8")
        .replace("/*__THEME__*/", (TEMPLATES / "_theme.css").read_text(encoding="utf-8"))
        .replace("/*__UI__*/", (TEMPLATES / "_ui.js").read_text(encoding="utf-8"))
        .replace("/*__TITLE__*/", html.escape(data["title"]))
    )
    # `<` only occurs inside JSON strings, so < keeps `</script>` and `<!--` inert.
    payload = json.dumps(data).replace("<", "\\u003c")
    out.write_text(template.replace("/*__DATA__*/null", payload), encoding="utf-8")
    return out
