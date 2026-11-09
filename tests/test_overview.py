import copy
import json
import re
from itertools import combinations
from pathlib import Path

import pytest
from foreman import overview, render
from foreman.cli import main

DATA = Path(__file__).parent / "data"
SAMPLE = json.loads((DATA / "overview_sample.json").read_text("utf-8"))
DIAGRAM = json.loads((DATA / "diagram_sample.json").read_text("utf-8"))
OPTIONAL = ("network", "sequence", "cards")


def _minimal():
    return {k: v for k, v in copy.deepcopy(SAMPLE).items() if k not in OPTIONAL}


def _render(tmp_path, data) -> str:
    return render.write(DIAGRAM, tmp_path / "diagram.html", data).read_text(encoding="utf-8")


def _overview_pane(page: str) -> str:
    return page.split('<div class="overview" id="overview"', 1)[1].split("</div>\n", 1)[0]


def test_sample_renders_every_section_offline_inside_the_diagram(tmp_path):
    page = _render(tmp_path, SAMPLE)
    assert "/*__" not in page
    assert "http" not in page.replace("http://www.w3.org/2000/svg", "")
    headings = [
        "Network view",
        "Sequence view",
        "Component view",
        "Key design decisions",
        "What changed",
        "Known limits / not done",
    ]
    positions = [page.index(f"<h2>{h}</h2>") for h in headings]
    assert positions == sorted(positions)
    assert page.count("<svg viewBox") == 2
    assert page.count('class="card-box"') == 2
    # the component view switches to the graph on the same page instead of linking away
    assert '<button type="button" class="view-link" data-view="graph">' in page
    assert "href=" not in _overview_pane(page)
    assert '<button type="button" data-mode="overview" hidden>Overview</button>' in page
    payload = page.split("const DATA = ", 1)[1].split(";\n", 1)[0]
    assert json.loads(payload) == DIAGRAM


def test_without_overview_the_diagram_is_unchanged(tmp_path):
    page = render.write(DIAGRAM, tmp_path / "diagram.html").read_text(encoding="utf-8")
    assert '<div class="overview" id="overview" role="region" aria-label="Overview"></div>' in page


def test_optional_sections_are_left_out(tmp_path):
    pane = _overview_pane(_render(tmp_path, _minimal()))
    for gone in ("<svg viewBox", "Network view", "Sequence view", 'class="card-box"'):
        assert gone not in pane
    assert "Component view" in pane and "Key design decisions" in pane and "Known limits" in pane


def test_text_is_escaped_and_backticks_become_code(tmp_path):
    data = _minimal()
    data["title"] = "</script><b>x</b> /*__DATA__*/null"
    data["summary"] = "uses `<iframe>` & more"
    data["network"] = {
        "caption": "c",
        "zones": [{"id": "z", "label": "<z>", "role": "blue"}],
        "nodes": [{"id": "a", "zone": "z", "title": "`a<b>`"}],
        "edges": [],
    }
    page = _render(tmp_path, data)
    assert "<b>x</b>" not in page and "&lt;/script&gt;&lt;b&gt;x&lt;/b&gt; /*__DATA__*/null" in page
    assert "uses <code>&lt;iframe&gt;</code> &amp; more" in page
    assert '<tspan class="code">a&lt;b&gt;</tspan>' in page
    assert "&lt;Z&gt;" in page
    assert "const DATA = {" in page


def _cli_render(tmp_path, diagram, overview_data) -> int:
    paths = []
    for name, data in (("data.json", diagram), ("overview.json", overview_data)):
        paths.append(tmp_path / name)
        paths[-1].write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "diagram.html"
    return main(["render", str(paths[0]), str(out), "--overview", str(paths[1])])


def test_every_problem_in_both_files_is_listed_at_once(tmp_path, capsys):
    diagram = copy.deepcopy(DIAGRAM)
    diagram["edges"][0]["kind"] = "uses"
    data = copy.deepcopy(SAMPLE)
    del data["summary"]
    data["bullets"] = ["only one"]
    data["stats"]["commits"] = -1
    data["decisions"][0]["why"] = ""
    data["network"]["zones"].append({"id": "empty", "label": "Empty", "role": "pink"})
    data["network"]["edges"].append({"from": "browser", "to": "ghost", "label": "x"})
    data["network"]["edges"].append({"from": "web", "to": "db", "label": "again"})
    data["sequence"]["messages"].append({"from": "web", "to": "nobody", "label": "x", "colour": 1})
    assert _cli_render(tmp_path, diagram, data) == 1
    err = capsys.readouterr().err.splitlines()
    assert err[0] == "foreman: invalid diagram and overview: 11 problems"
    assert sorted(err[1:]) == sorted(
        [
            "edge cart_view->cart: kind must be one of ['call', 'cycle', 'forbidden', 'impl', 'import']",
            "overview: missing 'summary'",
            "bullets: needs 3 to 6 items, got 1",
            "stats: 'commits' must be a whole number, 0 or more",
            "decisions #0: 'why' must be a non-empty string",
            (
                "network zones #3: 'role' must be one of "
                "['neutral', 'blue', 'green', 'purple', 'amber', 'red']"
            ),
            "network zone 'empty' has no nodes (drop it)",
            "network edge 'browser' -> 'ghost': unknown node",
            "network edge 'web' -> 'db': second edge between the same pair (use one with 'both')",
            "sequence messages #9: unknown key 'colour'",
            "sequence message 'x': unknown participant 'nobody'",
        ]
    )
    assert not (tmp_path / "diagram.html").exists()


def test_one_problem_is_singular(tmp_path, capsys):
    data = copy.deepcopy(SAMPLE)
    data["limits"] = []
    assert _cli_render(tmp_path, DIAGRAM, data) == 1
    assert capsys.readouterr().err.splitlines()[0] == (
        "foreman: invalid diagram and overview: 1 problem"
    )


def test_overview_goes_with_a_diagram_only(tmp_path):
    with pytest.raises(ValueError, match="an overview goes with a diagram, not a map"):
        render.write({"kind": "map", "title": "t"}, tmp_path / "m.html", SAMPLE)


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(network=[]),
        lambda d: d["network"].update(nodes={"a": 1}),
        lambda d: d["network"]["nodes"].append("x"),
        lambda d: d["network"]["nodes"][0].update(id=["a"], zone={"z": 1}),
        lambda d: d["network"]["edges"][0].update(**{"from": ["browser"]}),
        lambda d: d["sequence"]["participants"].append(None),
        lambda d: d["sequence"]["messages"][0].update(to=["web"]),
        lambda d: d.update(cards=[{"title": "t", "bullets": []}]),
        lambda d: d.update(limits="none"),
    ],
)
def test_malformed_shapes_are_problems_not_exceptions(change):
    data = copy.deepcopy(SAMPLE)
    change(data)
    assert overview.validate(data)


def _overlap(a, b) -> bool:
    (ax, ay, aw, ah), (bx, by, bw, bh) = a, b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


# A hub with three neighbours in its own zone (one stacked next to it, two further down) and two
# edges ending on the same side of the browser.
HUB = {
    "caption": "c",
    "zones": [
        {"id": "device", "label": "Shopper's device", "role": "neutral"},
        {"id": "cloud", "label": "Our cloud", "role": "blue"},
        {"id": "pay", "label": "Payments provider", "role": "purple"},
    ],
    "nodes": [
        {"id": "browser", "zone": "device", "title": "Browser"},
        {"id": "app", "zone": "cloud", "title": "App server"},
        {"id": "config", "zone": "cloud", "title": "Config store"},
        {"id": "db", "zone": "cloud", "title": "Database"},
        {"id": "cache", "zone": "cloud", "title": "Cache"},
        {"id": "form", "zone": "pay", "title": "Card form"},
    ],
    "edges": [
        {"from": "app", "to": "config", "label": "settings"},
        {"from": "app", "to": "db", "label": "orders", "both": True},
        {"from": "app", "to": "cache", "label": "cart totals", "sublabel": "1 min"},
        {"from": "browser", "to": "app", "label": "HTTPS server to server", "both": True},
        {"from": "form", "to": "browser", "label": "card fields", "style": "dashed"},
    ],
}


# Four zones and three edges that skip a zone, so three lanes above the zones.
SKIPS = {
    "caption": "c",
    "zones": [{"id": z, "label": z, "role": "neutral"} for z in ("w", "x", "y", "z")],
    "nodes": [
        {"id": "w1", "zone": "w", "title": "Browser"},
        {"id": "x1", "zone": "x", "title": "Shop web app"},
        {"id": "x2", "zone": "x", "title": "Worker"},
        {"id": "x3", "zone": "x", "title": "Scheduler"},
        {"id": "y1", "zone": "y", "title": "Database"},
        {"id": "z1", "zone": "z", "title": "Payments API"},
    ],
    "edges": [
        {"from": "w1", "to": "y1", "label": "never", "sublabel": "drawn for the test only"},
        {"from": "w1", "to": "z1", "label": "card fields", "sublabel": "hosted by the provider"},
        {"from": "x2", "to": "z1", "label": "charge", "style": "dashed"},
        {"from": "w1", "to": "x1", "label": "claim / delivery / id"},
        {"from": "x1", "to": "x2", "label": "claim / delivery / id", "sublabel": "queued"},
    ],
}


@pytest.mark.parametrize("net", [SAMPLE["network"], HUB, SKIPS], ids=["sample", "hub", "skips"])
def test_network_layout_keeps_labels_boxes_and_arrowheads_apart(net):
    assert overview.validate({**_minimal(), "network": net}) == []
    lay = overview.network_layout(net)
    labels = [lk["label"]["box"] for lk in lay["links"]]
    nodes = [(b["x"], b["y"], b["w"], b["h"]) for b in lay["nodes"].values()]
    titles = [(z["x"], z["y"], z["w"], lay["head"]) for z in lay["zones"]]
    assert not [p for p in combinations(labels, 2) if _overlap(*p)]
    assert not [(a, b) for a in labels for b in nodes + titles if _overlap(a, b)]
    assert not [p for p in combinations(nodes, 2) if _overlap(*p)]
    assert all(x + w <= lay["width"] and y + h <= lay["height"] for x, y, w, h in labels + nodes)
    close = [
        (p, q)
        for p, q in combinations(lay["ends"].values(), 2)
        if p[0] == q[0] and abs(p[1] - q[1]) < overview.END_PITCH
    ]
    assert not close


def _label_lines(page: str) -> dict[str, list[str]]:
    """Each edge label's text lines by class, keyed by the first line."""
    groups = [g.split("</g>", 1)[0] for g in page.split('<g class="label">')[1:]]
    found = [re.findall(r'class="label-(main|sub)"[^>]*>([^<]*)<', g) for g in groups]
    return {lines[0][1]: lines for lines in found}


def test_zones_fit_their_own_nodes_and_short_labels_stay_on_one_line():
    lay = overview.network_layout(SKIPS)
    heights = {z["title"][0]: z["h"] for z in lay["zones"]}
    assert heights["W"] < heights["X"]  # one node against three
    # between zones and beside a stacked line alike
    short = [lk["label"] for lk in lay["links"] if lk["edge"]["label"].startswith("claim")]
    assert [lab["main"] for lab in short] == [["claim / delivery / id"]] * 2


def test_a_wide_figure_shrinks_only_so_far_then_scrolls(tmp_path):
    wide = {
        "caption": "c",
        "zones": [{"id": f"z{i}", "label": f"zone {i}", "role": "neutral"} for i in range(5)],
        "nodes": [{"id": f"n{i}", "zone": f"z{i}", "title": f"node {i}"} for i in range(5)],
        "edges": [
            {"from": f"n{i}", "to": f"n{i + 1}", "label": "a label long enough to widen gaps"}
            for i in range(4)
        ],
    }
    width = overview.network_layout(wide)["width"]
    assert width > overview.WIDTH / overview.MIN_SCALE  # wide enough to need the floor
    page = _render(tmp_path, {**_minimal(), "network": wide})
    assert f'style="width:{width:.0f}px;min-width:{width * overview.MIN_SCALE:.0f}px"' in page
    assert "overflow-x: auto;" in page.split(".overview figure.drawing {", 1)[1].split("}", 1)[0]


def test_sequence_text_has_a_backing_where_lifelines_cross_it(tmp_path):
    seq = {
        "caption": "c",
        "participants": [{"id": p, "label": p} for p in ("web", "db", "pay")],
        "messages": [{"from": "web", "to": "pay", "label": "charge", "notes": ["skips db"]}],
    }
    page = _render(tmp_path, {**_minimal(), "sequence": seq})
    svg = page.split("<h2>Sequence view</h2>", 1)[1].split("</svg>", 1)[0]
    db_x = float(re.findall(r'<line class="lifeline" x1="([\d.]+)"', svg)[1])
    rects = [
        tuple(map(float, r))
        for r in re.findall(
            r'class="msg-bg" x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"', svg
        )
    ]
    texts = re.findall(r'y="([\d.]+)" class="msg-(?:label|note)"', svg)
    for y in map(float, texts):  # each text line sits on a rect that covers db's lifeline
        assert any(x <= db_x <= x + w and top <= y - 4 <= top + h for x, top, w, h in rects), y
    assert svg.index("lifeline") < svg.index("msg-bg")  # backings are drawn over the lifelines


def test_wrapped_label_lines_keep_label_style(tmp_path):
    hub = copy.deepcopy(HUB)
    hub["edges"][3]["label"] = "HTTPS server to server and then some more words"
    labels = _label_lines(_render(tmp_path, {**_minimal(), "network": hub}))
    https = next(v for k, v in labels.items() if k.startswith("HTTPS"))
    assert len(https) > 1 and {kind for kind, _ in https} == {"main"}
    assert labels["cart totals"] == [("main", "cart totals"), ("sub", "1 min")]


def test_documented_example_is_valid():
    doc = Path(__file__).parents[1] / "skills" / "review" / "references" / "overview.md"
    example = doc.read_text(encoding="utf-8").split("```json\n", 1)[1].split("```", 1)[0]
    assert overview.validate(json.loads(example)) == []
