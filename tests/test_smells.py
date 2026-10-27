import json

from foreman import smells
from foreman.metrics import percentiles


def _detect(
    nodes=(),
    edges=(),
    type_edges=(),
    cycles=(),
    churn=None,
    pairs=(),
    files=(),
    functions=(),
    blocks=(),
    layers=(),
    entry_points=(),
    facades=(),
    mentioned=(),
):
    ids = sorted(
        {*nodes, *(n for e in [*edges, *type_edges] for n in e), *(n for c in cycles for n in c)}
    )
    graph = {
        "nodes": [{"id": n, "lang": "python"} for n in ids],
        "edges": [{"from": a, "to": b, "type_only": False} for a, b in edges]
        + [{"from": a, "to": b, "type_only": True} for a, b in type_edges],
        "cycles": [list(c) for c in cycles],
    }
    history = {"recent_churn": churn or {}, "pairs": list(pairs)}
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
        frozenset(mentioned),
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


IMPORTERS = [(f"m{i}.py", "h.py") for i in range(3)]


def test_hub_at_floor_and_just_under():
    imports = [("h.py", f"n{i}.py") for i in range(5)]
    found = _kinds(_detect(edges=imports + IMPORTERS), "hub")
    assert [s["nodes"] for s in found] == [["h.py"]]
    assert found[0]["evidence"] == (
        "imports 5 modules (threshold 5); imported by 3 (floor 3); 8 neighbours (threshold 8)"
    )
    assert _kinds(_detect(edges=imports[:4] + IMPORTERS), "hub") == []


def test_hub_needs_fan_in_so_a_composition_root_is_not_one():
    imports = [("h.py", f"n{i}.py") for i in range(10)]
    assert _kinds(_detect(edges=imports + IMPORTERS[:2]), "hub") == []


def test_hub_counts_only_runtime_edges():
    imports = [("h.py", f"n{i}.py") for i in range(8)]
    assert _kinds(_detect(edges=imports[:2] + IMPORTERS, type_edges=imports[2:]), "hub") == []
    assert _kinds(_detect(edges=imports, type_edges=IMPORTERS), "hub") == []


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
    # no commits in the window: no recent churn, so no hotspots
    assert _kinds(_detect([p for p, _ in files], churn={}, files=files), "hotspot") == []


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


def _block_nodes(blocks):
    return sorted({loc["path"] for b in blocks for loc in b["locations"]})


def test_duplicate_severity_and_order():
    blocks = [
        _block(19, "a.py", "b.py"),
        _block(12, "a.py", "b.py", "c.py"),
        _block(19, "d.py", "e.py"),
        _block(20, "f.py", "g.py"),
    ]
    found = _kinds(_detect(_block_nodes(blocks), blocks=blocks), "duplicate")
    assert [(s["severity"], s["nodes"]) for s in found] == [
        ("medium", ["f.py", "g.py"]),
        ("medium", ["a.py", "b.py", "c.py"]),
        ("low", ["a.py", "b.py"]),
        ("low", ["d.py", "e.py"]),
    ]


def test_duplicate_blocks_between_the_same_files_are_one_smell():
    blocks = [_block(12, "a.py", "b.py"), _block(12, "b.py", "a.py"), _block(12, "a.py", "c.py")]
    found = _kinds(_detect(_block_nodes(blocks), blocks=blocks), "duplicate")
    assert [(s["nodes"], s["severity"]) for s in found] == [
        (["a.py", "b.py"], "medium"),
        (["a.py", "c.py"], "low"),
    ]
    assert found[0]["evidence"].startswith("24 lines in 2 block(s)")


def test_test_files_are_not_duplicates_oversize_or_hotspots():
    blocks = [_block(12, "a.py", "tests/test_a.py"), _block(12, "b.py", "c.py")]
    found = _kinds(_detect(_block_nodes(blocks), blocks=blocks), "duplicate")
    assert [s["nodes"] for s in found] == [["b.py", "c.py"]]
    files = [(f"f{i}.py", 100) for i in range(60)]
    big = [("big.py", 400), ("tests/test_big.py", 400), ("web/cart.test.ts", 400)]
    churn = {p: 9 for p, _ in big}
    found = _detect(files=[*files, *big], churn=churn)
    assert {(s["kind"], s["nodes"][0]) for s in found} == {
        ("oversize", "big.py"),
        ("hotspot", "big.py"),
    }


def test_each_kind_is_capped_except_cycles_and_layering():
    blocks = [_block(12 + i, f"a{i}.py", f"b{i}.py") for i in range(25)]
    cycles = [[f"c{i}.py", f"d{i}.py"] for i in range(25)]
    found = _detect(_block_nodes(blocks), blocks=blocks, cycles=cycles)
    shown, dropped = smells.cap(found)
    assert len(_kinds(shown, "duplicate")) == smells.MAX_PER_KIND
    assert _kinds(shown, "duplicate")[0]["evidence"].startswith("36 lines")
    assert len(_kinds(shown, "cycle")) == 25
    assert dropped["duplicate"] == {"low": 5} and "cycle" not in dropped


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
    assert (
        _kinds(
            _detect(
                nodes,
                edges=[("main.py", "used.py")],
                entry_points=["tool.py"],
                mentioned=["lonely.py"],
            ),
            "deadcode",
        )
        == []
    )


def test_files_named_in_other_files_are_mentioned(make_repo):
    files = {
        "templates/page.html": '<script src="/static/js/widget.js"></script>\n',
        "static/js/widget.js": "",
        "config/jobs.yml": "job: tasks.nightly.run\n",
        "tasks/nightly.py": "",
        "README.md": "Run `helper` to see the help.\n",
        "bin/helper.rb": "",
        "lonely.py": "# lonely.py talks only about itself\n",
        "logo.png": b"\x89PNG\0lonely.py",
        # a stem two source files share names neither
        "docs/notes.md": "Shared helpers live in utils.\n",
        "web/utils.py": "",
        "api/utils.py": "",
    }
    root = make_repo(files)
    assert smells.mentioned(root, sorted(files)) == frozenset(
        ["static/js/widget.js", "tasks/nightly.py", "bin/helper.rb"]
    )


def test_hub_needs_fan_out_so_a_definitions_module_is_not_one():
    importers = [(f"m{i}.py", "defs.py") for i in range(20)]
    assert _kinds(_detect(edges=importers), "hub") == []
    found = _kinds(
        _detect(
            edges=[*importers, *IMPORTERS, ("h.py", "defs.py")]
            + [("h.py", f"n{i}.py") for i in range(7)]
        ),
        "hub",
    )
    assert [s["nodes"] for s in found] == [["h.py"]]


def test_hub_neighbours_skip_tests():
    edges = [("h.py", f"n{i}.py") for i in range(5)] + [
        (f"tests/test_{i}.py", "h.py") for i in range(5)
    ]
    assert _kinds(_detect(edges=edges), "hub") == []
    edges = [("h.py", f"n{i}.py") for i in range(5)] + [(f"m{i}.py", "h.py") for i in range(3)]
    assert [s["nodes"] for s in _kinds(_detect(edges=edges), "hub")] == [["h.py"]]


def test_non_source_files_are_never_smells():
    found = _detect(
        nodes=["infra/main.tf", "infra/prod.tfvars", "lonely.py", "a.py"],
        pairs=[_pair(9, 1.0, "infra/main.tf", "a.py"), _pair(9, 1.0, "lonely.py", "a.py")],
        cycles=[["infra/net.tf", "infra/main.tf"]],
    )
    assert {s["kind"]: s["nodes"] for s in found if "tf" in str(s["nodes"])} == {}
    assert {(s["kind"], tuple(s["nodes"])) for s in found} >= {
        ("deadcode", ("lonely.py",)),
        ("cochange", ("a.py", "lonely.py")),
    }


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


def test_no_pair_with_a_test_is_cochange():
    pairs = [
        _pair(9, 1.0, "tests/test_a.py", "tests/test_b.py"),
        _pair(9, 1.0, "shop/cart.py", "tests/unit/shop/test_cart.py"),
        _pair(9, 1.0, "web/src/cart.ts", "web/__tests__/cart.ts"),
        _pair(9, 1.0, "web/src/cart.ts", "web/src/cart.test.ts"),
        _pair(9, 1.0, "src/pricing.py", "tests/test_checkout.py"),
    ]
    nodes = [p[k] for p in pairs for k in ("a", "b")]
    assert _kinds(_detect(nodes, pairs=pairs), "cochange") == []


def test_tests_in_other_languages_are_not_cochange_with_their_subject():
    pairs = [
        _pair(9, 1.0, "app/models/user.rb", "spec/models/user_spec.rb"),
        _pair(9, 1.0, "src/main/java/shop/Cart.java", "src/test/java/shop/CartTest.java"),
        _pair(9, 1.0, "src/main/kotlin/Order.kt", "src/test/kotlin/OrderSpec.kt"),
        _pair(9, 1.0, "Sources/Bill.swift", "Tests/BillTests.swift"),
        _pair(9, 1.0, "lib/tax.rb", "lib/spec_tax.rb"),
    ]
    nodes = [p[k] for p in pairs for k in ("a", "b")]
    assert _kinds(_detect(nodes, pairs=pairs), "cochange") == []
    # a source file whose name merely ends in "test" is still a subject that can be coupled
    kept = [_pair(9, 1.0, "src/latest.py", "src/feed.py")]
    found = _kinds(_detect(["src/latest.py", "src/feed.py"], pairs=kept), "cochange")
    assert [s["nodes"] for s in found] == [["src/feed.py", "src/latest.py"]]


def test_hubs_skip_tests_conftest_and_facades_and_cap_entry_points():
    hubs = ["conftest.py", "tests/test_big.py", "pkg/__init__.py", "main.py", "mig/x.py", "h.py"]
    edges = [(h, f"n{i}.py") for h in hubs for i in range(8)]
    edges += [(f"m{i}.py", h) for h in hubs for i in range(3)]
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


def _smell(kind, severity, *nodes):
    return {"kind": kind, "severity": severity, "nodes": list(nodes), "title": f"{kind} {nodes}"}


def test_triage_takes_every_high_then_round_robins_kinds_within_the_budget():
    shown = [
        _smell("cycle", "high", "a.py", "b.py"),
        *[_smell("duplicate", "medium", f"d{i}.py", f"e{i}.py") for i in range(40)],
        *[_smell("cochange", "low", f"c{i}.py", f"x{i}.py") for i in range(40)],
        _smell("hotspot", "medium", "big.py"),
        _smell("oversize", "low", "big.py"),
    ]
    counts = {
        "cycle": {"high": 1},
        "duplicate": {"medium": 45},
        "cochange": {"low": 40},
        "hotspot": {"medium": 1},
        "oversize": {"low": 1},
    }
    items, left = smells.triage_order(shown, counts)
    assert len(items) == smells.TRIAGE_BUDGET
    assert [(i["kind"], i["nodes"][0]) for i in items[:6]] == [
        ("cycle", "a.py"),
        ("duplicate", "d0.py"),
        ("hotspot", "big.py"),
        ("cochange", "c0.py"),
        ("duplicate", "d1.py"),
        ("cochange", "c1.py"),
    ]
    # one item per file carries all its smells
    assert [s["kind"] for s in items[2]["smells"]] == ["hotspot", "oversize"]
    assert left == {"cochange": 11, "duplicate": 16}


def test_triage_never_caps_highs():
    shown = [_smell("layering", "high", f"a{i}.py", "b.py") for i in range(70)]
    shown.append(_smell("deadcode", "low", "z.py"))
    items, left = smells.triage_order(shown, {"layering": {"high": 70}, "deadcode": {"low": 1}})
    assert len(items) == 70 and {i["kind"] for i in items} == {"layering"}
    assert left == {"deadcode": 1}


def test_class_test_suffixes_need_a_test_folder_or_their_subject():
    spec, foo, foo_test = "src/main/kotlin/PricingSpec.kt", "src/Foo.java", "src/FooTest.java"
    dead = _kinds(_detect([spec, foo, foo_test]), "deadcode")
    # no Pricing.kt and no test folder: a class named so, still eligible for smells
    assert sorted(s["nodes"][0] for s in dead) == [foo, spec]
    pairs = [_pair(9, 1.0, foo, foo_test)]
    assert _kinds(_detect([foo, foo_test], pairs=pairs), "cochange") == []


def test_test_folders_match_in_any_case():
    for path in ["Tests/Helpers.swift", "src/Test/Util.java", "web/__TESTS__/x.js"]:
        assert smells._is_test(path, set()), path
    assert not smells._is_test("src/Testing/Util.java", set())
