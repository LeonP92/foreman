import json

from foreman import cli
from foreman.graph import build
from foreman.langs import rule

RUBY = {
    "extensions": [".rb"],
    "pattern": r"^\s*require_relative\s+['\"](.+?)['\"]",
    "resolve": ["{dir}/{1}.rb"],
}
JAVA = {
    "extensions": [".java"],
    "pattern": r"^\s*import\s+([\w.]+);",
    "resolve": ["src/main/java/{1|path}.java"],
}


def test_ruby_rule_builds_edges(make_repo):
    root = make_repo({"lib/cart.rb": "require_relative 'pricing'\n", "lib/pricing.rb": ""})
    graph = build(root, rules={"ruby": RUBY})
    assert graph["edges"] == [{"from": "lib/cart.rb", "to": "lib/pricing.rb", "type_only": False}]
    assert {"id": "lib/cart.rb", "lang": "ruby"} in graph["nodes"]
    assert graph["unsupported"] == {}


def test_java_rule_maps_packages_and_skips_external(make_repo):
    root = make_repo(
        {
            "src/main/java/shop/Cart.java": "import shop.util.Money;\nimport java.util.List;\n",
            "src/main/java/shop/util/Money.java": "",
        }
    )
    edges = {(e["from"], e["to"]) for e in build(root, rules={"java": JAVA})["edges"]}
    assert edges == {("src/main/java/shop/Cart.java", "src/main/java/shop/util/Money.java")}


def test_check_reports_resolution_rate(make_repo):
    root = make_repo(
        {
            "a.rb": "require_relative 'b'\nrequire_relative 'lib/missing'\nrequire_relative 'set'\n",
            "b.rb": "",
        }
    )
    result = rule.check(root, RUBY)
    assert (result["files"], result["matches"], result["resolved"]) == (2, 3, 1)
    assert result["external"] == 1
    assert result["ok"] is True
    assert result["unresolved_examples"] == [{"import": "lib/missing", "path": "a.rb"}]


def test_check_counts_only_unknown_bare_names_as_external(make_repo):
    # `pricing` names a repo file the templates can't reach, so it is a miss, not external
    root = make_repo(
        {"a.rb": "require_relative 'pricing'\nrequire_relative 'json'\n", "lib/pricing.rb": ""}
    )
    result = rule.check(root, RUBY)
    assert (result["matches"], result["resolved"], result["external"]) == (2, 0, 1)
    assert result["unresolved_examples"] == [{"import": "pricing", "path": "a.rb"}]
    assert result["ok"] is False


def test_check_shows_import_lines_the_pattern_missed(make_repo):
    root = make_repo(
        {
            "a.rb": "require_relative 'b'\nrequire_relative File.join(__dir__, 'c')\n",
            "b.rb": "# require_relative_helper is not the keyword\n",
            "Cart.java": "import shop.Money;\nimport static shop.Util.round;\n",
        }
    )
    assert rule.check(root, RUBY)["unmatched_examples"] == [
        {"line": "require_relative File.join(__dir__, 'c')", "path": "a.rb"}
    ]
    assert rule.check(root, JAVA)["unmatched_examples"] == [
        {"line": "import static shop.Util.round;", "path": "Cart.java"}
    ]


def test_check_fails_when_nothing_matches(make_repo):
    root = make_repo({"a.rb": "require 'json'\n"})
    assert rule.check(root, RUBY)["ok"] is False


def test_rule_cannot_escape_repo(make_repo, tmp_path):
    root = make_repo({"a.rb": "require_relative '../outside'\n"})
    (root.parent / "outside.rb").write_text("", encoding="utf-8")
    assert build(root, rules={"ruby": RUBY})["edges"] == []


def test_validate_rejects_bad_regex_missing_group_and_builtin_name():
    assert rule.validate("ruby", RUBY) == []
    assert rule.validate("ruby", {**RUBY, "pattern": "("})
    assert rule.validate("ruby", {**RUBY, "pattern": "require"})
    assert rule.validate("python", RUBY)
    assert rule.validate("ruby", {"pattern": RUBY["pattern"]})
    assert rule.validate("ruby", {**RUBY, "pattern": 1})
    assert rule.validate("ruby", {**RUBY, "extensions": ".rb"})
    assert rule.validate("ruby", {**RUBY, "extensions": []})
    assert rule.validate("ruby", {**RUBY, "resolve": "x"})
    assert rule.validate("ruby", {**RUBY, "resolve": [1]})


def test_cli_rule_check_exit_codes(make_repo, capsys):
    root = make_repo(
        {
            "a.rb": "require_relative 'b'\n",
            "b.rb": "",
            ".foreman/config.toml": (
                "[graph.ruby]\nextensions = ['.rb']\n"
                "pattern = '''^require_relative\\s+'(.+?)''''\nresolve = ['{dir}/{1}.rb']\n"
                "[graph.broken]\nextensions = ['.rb']\npattern = '('\nresolve = []\n"
                "[graph.typed]\nextensions = ['.rb']\npattern = 1\nresolve = ['{1}.rb']\n"
            ),
        }
    )
    assert cli.main(["graph-rule-check", "--name", "ruby", "--root", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    for name in ("broken", "typed"):
        assert cli.main(["graph-rule-check", "--name", name, "--root", str(root)]) == 1
        err = capsys.readouterr().err
        assert f"invalid rule {name}: " in err
        assert err.splitlines()[1].startswith("  ")


def test_rule_check_and_graph_count_the_same_files(make_repo, capsys):
    root = make_repo(
        {
            "lib/a.rb": "require_relative 'b'\n",
            "lib/b.rb": "",
            "vendor/c.rb": "require_relative 'd'\n",
            ".foreman/config.toml": (
                "[repo]\nignore = ['vendor/**']\n"
                "[graph.ruby]\nextensions = ['.rb']\n"
                "pattern = '''^require_relative\\s+'(.+?)''''\nresolve = ['{dir}/{1}.rb']\n"
            ),
        }
    )
    cli.main(["graph-rule-check", "--name", "ruby", "--root", str(root)])
    checked = json.loads(capsys.readouterr().out)
    cli.main(["graph", "--root", str(root)])
    graphed = json.loads(capsys.readouterr().out)
    assert checked["files"] == sum(n["lang"] == "ruby" for n in graphed["nodes"]) == 2
    assert checked["matches"] == 1
