import json

from foreman import smells
from foreman.metrics import percentiles


def _detect(
    nodes=(),
    edges=(),
    cycles=(),
    churn=None,
    pairs=(),
    files=(),
    functions=(),
    blocks=(),
    layers=(),
    entry_points=(),
    facades=(),
):
    ids = sorted({*nodes, *(n for e in edges for n in e), *(n for c in cycles for n in c)})
    graph = {
        "nodes": [{"id": n, "lang": "python"} for n in ids],
        "edges": [{"from": a, "to": b, "type_only": False} for a, b in edges],
        "cycles": [list(c) for c in cycles],
    }
    history = {"churn": churn or {}, "pairs": list(pairs)}
    metrics = {
        "files": [{"path": p, "lines": n} for p, n in files],
        "functions": [{"path": p, "name": f, "start": 1, "lines": n} for p, f, n in functions],
        "stats": {
            "file_lines": percentiles([n for _, n in files]),
            "function_lines": percentiles([n for *_, n in functions]),
        },
    }
    return smells.detect(
        graph,
        history,
        metrics,
        {"blocks": list(blocks)},
        list(layers),
        frozenset(entry_points),
        frozenset(facades),
    )


def _kinds(found, kind):
    return [s for s in found if s["kind"] == kind]


def test_cycle_across_top_level_dirs_is_high():
    found = _kinds(_detect(cycles=[["a/x.py", "b/y.py"], ["c/x.py", "c/y.py"]]), "cycle")
    assert [(s["severity"], s["nodes"]) for s in found] == [
        ("high", ["a/x.py", "b/y.py"]),
        ("medium", ["c/x.py", "c/y.py"]),
    ]


def test_layering_flags_only_the_forbidden_direction():
    layers = [{"from": "core/**", "to": "app/**"}]
    found = _kinds(
        _detect(edges=[("core/a.py", "app/b.py"), ("app/b.py", "core/c.py")], layers=layers),
        "layering",
    )
    assert [(s["severity"], s["nodes"]) for s in found] == [("high", ["core/a.py", "app/b.py"])]


def test_layering_skips_targets_the_rule_excepts():
    layers = [{"from": "ui/**", "to": "data/**", "except": ["data/public/**", "data/types.py"]}]
    edges = [
        ("ui/a.py", "data/db.py"),
        ("ui/a.py", "data/public/api.py"),
        ("ui/a.py", "data/types.py"),
    ]
    found = _kinds(_detect(edges=edges, layers=layers), "layering")
    assert [s["nodes"] for s in found] == [["ui/a.py", "data/db.py"]]


def test_hub_at_floor_and_just_under():
    found = _kinds(_detect(edges=[("h.py", f"n{i}.py") for i in range(8)]), "hub")
    assert [s["nodes"] for s in found] == [["h.py"]]
    assert found[0]["evidence"] == "8 neighbours; repo p95 is 8, floor 8"
    assert _kinds(_detect(edges=[("h.py", f"n{i}.py") for i in range(7)]), "hub") == []


def _pair(both, conf, a="a.py", b="b.py"):
    return {"a": a, "b": b, "both": both, "conf": conf}


def test_cochange_thresholds():
    nodes = ["a.py", "b.py"]
    assert [s["severity"] for s in _kinds(_detect(nodes, pairs=[_pair(5, 0.6)]), "cochange")] == [
        "low"
    ]
    assert _kinds(_detect(nodes, pairs=[_pair(5, 0.8)]), "cochange")[0]["severity"] == "medium"
    assert _kinds(_detect(nodes, pairs=[_pair(4, 1.0)]), "cochange") == []
    assert _kinds(_detect(nodes, pairs=[_pair(5, 0.59)]), "cochange") == []
    assert _kinds(_detect(edges=[("b.py", "a.py")], pairs=[_pair(9, 1.0)]), "cochange") == []


def test_test_subject_pairs_are_not_cochange():
    pairs = [
        _pair(9, 1.0, "src/a.py", "tests/test_a.py"),
        _pair(9, 1.0, "b.ts", "b.spec.ts"),
        _pair(9, 1.0, "c.go", "c_test.go"),
    ]
    nodes = [p[k] for p in pairs for k in ("a", "b")]
    assert _kinds(_detect(nodes, pairs=pairs), "cochange") == []


def test_hotspot_at_threshold_and_just_under():
    files = [("hot.py", 100)] + [(f"f{i}.py", 10) for i in range(9)]
    churn = {p: 1 for p, _ in files}
    found = _kinds(
        _detect([p for p, _ in files], churn={**churn, "hot.py": 5}, files=files), "hotspot"
    )
    assert [(s["nodes"], s["severity"]) for s in found] == [(["hot.py"], "medium")]
    assert (
        _kinds(_detect([p for p, _ in files], churn={**churn, "hot.py": 4}, files=files), "hotspot")
        == []
    )


def test_oversize_file_at_floor_and_just_under():
    files = [(f"f{i}.py", 100) for i in range(20)]
    nodes = [p for p, _ in files] + ["big.py"]
    found = _kinds(_detect(nodes, files=[*files, ("big.py", 300)]), "oversize")
    assert [s["nodes"] for s in found] == [["big.py"]]
    assert _kinds(_detect(nodes, files=[*files, ("big.py", 299)]), "oversize") == []


def test_oversize_function_is_python_only_and_floored():
    functions = [("a.py", f"f{i}", 10) for i in range(20)]
    found = _kinds(_detect(["a.py"], functions=[*functions, ("a.py", "long", 60)]), "oversize")
    assert [s["severity"] for s in found] == ["low"]
    assert "Python only" in found[0]["evidence"]
    assert _kinds(_detect(["a.py"], functions=[*functions, ("a.py", "long", 59)]), "oversize") == []


def _block(lines, *paths):
    return {"lines": lines, "locations": [{"path": p, "start": 1, "end": lines} for p in paths]}


def test_duplicate_severity_and_order():
    blocks = [
        _block(19, "a.py", "b.py"),
        _block(8, "a.py", "b.py", "c.py"),
        _block(20, "a.py", "b.py"),
    ]
    found = _kinds(_detect(["a.py", "b.py", "c.py"], blocks=blocks), "duplicate")
    assert [(s["severity"], len(s["nodes"])) for s in found] == [
        ("medium", 2),
        ("medium", 3),
        ("low", 2),
    ]


def test_each_kind_is_capped_and_the_rest_counted():
    blocks = [_block(10 + i, "a.py", "b.py") for i in range(25)]
    found = _detect(["a.py", "b.py"], blocks=blocks, cycles=[["a.py", "b.py"]])
    shown, dropped = smells.cap(found)
    assert len(_kinds(shown, "duplicate")) == smells.MAX_PER_KIND
    assert _kinds(shown, "duplicate")[0]["evidence"].startswith("34 lines")
    assert len(_kinds(shown, "cycle")) == 1
    assert dropped == {"duplicate": 5}


def test_dead_code_skips_tests_and_entry_points():
    nodes = [
        "lonely.py",
        "pkg/__init__.py",
        "used.py",
        "main.py",
        "tests/test_x.py",
        "index.js",
        "web.config.js",
        "tool.py",
    ]
    found = _kinds(
        _detect(nodes, edges=[("main.py", "used.py")], entry_points=["tool.py"]), "deadcode"
    )
    assert [s["nodes"] for s in found] == [["lonely.py"]]


def test_entry_points_are_not_dead_code(make_repo):
    root = make_repo(
        {
            "package.json": json.dumps({"main": "lib/start.js", "bin": {"tool": "./bin/tool.js"}}),
            "pyproject.toml": '[project.scripts]\nrun = "pkg.run:main"\n',
            "broken/package.json": "{",
            "odd/pyproject.toml": "project = 3\n",
            "cmd/app/app.go": "package main\n\nfunc main() {}\n",
            "lib/start.js": "",
            "bin/tool.js": "",
            "pkg/__init__.py": "",
            "pkg/run.py": "",
            "tools/run.py": 'def main():\n    pass\n\n\nif __name__ == "__main__":\n    main()\n',
            "tools/lib.py": "def main():\n    pass\n",
            "hooks/check.js": "#!/usr/bin/env node\nconsole.log(1)\n",
        }
    )
    files = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and ".git" not in p.parts
    )
    assert smells.entry_points(root, files) == frozenset(
        ["lib/start.js", "bin/tool.js", "pkg/run.py", "cmd/app", "tools/run.py", "hooks/check.js"]
    )


def test_file_smells_cover_ungraphed_sources():
    files = [("a.rb", 10), ("b.rb", 10)]
    found = _detect(files=files, blocks=[_block(8, "a.rb", "b.rb")], churn={"a.rb": 1})
    assert [(s["kind"], s["nodes"]) for s in found] == [("duplicate", ["a.rb", "b.rb"])]


def test_same_name_modules_are_cochange():
    found = _kinds(
        _detect(
            pairs=[_pair(9, 1.0, "a/index.ts", "b/index.ts")], nodes=["a/index.ts", "b/index.ts"]
        ),
        "cochange",
    )
    assert [s["nodes"] for s in found] == [["a/index.ts", "b/index.ts"]]


def test_test_pairs_and_nested_test_subjects_are_not_cochange():
    pairs = [
        _pair(9, 1.0, "tests/test_a.py", "tests/test_b.py"),
        _pair(9, 1.0, "shop/cart.py", "tests/unit/shop/test_cart.py"),
        _pair(9, 1.0, "web/src/cart.ts", "web/__tests__/cart.ts"),
        _pair(9, 1.0, "web/src/cart.ts", "web/src/cart.test.ts"),
    ]
    nodes = [p[k] for p in pairs for k in ("a", "b")]
    assert _kinds(_detect(nodes, pairs=pairs), "cochange") == []


def test_hubs_skip_tests_conftest_and_facades_and_cap_entry_points():
    hubs = ["conftest.py", "tests/test_big.py", "pkg/__init__.py", "main.py", "mig/x.py", "h.py"]
    edges = [(h, f"n{i}.py") for h in hubs for i in range(8)]
    found = _kinds(
        _detect(edges=edges, entry_points=["mig/x.py"], facades=["pkg/__init__.py"]), "hub"
    )
    assert sorted((s["nodes"][0], s["severity"]) for s in found) == [
        ("h.py", "medium"),
        ("main.py", "low"),
        ("mig/x.py", "low"),
    ]


def test_path_loaded_files_are_entry_points(make_repo):
    files = {
        "app/migrations/0001_init.py": "",
        "alembic/versions/a1.py": "",
        "db/alembic.ini": "[alembic]\nscript_location = %(here)s/schema\n",
        "db/schema/versions/b2.py": "",
        "db/schema/env.py": "",
        "plugins/extra.py": "",
        "lib/helper.py": "",
    }
    root = make_repo(files)
    assert smells.entry_points(root, sorted(files), ["plugins/*.py"]) == frozenset(
        [
            "app/migrations/0001_init.py",
            "alembic/versions/a1.py",
            "db/schema/versions/b2.py",
            "plugins/extra.py",
        ]
    )


def test_facades_are_init_files_holding_only_imports(make_repo):
    files = {
        "a/__init__.py": '"""Pkg."""\nfrom .x import X\n__all__ = ["X"]\n',
        "b/__init__.py": "from .x import X\n\ndef helper():\n    pass\n",
        "c/__init__.py": "",
        "d/mod.py": "import os\n",
    }
    root = make_repo(files)
    assert smells.facades(root, sorted(files)) == frozenset(["a/__init__.py", "c/__init__.py"])
