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


@pytest.mark.browser
def test_views_in_a_browser(tmp_path, serve):
    site = tmp_path / "site"
    site.mkdir()
    diagram = json.loads((DATA / "diagram_sample.json").read_text(encoding="utf-8"))
    render.write(diagram, site / "diagram.html")
    render.write(MAP, site / "map.html")
    render.write(DENSE, site / "dense.html")
    render.write(LAYERED, site / "layered.html")
    r = run(SPEC, tmp_path / "out", serve(site))
    assert [(t["title"], t["status"]) for t in r["tests"]] == [
        ("diagram filter enter focuses the first match", "passed"),
        ("diagram focus pulls neighbours up and fades the rest", "passed"),
        ("diagram neighbourhood puts dependents left and dependencies right", "passed"),
        ("map enter on a group drills in and focuses the breadcrumb", "passed"),
        ("map neighbourhood puts dependents left and dependencies right", "passed"),
        ("map with few package edges opens as a graph", "passed"),
        ("map with more than 30 package edges opens as a matrix", "passed"),
        ("problems only hides import edges", "passed"),
    ]
    assert all(not t["console_errors"] and not t["bad_responses"] for t in r["tests"])
