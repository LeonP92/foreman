import json
from pathlib import Path

import pytest
from foreman import render
from foreman.browser import run

DATA = Path(__file__).parent / "data"
SPEC = Path(__file__).parent / "browser_site" / "views.spec.mjs"
MAP = {
    "kind": "map",
    "title": "Sample map",
    "notes": "",
    "groups": [
        {"id": "app", "label": "app", "layer": 0, "nodes": ["app/main.py"]},
        {"id": "lib", "label": "lib", "layer": 1, "nodes": ["lib/util.py"]},
    ],
    "nodes": [
        {"id": "app/main.py", "label": "main.py", "group": "app", "lang": "python", "lines": 20},
        {"id": "lib/util.py", "label": "util.py", "group": "lib", "lang": "python", "lines": 8},
    ],
    "edges": [{"from": "app/main.py", "to": "lib/util.py", "kind": "import"}],
    "packages": [{"from": "app", "to": "lib", "imports": 1, "kind": "import", "dir": "down"}],
    "smells": [],
    "unsupported": {},
}


def _map(groups: list[tuple[str, int]], edges: list[tuple[str, str, str, str]]) -> dict:
    """One module per group, so each edge is its group pair: (from group, to group, kind, dir)."""
    return {
        **MAP,
        "groups": [
            {"id": g, "label": g, "layer": layer, "nodes": [f"{g}/m.py"]} for g, layer in groups
        ],
        "nodes": [
            {"id": f"{g}/m.py", "label": "m.py", "group": g, "lang": "python", "lines": 1}
            for g, _ in groups
        ],
        "edges": [
            {"from": f"{a}/m.py", "to": f"{b}/m.py", "kind": kind} for a, b, kind, _ in edges
        ],
        "packages": [
            {"from": a, "to": b, "imports": 1, "kind": kind, "dir": d} for a, b, kind, d in edges
        ],
    }


# 9 groups each importing every later one: 36 package edges.
DENSE = _map(
    [(f"g{i}", i) for i in range(9)],
    [(f"g{i}", f"g{j}", "import", "down") for i in range(9) for j in range(i + 1, 9)],
)
LAYERED = _map(
    [("app", 0), ("svc", 1), ("core", 2)],
    [
        ("app", "svc", "import", "down"),
        # a module cycle inside a downward pair: still a problem
        ("svc", "core", "cycle", "down"),
        ("core", "app", "forbidden", "up"),
    ],
)

# Nine modules in three lanes, each importing every later one: 36 edges.
DENSE_DIAGRAM = {
    "title": "Dense diagram",
    "lanes": ["a", "b", "c"],
    "nodes": [
        {"id": f"m{i}", "label": f"m{i}", "lane": "abc"[i // 3], "status": "affected"}
        for i in range(9)
    ],
    "edges": [
        {"from": f"m{i}", "to": f"m{j}", "kind": "import"}
        for i in range(9)
        for j in range(i + 1, 9)
    ],
    "smells": [],
}

# One listed layering smell, three more past the cap and two dismissed; hubs of two severities,
# each with its own past-the-cap or dismissed note; every low deadcode dismissed.
CAPPED = {
    **MAP,
    "smells": [
        {
            "kind": "layering",
            "severity": "high",
            "nodes": ["app/main.py", "lib/util.py"],
            "title": "Forbidden import into lib/**",
            "evidence": "`app/main.py` imports `lib/util.py`",
        },
        *(
            {
                "kind": "hub",
                "severity": sev,
                "nodes": [node],
                "title": f"Hub: {node}",
                "evidence": "imports 9 modules",
            }
            for sev, node in [("medium", "app/main.py"), ("low", "lib/util.py")]
        ),
    ],
    "dropped": {"layering": {"high": 3}, "hub": {"low": 2}},
    "dismissed": {"layering": {"high": 2}, "hub": {"medium": 1}, "deadcode": {"low": 4}},
}

# One layer of three: with the drawer open it wraps, sending z -> x round the gutter.
WIDE = _map([("x", 0), ("y", 0), ("z", 0)], [("z", "x", "cycle", "up")])


@pytest.mark.browser
def test_views_in_a_browser(tmp_path, serve):
    site = tmp_path / "site"
    site.mkdir()
    diagram = json.loads((DATA / "diagram_sample.json").read_text(encoding="utf-8"))
    render.write(diagram, site / "diagram.html")
    render.write(MAP, site / "map.html")
    render.write(DENSE, site / "dense.html")
    render.write(LAYERED, site / "layered.html")
    render.write(WIDE, site / "wide.html")
    render.write(CAPPED, site / "capped.html")
    render.write(DENSE_DIAGRAM, site / "dense-diagram.html")
    r = run(SPEC, tmp_path / "out", serve(site))
    assert [(t["title"], t["status"]) for t in r["tests"]] == [
        ("diagram filter enter focuses the first match", "passed"),
        ("diagram focus pulls neighbours up and fades the rest", "passed"),
        ("diagram header and card sub-lines keep their full text on hover", "passed"),
        ("diagram neighbourhood puts dependents left and dependencies right", "passed"),
        ("diagram switch toggles to matrix and back", "passed"),
        ("diagram with more than 30 edges opens as a matrix", "passed"),
        ("map double-click on a group drills in", "passed"),
        ("map enter on a group drills in and focuses the breadcrumb", "passed"),
        ("map filter enter focuses the first match so N opens its neighbourhood", "passed"),
        ("map label follows its arc after the drawer closes", "passed"),
        ("map neighbourhood puts dependents left and dependencies right", "passed"),
        ("map renders when storage is unavailable", "passed"),
        ("map smell chips split severities and count dropped and dismissed", "passed"),
        ("map with few package edges opens as a graph", "passed"),
        ("map with more than 30 package edges opens as a matrix", "passed"),
        ("problems only hides import edges", "passed"),
    ]
    assert all(not t["console_errors"] and not t["bad_responses"] for t in r["tests"])
