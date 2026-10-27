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
    "edges": [{"from": "app/main.py", "to": "lib/util.py", "kind": "import", "dir": "down"}],
    "smells": [],
    "unsupported": {},
}


@pytest.mark.browser
def test_views_in_a_browser(tmp_path, serve):
    site = tmp_path / "site"
    site.mkdir()
    diagram = json.loads((DATA / "diagram_sample.json").read_text(encoding="utf-8"))
    render.write(diagram, site / "diagram.html")
    render.write(MAP, site / "map.html")
    r = run(SPEC, tmp_path / "out", serve(site))
    assert [(t["title"], t["status"]) for t in r["tests"]] == [
        ("diagram filter enter focuses the first match", "passed"),
        ("diagram focus pulls neighbours up and fades the rest", "passed"),
        ("map enter on a group drills in and focuses the breadcrumb", "passed"),
    ]
    assert all(not t["console_errors"] and not t["bad_responses"] for t in r["tests"])
