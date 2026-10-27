import json
import os
import subprocess
import sys
from pathlib import Path

from foreman import codemap, render
from foreman.config import DEFAULTS

RUN = str(Path(__file__).resolve().parents[1] / "scripts" / "run.py")


def _config(**rules):
    return {**DEFAULTS, "rules": rules}


def test_type_only_cycle_is_not_a_smell(make_repo):
    root = make_repo(
        {
            "a.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import b\n",
            "b.py": "import a\n",
        }
    )
    data = codemap.build(root, _config())
    assert [s for s in data["smells"] if s["kind"] == "cycle"] == []
    assert {e["kind"] for e in data["edges"]} == {"import"}


def test_runtime_cycle_edges_are_marked(make_repo):
    data = codemap.build(make_repo({"a.py": "import b\n", "b.py": "import a\n"}), _config())
    assert [e["kind"] for e in data["edges"]] == ["cycle", "cycle"]
    assert [s["kind"] for s in data["smells"]] == ["cycle"]


def test_layering_rule_flags_forbidden_edge(make_repo):
    root = make_repo({"core/a.py": "import app.b\n", "app/b.py": "", "app/c.py": "import core.a\n"})
    data = codemap.build(root, _config(layers=[{"from": "core/**", "to": "app/**"}]))
    assert {(e["from"], e["kind"]) for e in data["edges"]} == {
        ("core/a.py", "forbidden"),
        ("app/c.py", "import"),
    }
    assert [s["nodes"] for s in data["smells"] if s["kind"] == "layering"] == [
        ["core/a.py", "app/b.py"]
    ]


def test_map_groups_descend_from_single_src_dir(make_repo):
    root = make_repo({"src/a/x.py": "import src.b.y\n", "src/b/y.py": "", "src/b/z.py": ""})
    data = codemap.build(root, _config())
    assert data["groups"] == [
        {"id": "src/a", "label": "src/a", "nodes": ["src/a/x.py"]},
        {"id": "src/b", "label": "src/b", "nodes": ["src/b/y.py", "src/b/z.py"]},
    ]
    assert data["nodes"][0] == {
        "id": "src/a/x.py",
        "label": "x.py",
        "group": "src/a",
        "lang": "python",
        "lines": 1,
    }


def test_map_validates_and_renders(make_repo, tmp_path):
    root = make_repo({"pkg/a.py": "import pkg.b\n", "pkg/b.py": "x = 1\n", "lib.rb": "puts 1\n"})
    data = codemap.build(root, _config())
    assert data["unsupported"] == {".rb": 1}
    assert render.validate(data) == []
    html = render.write(data, tmp_path / "map.html").read_text(encoding="utf-8")
    assert "/*__DATA__*/null" not in html
    bad = {**data, "edges": [{"from": "pkg/a.py", "to": "nope", "kind": "call"}]}
    assert len(render.validate(bad)) == 2


def test_map_output_identical_across_hash_seeds(make_repo, tmp_path):
    files = {f"m{i}/f{j}.py": f"import m{(i + 1) % 3}.f{j}\n" for i in range(3) for j in range(3)}
    root = make_repo(files)
    outs = []
    for seed in ("1", "2"):
        out = tmp_path / f"out{seed}"
        # not -I: isolated mode ignores PYTHONHASHSEED
        result = subprocess.run(
            [sys.executable, RUN, "map", "--root", str(root), "--out", str(out)],
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            encoding="utf-8",
            check=True,
        )
        printed = json.loads(result.stdout)
        assert printed.pop("html") == (out / "map.html").as_posix()
        outs.append((printed, (out / "map.json").read_text(encoding="utf-8")))
    assert outs[0] == outs[1]
    assert outs[0][0]["smells"]


def test_malformed_map_is_problems_not_exceptions():
    bad = {
        "kind": "map",
        "title": "t",
        "groups": [],
        "nodes": [{"id": ["x"]}],
        "edges": {},
        "smells": [],
    }
    assert render.validate(bad) == [
        "nodes #0: must be an object with string id, label, group, lang",
        "'edges' must be a list",
    ]


def test_ungraphed_sources_are_map_nodes(make_repo):
    body = "\n".join(f"total += price * {i}" for i in range(10))
    root = make_repo({"a.rb": body, "lib/b.rb": body, "c.py": "", "LICENSE": "x\n"})
    data = codemap.build(root, _config())
    nodes = {n["id"]: n["lang"] for n in data["nodes"]}
    assert nodes == {"a.rb": ".rb", "lib/b.rb": ".rb", "c.py": "python"}
    assert [s["nodes"] for s in data["smells"] if s["kind"] == "duplicate"] == [
        ["a.rb", "lib/b.rb"]
    ]
    assert [s["nodes"] for s in data["smells"] if s["kind"] == "deadcode"] == [["c.py"]]
    assert data["unsupported"] == {".rb": 2}
    assert render.validate(data) == []


def test_go_package_layering(make_repo):
    root = make_repo(
        {
            "go.mod": "module example.com/shop\n\ngo 1.22\n",
            "core/core.go": 'package core\n\nimport "example.com/shop/app"\n\nvar _ = app.Name\n',
            "app/app.go": "package app\n\nconst Name = 1\n",
        }
    )
    data = codemap.build(root, _config(layers=[{"from": "core/**", "to": "app/**"}]))
    assert data["edges"] == [{"from": "core", "to": "app", "kind": "forbidden"}]
    assert [s["nodes"] for s in data["smells"] if s["kind"] == "layering"] == [["core", "app"]]
