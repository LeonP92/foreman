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


def test_rejects_node_without_edges():
    assert "node b: has no edges (drop it or connect it)" in render.validate(_data(edges=[]))


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


def test_unknown_kind_is_rejected():
    assert render.validate({"kind": "pie"}) == ["kind must be one of ['diagram'], got 'pie'"]


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
    assert lines[0] == "foreman: invalid diagram: 3 problems"
    assert len(lines) == 4
    assert not (tmp_path / "d.html").exists()


@pytest.mark.parametrize("content", ["[]", "{"])
def test_cli_render_rejects_non_object(tmp_path, capsys, content):
    data = tmp_path / "d.json"
    data.write_text(content, encoding="utf-8")
    assert main(["render", str(data), str(tmp_path / "d.html")]) == 1
    assert capsys.readouterr().err.count("\n") == 1
