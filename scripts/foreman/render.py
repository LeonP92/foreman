"""Validate report data and render it into a self-contained HTML template."""

import json
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"

STATUSES = {"added", "changed", "removed", "affected"}
EDGE_KINDS = {"import", "call", "impl", "cycle", "forbidden"}
SUMMARY_KEYS = {"added", "removed", "changed", "affected"}
SMELL_SEVERITIES = {"low", "medium", "high"}
# Structural smells only; line-level findings belong in the review report.
# kind -> (min nodes, max nodes)
DIAGRAM_SMELLS = {"scatter": (3, None), "twin": (2, 2), "hub": (1, 1)}
HUB_MIN_NEIGHBOURS = 5
_MAP_STRING_FIELDS = {
    "groups": ("id", "label"),
    "nodes": ("id", "label", "group", "lang"),
    "edges": ("from", "to", "kind"),
    "packages": ("from", "to", "kind", "dir"),
    "smells": ("kind", "severity", "title", "evidence"),
}
MAP_EDGE_KINDS = {"import", "cycle", "forbidden"}
MAP_EDGE_DIRS = {"down", "up"}
MAP_SMELLS = {
    "cycle",
    "layering",
    "hub",
    "cochange",
    "hotspot",
    "oversize",
    "duplicate",
    "deadcode",
}
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
        extra = set(n.get("summary", {})) - SUMMARY_KEYS
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


def _map(data: dict) -> list[str]:
    errs = [] if isinstance(data.get("title"), str) else ["'title' must be a string"]
    unsupported = data.get("unsupported")
    if not isinstance(unsupported, dict) or not all(
        isinstance(k, str) and isinstance(v, int) for k, v in unsupported.items()
    ):
        errs.append("'unsupported' must map extensions to file counts")
    for key, fields in _MAP_STRING_FIELDS.items():
        items = data.get(key)
        if not isinstance(items, list):
            errs.append(f"'{key}' must be a list")
            continue
        for i, item in enumerate(items):
            if not isinstance(item, dict) or not all(isinstance(item.get(f), str) for f in fields):
                errs.append(f"{key} #{i}: must be an object with string {', '.join(fields)}")
            elif key in ("groups", "smells") and not _is_str_list(item.get("nodes")):
                errs.append(f"{key} #{i}: 'nodes' must be a list of node ids")
    if errs:
        return errs
    if not data["nodes"]:
        errs.append("nodes must not be empty")
    ids: set[str] = set()
    for n in data["nodes"]:
        if not n["id"] or n["id"] in ids:
            errs.append(f"node id missing or duplicated: {n['id']!r}")
        ids.add(n["id"])
        if not isinstance(n.get("lines"), int):
            errs.append(f"node {n['id']}: lines must be an integer")
    grouped = {(n, g["id"]) for g in data["groups"] for n in g["nodes"]}
    errs += [
        f"node {n['id']}: group {n['group']!r} does not list it"
        for n in data["nodes"]
        if (n["id"], n["group"]) not in grouped
    ]
    errs += [
        f"group {g['id']!r}: nodes must be a non-empty list of node ids"
        for g in data["groups"]
        if not g["nodes"] or not set(g["nodes"]) <= ids
    ]
    errs += [
        f"group {g['id']!r}: layer must be an integer >= 0"
        for g in data["groups"]
        if type(g.get("layer")) is not int or g["layer"] < 0
    ]
    for e in data["edges"]:
        name = f"edge {e['from']}->{e['to']}"
        if e["from"] not in ids or e["to"] not in ids:
            errs.append(f"{name}: unknown node")
        if e["kind"] not in MAP_EDGE_KINDS:
            errs.append(f"{name}: kind must be one of {sorted(MAP_EDGE_KINDS)}")
    group_ids = {g["id"] for g in data["groups"]}
    for pk in data["packages"]:
        name = f"package {pk['from']}->{pk['to']}"
        if pk["from"] not in group_ids or pk["to"] not in group_ids or pk["from"] == pk["to"]:
            errs.append(f"{name}: unknown group")
        if type(pk.get("imports")) is not int or pk["imports"] < 1:
            errs.append(f"{name}: imports must be a positive integer")
        if pk["kind"] not in MAP_EDGE_KINDS:
            errs.append(f"{name}: kind must be one of {sorted(MAP_EDGE_KINDS)}")
        if pk["dir"] not in MAP_EDGE_DIRS:
            errs.append(f"{name}: dir must be one of {sorted(MAP_EDGE_DIRS)}")
    for i, sm in enumerate(data["smells"]):
        name = f"smell #{i} ({sm['title']!r})"
        if sm["kind"] not in MAP_SMELLS:
            errs.append(f"{name}: kind must be one of {sorted(MAP_SMELLS)}")
        if sm["severity"] not in SMELL_SEVERITIES:
            errs.append(f"{name}: severity must be one of {sorted(SMELL_SEVERITIES)}")
        if not sm["title"].strip() or not sm["evidence"].strip():
            errs.append(f"{name}: missing title or evidence (no evidence, no smell)")
        if not sm["nodes"] or not set(sm["nodes"]) <= ids:
            errs.append(f"{name}: nodes must be a non-empty list of node ids")
    return errs


_VALIDATORS = {"diagram": _diagram, "map": _map}


def validate(data: dict) -> list[str]:
    kind = data.get("kind", "diagram")
    if not isinstance(kind, str) or kind not in _VALIDATORS:
        return [f"kind must be one of {sorted(_VALIDATORS)}, got {kind!r}"]
    return _VALIDATORS[kind](data)


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
    )
    # `<` only occurs inside JSON strings, so < keeps `</script>` and `<!--` inert.
    payload = json.dumps(data).replace("<", "\\u003c")
    out.write_text(template.replace("/*__DATA__*/null", payload), encoding="utf-8")
    return out
