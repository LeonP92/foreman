import json
from pathlib import Path

import pytest
from foreman import render
from foreman.cli import main

SAMPLE = Path(__file__).parent / "data" / "diagram_sample.json"


def _data(nodes=None, edges=None, smells=()):
    nodes = nodes or [
        {
            "id": "a",
            "label": "a.py",
            "lane": "core",
            "status": "changed",
            "summary": {"changed": ["x"]},
        },
        {"id": "b", "label": "b.py", "lane": "core", "status": "affected"},
    ]
    edges = edges if edges is not None else [{"from": "a", "to": "b", "kind": "import"}]
    return {"title": "t", "lanes": ["core"], "nodes": nodes, "edges": edges, "smells": list(smells)}


def _smell(kind, nodes, **extra):
    return {"kind": kind, "severity": "low", "nodes": nodes, "title": "t", "evidence": "e", **extra}


def test_sample_renders(tmp_path):
    out = render.write(json.loads(SAMPLE.read_text(encoding="utf-8")), tmp_path / "d.html")
    html = out.read_text(encoding="utf-8")
    assert "/*__DATA__*/null" not in html
    assert 'id="filter"' in html
    assert "function focusNode(" in html


def test_diagram_inlines_shared_theme_and_ui(tmp_path):
    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    html = render.write(data, tmp_path / "d.html").read_text(encoding="utf-8")
    assert "/*__THEME__*/" not in html
    assert "/*__UI__*/" not in html
    assert "--surface-1" in html
    assert "#0d0d0d" in html
    assert "function openDrawer(" in html
    assert json.dumps(data).replace("<", "\\u003c") in html
    assert "http" not in html.replace("http://www.w3.org/2000/svg", "")


def test_only_affected_nodes_need_edges():
    assert render.validate(_data(edges=[])) == ["node b: has no edges (drop it or connect it)"]
    standalone = [
        {"id": s, "label": s, "lane": "core", "status": s, "summary": {"added": ["x"]}}
        for s in ("added", "changed", "removed")
    ]
    assert render.validate(_data(nodes=standalone, edges=[])) == []


def test_rejects_smell_without_evidence():
    errs = render.validate(_data(smells=[_smell("twin", ["a", "b"], evidence=" ")]))
    assert any("missing evidence" in e for e in errs)


def test_twin_needs_exactly_two_nodes():
    errs = render.validate(_data(smells=[_smell("twin", ["a"])]))
    assert any("twin needs exactly 2 distinct nodes, got 1" in e for e in errs)
    assert render.validate(_data(smells=[_smell("twin", ["a", "b"])])) == []


def test_hub_needs_five_neighbours():
    leaves = [
        {"id": f"n{i}", "label": f"n{i}", "lane": "core", "status": "affected"} for i in range(5)
    ]
    hub = {
        "id": "h",
        "label": "h",
        "lane": "core",
        "status": "changed",
        "summary": {"added": ["x"]},
    }
    edges = [{"from": "h", "to": f"n{i}", "kind": "call"} for i in range(5)]
    assert render.validate(_data([hub, *leaves], edges, [_smell("hub", ["h"])])) == []
    errs = render.validate(_data([hub, *leaves[:4]], edges[:4], [_smell("hub", ["h"])]))
    assert any("hub has 4 neighbours" in e for e in errs)


def test_script_close_tag_in_data_is_escaped(tmp_path):
    data = _data()
    data["title"] = "</script><script>alert(1)</script>"
    html = render.write(data, tmp_path / "d.html").read_text(encoding="utf-8")
    assert "alert(1)</script>" not in html
    payload = html.split("const DATA = ", 1)[1].split(";\n", 1)[0]
    assert json.loads(payload) == data


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(nodes={"a": 1}),
        lambda d: d.update(lanes=[["core"]]),
        lambda d: d["nodes"].append("c.py"),
        lambda d: d["edges"].append(None),
        lambda d: d["nodes"][0].update(id=["a"], label=3),
        lambda d: d["nodes"][0].update(summary=["x"]),
        lambda d: d["nodes"][0].update(summary={"added": "x"}),
        lambda d: d["nodes"][0]["summary"]["changed"].append(7),
        lambda d: d["edges"][0].update(**{"from": {"id": "a"}}),
        lambda d: d.update(smells=[_smell("twin", [["a"], "b"])]),
        lambda d: d.update(smells=[_smell({"k": 1}, ["a", "b"])]),
        lambda d: d.update(smells=[_smell("hub", ["a"])], edges=[{"to": "b", "from": "a"}, {}]),
    ],
)
def test_malformed_shapes_are_problems_not_exceptions(change):
    data = _data()
    change(data)
    assert render.validate(data)


def test_cli_render_malformed_has_no_traceback(tmp_path, capsys):
    data = tmp_path / "d.json"
    data.write_text(json.dumps({**_data(), "nodes": [1, "x"], "edges": {}}), encoding="utf-8")
    assert main(["render", str(data), str(tmp_path / "d.html")]) == 1
    err = capsys.readouterr().err
    assert err.splitlines()[0] == "foreman: invalid diagram: 3 problems"
    assert "Traceback" not in err


def test_unknown_kind_is_rejected():
    assert render.validate({"kind": "pie"}) == ["kind must be one of ['diagram', 'map'], got 'pie'"]


def test_cli_render_writes_file(tmp_path, capsys):
    out = tmp_path / "d.html"
    assert main(["render", str(SAMPLE), str(out)]) == 0
    assert json.loads(capsys.readouterr().out) == {"path": out.as_posix()}
    assert out.exists()


def test_cli_render_lists_every_problem(tmp_path, capsys):
    data = tmp_path / "d.json"
    data.write_text(json.dumps(_data(edges=[], smells=[_smell("twin", ["a"])])), encoding="utf-8")
    assert main(["render", str(data), str(tmp_path / "d.html")]) == 1
    lines = capsys.readouterr().err.splitlines()
    assert lines[0] == "foreman: invalid diagram: 2 problems"
    assert len(lines) == 3
    assert not (tmp_path / "d.html").exists()


@pytest.mark.parametrize("content", ["[]", "{"])
def test_cli_render_rejects_non_object(tmp_path, capsys, content):
    data = tmp_path / "d.json"
    data.write_text(content, encoding="utf-8")
    assert main(["render", str(data), str(tmp_path / "d.html")]) == 1
    assert capsys.readouterr().err.count("\n") == 1


def test_rejects_empty_nodes():
    assert "nodes must not be empty" in render.validate({**_data(), "nodes": [], "edges": []})


def test_hub_self_edge_is_not_a_neighbour():
    hub = {
        "id": "h",
        "label": "h",
        "lane": "core",
        "status": "changed",
        "summary": {"added": ["x"]},
    }
    leaves = [
        {"id": f"n{i}", "label": f"n{i}", "lane": "core", "status": "affected"} for i in range(4)
    ]
    edges = [{"from": "h", "to": f"n{i}", "kind": "call"} for i in range(4)]
    edges.append({"from": "h", "to": "h", "kind": "call"})
    errs = render.validate(_data([hub, *leaves], edges, [_smell("hub", ["h"])]))
    assert any("hub has 4 neighbours" in e for e in errs)


def _map_data():
    return {
        "kind": "map",
        "title": "</script><script>alert(1)</script>",
        "notes": "",
        "groups": [{"id": "src", "label": "src", "layer": 0, "nodes": ["src/a.py"]}],
        "nodes": [
            {"id": "src/a.py", "label": "a.py", "group": "src", "lang": "python", "lines": 3}
        ],
        "edges": [],
        "packages": [],
        "smells": [],
        "unsupported": {".rb": 2},
    }


def test_map_inlines_theme_and_escapes_payload(tmp_path):
    data = _map_data()
    html = render.write(data, tmp_path / "map.html").read_text(encoding="utf-8")
    assert "/*__" not in html
    assert "#0d0d0d" in html
    assert "function openDrawer(" in html
    assert "alert(1)</script>" not in html
    payload = html.split("const DATA = ", 1)[1].split(";\n", 1)[0]
    assert json.loads(payload) == data


def test_map_unsupported_must_map_extensions_to_counts():
    data = {**_map_data(), "unsupported": {".rb": "<img src=x onerror=alert(1)>"}}
    assert render.validate(data) == ["'unsupported' must map extensions to file counts"]
