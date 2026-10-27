import json

from foreman import cli
from foreman.graph import build, cycles


def edge_set(graph):
    return {(e["from"], e["to"], e["type_only"]) for e in graph["edges"]}


def test_python_absolute_relative_and_submodule_resolution(make_repo):
    root = make_repo(
        {
            "shop/__init__.py": "",
            "shop/cart.py": "from . import pricing\nfrom shop.models import Item\n",
            "shop/pricing.py": "",
            "shop/models/__init__.py": "",
            "shop/models/Item.py": "",
        }
    )
    edges = {(e["from"], e["to"]) for e in build(root)["edges"]}
    assert {("shop/cart.py", "shop/pricing.py"), ("shop/cart.py", "shop/models/Item.py")} <= edges


def test_python_src_layout_and_parent_relative(make_repo):
    root = make_repo(
        {
            "src/shop/__init__.py": "",
            "src/shop/tax.py": "",
            "src/shop/sub/calc.py": "import shop.tax\nfrom ..tax import rate\n",
            "src/shop/sub/__init__.py": "",
        }
    )
    assert ("src/shop/sub/calc.py", "src/shop/tax.py", False) in edge_set(build(root))


def test_type_checking_import_is_type_only_and_ignored_by_cycles(make_repo):
    root = make_repo(
        {
            "a.py": "import b\n",
            "b.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import a\n",
        }
    )
    graph = build(root)
    assert edge_set(graph) == {("a.py", "b.py", False), ("b.py", "a.py", True)}
    assert graph["cycles"] == []


def test_js_relative_index_and_type_imports(make_repo):
    root = make_repo(
        {
            "src/a.ts": (
                "import type { T } from './b'\n"
                "import { run } from './lib'\n"
                "export * from '../c.js'\n"
                "import React from 'react'\n"
                "const m = require('./b')\n"
            ),
            "src/b.ts": "",
            "src/lib/index.ts": "",
            "c.js": "",
        }
    )
    assert edge_set(build(root)) == {
        ("src/a.ts", "src/b.ts", False),
        ("src/a.ts", "src/lib/index.ts", False),
        ("src/a.ts", "c.js", False),
    }


def test_js_type_only_import(make_repo):
    root = make_repo({"a.ts": "import type { T } from './b'\n", "b.ts": ""})
    assert edge_set(build(root)) == {("a.ts", "b.ts", True)}


def test_go_packages_from_go_mod(make_repo):
    root = make_repo(
        {
            "go.mod": "module example.com/shop\n\ngo 1.22\n",
            "cmd/main.go": (
                'package main\n\nimport (\n\t"fmt"\n\tst "example.com/shop/internal/store"\n)\n'
            ),
            "internal/store/store.go": 'package store\n\nimport "fmt"\n',
        }
    )
    graph = build(root)
    assert edge_set(graph) == {("cmd", "internal/store", False)}
    assert {"id": "cmd", "lang": "go"} in graph["nodes"]


def test_cycles_found_and_sorted(make_repo):
    root = make_repo(
        {
            "b.py": "import a\n",
            "a.py": "import b\n",
            "e.py": "import c\n",
            "d.py": "import e\n",
            "c.py": "import d\n",
        }
    )
    assert build(root)["cycles"] == [["a.py", "b.py"], ["c.py", "d.py", "e.py"]]


def test_cycles_on_5000_node_chain():
    edges = [{"from": str(i), "to": str(i + 1), "type_only": False} for i in range(5000)]
    edges.append({"from": "5000", "to": "0", "type_only": False})
    found = cycles(edges)
    assert len(found) == 1 and len(found[0]) == 5001


def test_syntax_error_and_latin1_files_are_skipped_not_fatal(make_repo):
    root = make_repo(
        {"bad.py": "def (:\n", "old.py": "x = '\xe9'\n".encode("latin-1"), "ok.py": ""}
    )
    graph = build(root)
    assert [s["path"] for s in graph["skipped"]] == ["bad.py", "old.py"]
    assert "ok.py" in {n["id"] for n in graph["nodes"]}


def test_unknown_extensions_counted_in_unsupported(make_repo):
    root = make_repo({"a.rb": "", "lib/b.rb": "", "README.md": "", "data.json": "{}"})
    assert build(root)["unsupported"] == {".rb": 2}


def test_skipped_extensions_are_not_unsupported(make_repo):
    root = make_repo({"a.rb": "", "run.sh": "", "lib/go.sh": ""})
    assert build(root, rules={"skip": [".sh"]})["unsupported"] == {".rb": 1}


def test_python_inferred_source_roots(make_repo):
    root = make_repo(
        {
            "scripts/run.py": "from foreman import cli\n",
            "scripts/foreman/__init__.py": "",
            "scripts/foreman/cli.py": "from foreman.files import read_text\n",
            "scripts/foreman/files.py": "",
            "packages/a/src/a/__init__.py": "",
            "packages/a/src/a/x.py": "import a.y\n",
            "packages/a/src/a/y.py": "",
        }
    )
    assert {
        ("scripts/run.py", "scripts/foreman/cli.py", False),
        ("scripts/foreman/cli.py", "scripts/foreman/files.py", False),
        ("packages/a/src/a/x.py", "packages/a/src/a/y.py", False),
    } <= edge_set(build(root))


def test_python_prefers_the_importers_own_source_root(make_repo):
    files = {f"services/{s}/app/{m}": "" for s in "ab" for m in ("__init__.py", "db.py")}
    files["services/a/app/main.py"] = "from app import db\n"
    files["services/b/app/main.py"] = "from app import db\n"
    assert {
        ("services/a/app/main.py", "services/a/app/db.py", False),
        ("services/b/app/main.py", "services/b/app/db.py", False),
    } <= edge_set(build(make_repo(files)))


def test_js_path_aliases_from_tsconfig_with_comments(make_repo):
    tsconfig = """{
  "$schema": "https://json.schemastore.org/tsconfig", // comments are allowed
  /* block comment */
  "compilerOptions": {"baseUrl": "web", "paths": {"@/*": ["src/*"], "settings": ["src/conf.ts"]}}
}"""
    root = make_repo(
        {
            "tsconfig.json": tsconfig,
            "web/src/app.ts": "import a from '@/ui/button'\nimport s from 'settings'\nimport r from 'react'\n",
            "web/src/ui/button.tsx": "",
            "web/src/conf.ts": "",
        }
    )
    assert edge_set(build(root)) == {
        ("web/src/app.ts", "web/src/ui/button.tsx", False),
        ("web/src/app.ts", "web/src/conf.ts", False),
    }


def test_js_path_aliases_from_jsconfig(make_repo):
    root = make_repo(
        {
            "jsconfig.json": '{"compilerOptions": {"paths": {"~lib/*": ["./lib/*"]}}}',
            "main.js": "const x = require('~lib/util')\n",
            "lib/util/index.js": "",
        }
    )
    assert edge_set(build(root)) == {("main.js", "lib/util/index.js", False)}


def test_js_specifier_maps_to_ts_source(make_repo):
    root = make_repo({"a.ts": "import x from './c.js'\n", "c.ts": ""})
    assert edge_set(build(root)) == {("a.ts", "c.ts", False)}


def test_files_filter_keeps_edges_touching_given_paths(make_repo):
    root = make_repo({"a.py": "import b\n", "b.py": "", "c.py": "import d\n", "d.py": ""})
    graph = build(root, paths=["b.py"])
    assert edge_set(graph) == {("a.py", "b.py", False)}
    assert {n["id"] for n in graph["nodes"]} == {"a.py", "b.py"}


def test_cli_graph_applies_config_ignore(make_repo, capsys):
    root = make_repo(
        {
            "a.py": "import b\n",
            "b.py": "",
            "gen/c.py": "",
            ".foreman/config.toml": '[repo]\nignore = ["gen/**"]\n',
        }
    )
    assert cli.main(["graph", "--root", str(root)]) == 0
    graph = json.loads(capsys.readouterr().out)
    assert [n["id"] for n in graph["nodes"]] == ["a.py", "b.py"]


def test_cli_files_scope_is_normalised(make_repo, capsys):
    root = make_repo({"a.py": "import sub.b\n", "sub/__init__.py": "", "sub/b.py": ""})
    for given in ("./sub/b.py", "sub\\b.py"):
        assert cli.main(["graph", "--root", str(root), "--files", given]) == 0
        edges = json.loads(capsys.readouterr().out)["edges"]
        assert edges == [{"from": "a.py", "to": "sub/b.py", "type_only": False}]


def test_files_not_in_the_listing_are_reported_missing(make_repo, capsys):
    root = make_repo({"a.py": "import b\n", "b.py": ""})
    assert cli.main(["graph", "--root", str(root), "--files", "b.py", "gone.py", "a.py c.py"]) == 0
    graph = json.loads(capsys.readouterr().out)
    assert graph["missing"] == ["a.py c.py", "gone.py"]
    assert [n["id"] for n in graph["nodes"]] == ["a.py", "b.py"]
    assert build(root)["missing"] == []


def test_python_import_through_a_reexporting_package_reaches_the_submodule(make_repo):
    root = make_repo(
        {
            "shop/__init__.py": "from .pricing import Price as Cost\nfrom shop.tax import rate\n",
            # a second-level re-export is not followed: no edge from app.py to shop/money.py
            "shop/pricing.py": "from shop.money import Price\n",
            "shop/money.py": "",
            "shop/tax.py": "",
            "app.py": "from shop import Cost, rate\n",
        }
    )
    edges = {(e["from"], e["to"]) for e in build(root)["edges"] if e["from"] == "app.py"}
    assert edges == {
        ("app.py", "shop/__init__.py"),
        ("app.py", "shop/pricing.py"),
        ("app.py", "shop/tax.py"),
    }
