import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from foreman import codemap, render
from foreman.cli import main
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
        {"id": "src/a", "label": "src/a", "layer": 0, "nodes": ["src/a/x.py"]},
        {"id": "src/b", "label": "src/b", "layer": 1, "nodes": ["src/b/y.py", "src/b/z.py"]},
    ]
    assert data["nodes"][0] == {
        "id": "src/a/x.py",
        "label": "x.py",
        "group": "src/a",
        "lang": "python",
        "lines": 1,
    }


def test_map_renders(make_repo, tmp_path):
    root = make_repo({"pkg/a.py": "import pkg.b\n", "pkg/b.py": "x = 1\n", "lib.rb": "puts 1\n"})
    data = codemap.build(root, _config())
    assert data["unsupported"] == {".rb": 1}
    html = render.write(data, tmp_path / "map.html").read_text(encoding="utf-8")
    assert "/*__DATA__*/null" not in html


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


def test_ungraphed_sources_are_map_nodes(make_repo):
    body = "\n".join(f"total += price * {i}" for i in range(12))
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
    assert data["packages"] == [
        {"from": "core", "to": "app", "imports": 1, "kind": "forbidden", "dir": "up"}
    ]
    assert [s["nodes"] for s in data["smells"] if s["kind"] == "layering"] == [["core", "app"]]


def _layers(data):
    return {g["id"]: g["layer"] for g in data["groups"]}


def _packages(data):
    return {(p["from"], p["to"]): (p["kind"], p["dir"], p["imports"]) for p in data["packages"]}


def test_groups_are_layered_by_longest_path_to_a_sink(make_repo):
    root = make_repo(
        {
            "app/main.py": "import svc.orders\nimport core.db\n",
            "svc/orders.py": "import core.db\n",
            "tool/cli.py": "import core.db\n",
            "core/db.py": "",
        }
    )
    data = codemap.build(root, _config())
    assert _layers(data) == {"app": 0, "core": 2, "svc": 1, "tool": 1}
    # ties in a layer keep group id order
    assert [g["id"] for g in data["groups"] if g["layer"] == 1] == ["svc", "tool"]
    assert {d for _, d, _ in _packages(data).values()} == {"down"}


def test_groups_in_a_cycle_share_a_layer_and_the_back_edge_is_up(make_repo):
    root = make_repo(
        {
            "a/x.py": "import b.y\nimport c.z\n",
            "b/y.py": "",
            "b/w.py": "import a.v\n",
            "a/v.py": "",
            "c/z.py": "",
        }
    )
    data = codemap.build(root, _config())
    assert _layers(data) == {"a": 0, "b": 0, "c": 1}
    assert _packages(data) == {
        ("a", "b"): ("import", "down", 1),
        ("a", "c"): ("import", "down", 1),
        ("b", "a"): ("cycle", "up", 1),
    }


def test_forbidden_edges_do_not_order_layers_and_flow_up(make_repo):
    root = make_repo({"core/a.py": "import app.b\n", "app/b.py": "", "app/c.py": "import core.a\n"})
    data = codemap.build(root, _config(layers=[{"from": "core/**", "to": "app/**"}]))
    assert _layers(data) == {"app": 0, "core": 1}
    assert _packages(data) == {
        ("core", "app"): ("forbidden", "up", 1),
        ("app", "core"): ("import", "down", 1),
    }


def test_type_only_back_edge_is_not_a_package_cycle(make_repo):
    root = make_repo(
        {
            "a/x.py": "import b.y\n",
            "b/y.py": "",
            "b/w.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import a.v\n",
            "a/v.py": "",
        }
    )
    data = codemap.build(root, _config())
    assert _layers(data) == {"a": 0, "b": 1}
    assert _packages(data) == {("a", "b"): ("import", "down", 1), ("b", "a"): ("import", "up", 1)}


def test_package_takes_its_most_severe_module_kind(make_repo):
    root = make_repo(
        {
            "a/x.py": "import b.y\n",
            "b/y.py": "import a.x\n",
            "core/a.py": "import app.b\n",
            "core/d.py": "import app.b\n",
            "app/b.py": "",
        }
    )
    data = codemap.build(root, _config(layers=[{"from": "core/a.py", "to": "app/**"}]))
    packages = _packages(data)
    # a module cycle inside a downward pair, and one forbidden import among plain ones
    assert packages[("a", "b")] == ("cycle", "down", 1)
    assert packages[("core", "app")] == ("forbidden", "down", 2)


def test_excepted_target_is_a_plain_import(make_repo):
    root = make_repo(
        {"core/a.py": "import app.b\nimport app.api\n", "app/b.py": "", "app/api.py": ""}
    )
    rule = {"from": "core/**", "to": "app/**", "except": ["app/api.py"]}
    data = codemap.build(root, _config(layers=[rule]))
    assert {e["to"]: e["kind"] for e in data["edges"]} == {
        "app/api.py": "import",
        "app/b.py": "forbidden",
    }


def test_configured_entry_points_and_infra_files(make_repo):
    root = make_repo(
        {"plugins/extra.py": "", "lonely.py": "", "infra/main.tf": 'resource "x" "y" {}\n'}
    )
    data = codemap.build(root, {**DEFAULTS, "audit": {"entry_points": ["plugins/*.py"]}})
    assert [s["nodes"] for s in data["smells"] if s["kind"] == "deadcode"] == [["lonely.py"]]
    assert "infra/main.tf" not in {n["id"] for n in data["nodes"]}


def test_map_counts_every_smell_and_what_the_cap_dropped(make_repo, tmp_path, capsys):
    root = make_repo({f"m{i:02}.py": "" for i in range(23)})
    out = tmp_path / "out"
    assert main(["map", "--root", str(root), "--out", str(out)]) == 0
    printed = json.loads(capsys.readouterr().out)
    data = json.loads((out / "map.json").read_text(encoding="utf-8"))
    for result in (printed, data):
        assert result["dropped"] == {"deadcode": 3}
        assert result["counts"] == {"deadcode": {"low": 23}}
        assert len(result["smells"]) == 20
    assert len(printed["triage"]) == 20 and printed["not_triaged"] == {"deadcode": 3}


@pytest.mark.slow
def test_large_repo_maps_quickly(make_repo):
    files = {
        f"pkg{i % 30}/mod{i}.py": f"import pkg{(i + 1) % 30}.mod{i + 1}\n"
        + "\n".join(f"value_{i}_{j} = {j} * {i}  # see mod{i - 1}.py" for j in range(40))
        for i in range(3000)
    }
    files.update(
        {f"docs/page{i}.md": f"See `mod{i}` and pkg{i % 30}/mod{i}.py.\n" for i in range(200)}
    )
    root = make_repo(files)
    start = time.perf_counter()
    data = codemap.build(root, _config())
    # measured 3.0 s (mention scan 0.3 s) on a laptop; the bound catches a per-file scan
    assert time.perf_counter() - start < 30
    assert len(data["nodes"]) == 3000


def _write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_map_dismiss_drops_triaged_smells_and_keeps_counts(make_repo, tmp_path, capsys):
    root = make_repo({f"m{i:02}.py": "" for i in range(23)})
    out = tmp_path / "out"
    assert main(["map", "--root", str(root), "--out", str(out)]) == 0
    capsys.readouterr()
    triage = {"dismissed": [{"kind": "deadcode", "nodes": ["m00.py"], "reason": "loaded by name"}]}
    path = _write_json(tmp_path / "triage.json", triage)
    assert main(["map", "--out", str(out), "--dismiss", path]) == 0
    printed = json.loads(capsys.readouterr().out)
    data = json.loads((out / "map.json").read_text(encoding="utf-8"))
    for result in (printed, data):
        assert result["dismissed"] == {"deadcode": 1}
        assert result["dropped"] == {"deadcode": 3}
        assert result["counts"] == {"deadcode": {"low": 23}}
        assert ["m00.py"] not in [s["nodes"] for s in result["smells"]]
        assert len(result["smells"]) == 19
    assert data["dismissed_by_severity"] == {"deadcode": {"low": 1}}
    assert data["dropped_by_severity"] == {"deadcode": {"low": 3}}
    assert '"dismissed": {"deadcode": 1}' in (out / "map.html").read_text(encoding="utf-8")
    # the same triage again is a no-op
    assert main(["map", "--out", str(out), "--dismiss", path]) == 0
    assert json.loads(capsys.readouterr().out)["dismissed"] == {"deadcode": 1}


def test_map_dismiss_rejects_unknown_kind_or_nodes(make_repo, tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["map", "--root", str(make_repo({"a.py": ""})), "--out", str(out)]) == 0
    for entry, error in [
        ({"kind": "smelly", "nodes": ["a.py"], "reason": "x"}, "unknown kind 'smelly'"),
        ({"kind": "deadcode", "nodes": ["b.py"], "reason": "x"}, "no listed deadcode smell"),
        ({"kind": "deadcode", "nodes": ["a.py"]}, "needs a string kind, a list of nodes"),
    ]:
        capsys.readouterr()
        path = _write_json(tmp_path / "triage.json", {"dismissed": [entry]})
        assert main(["map", "--out", str(out), "--dismiss", path]) == 1
        err = capsys.readouterr().err
        assert error in err and err.count("\n") == 1


def test_map_title_names_the_origin_or_main_checkout_not_a_worktree(make_repo, tmp_path):
    root = make_repo({"a.py": ""})
    worktree = tmp_path.parent / f"{tmp_path.name}-wt-1a2b"
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(worktree)],
        cwd=root,
        check=True,
        capture_output=True,
    )
    assert codemap.build(worktree, _config())["title"] == f"Codebase map: {root.name}"
    for verb, url in [
        ("add", "git@example.com:team/shop.git"),
        ("set-url", "https://x.test/shop/"),
    ]:
        subprocess.run(["git", "remote", verb, "origin", url], cwd=root, check=True)
        assert codemap.build(worktree, _config())["title"] == "Codebase map: shop"


def test_skipped_extensions_are_still_mapped(make_repo):
    root = make_repo({"a.py": "", "run.sh": "echo hi\n"})
    data = codemap.build(root, {**DEFAULTS, "graph": {"skip": [".sh"]}})
    assert data["unsupported"] == {}
    assert "run.sh" in {n["id"] for n in data["nodes"]}


def _oversize_map():
    smell = {"kind": "oversize", "severity": "low", "nodes": ["a.py"], "evidence": "big"}
    return {
        "smells": [
            {**smell, "title": "Large file: a.py"},
            {**smell, "title": "Long function: `run` in a.py"},
        ]
    }


def test_dismiss_matches_one_smell_by_title():
    entry = {"kind": "oversize", "nodes": ["a.py"], "reason": "generated"}
    data = codemap.dismiss(_oversize_map(), {"dismissed": [{**entry, "title": "Large file: a.py"}]})
    assert [s["title"] for s in data["smells"]] == ["Long function: `run` in a.py"]
    assert data["dismissed"] == {"oversize": 1}
    with pytest.raises(ValueError, match="2 listed oversize smells match") as err:
        codemap.dismiss(_oversize_map(), {"dismissed": [entry]})
    assert "Long function: `run` in a.py" in str(err.value)


def test_dismiss_keeps_the_first_reason_for_a_smell():
    entry = {"kind": "oversize", "nodes": ["a.py"], "title": "Large file: a.py"}
    triage = {"dismissed": [{**entry, "reason": "generated"}, {**entry, "reason": "vendored"}]}
    data = codemap.dismiss(_oversize_map(), triage)
    assert [s["reason"] for s in data["dismissed_smells"]] == ["generated"]


@pytest.mark.skipif(os.name == "nt", reason="bytes arguments are POSIX-only")
def test_a_file_name_that_is_not_utf8_is_skipped(make_repo):
    root = make_repo({"a.py": "import b\n", "b.py": ""})
    git = [
        "git",
        "-c",
        "commit.gpgsign=false",
        "-c",
        "user.name=T",
        "-c",
        "user.email=t@example.com",
    ]
    blob = subprocess.run(
        [*git, "hash-object", "-w", "b.py"], cwd=root, capture_output=True, check=True
    ).stdout.strip()
    # committed straight to the index: some file systems refuse such a name on disk
    subprocess.run(
        [*git, "update-index", "--add", "--cacheinfo", b"100644," + blob + b",bad\xff.py"],
        cwd=root,
        check=True,
    )
    subprocess.run([*git, "commit", "-qm", "odd name"], cwd=root, check=True)
    data = codemap.build(root, _config())
    assert sorted(n["id"] for n in data["nodes"]) == ["a.py", "b.py"]
