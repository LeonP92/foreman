import json

import pytest
from foreman import config
from foreman.cli import main

VALID = """
[repo]
base = "develop"
[server]
start = "run --port {port}"
[database]
kind = "command"
create = "mkdb {dir}"
env_override = "DB_URL"
url_template = "db://{dir}"
[[rules.layers]]
from = "core/**"
to = "apps/**"
[graph.ruby]
extensions = [".rb"]
pattern = "require '(.*)'"
resolve = ["{1}.rb"]
"""


def check_toml(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return config.check(config.load_or_default(path))


def test_valid_config_has_no_problems(tmp_path):
    assert check_toml(tmp_path, VALID) == []


def test_missing_file_gives_defaults(tmp_path):
    cfg = config.load_or_default(tmp_path / "none.toml")
    assert cfg == config.DEFAULTS
    assert config.check(cfg) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[nope]\na = 1", "unknown table [nope]"),
        ("[repo]\nbse = 1", "unknown key repo.bse"),
        ('[server]\nstart = "run"', "server.start must contain {port}"),
        ('[database]\nkind = "x"', "database.kind must be one of"),
        ('[database]\nkind = "file"', "database.path is required"),
        ('[database]\nkind = "command"\ncreate = "c"', "database.env_override is required"),
        ("[[rules.layers]]\nfrom = 'a/**'", "rules.layers entry needs both"),
        ('[graph.python]\nextensions = [".py"]', "[graph.python]: missing key"),
    ],
)
def test_problems(tmp_path, text, expected):
    assert any(expected in p for p in check_toml(tmp_path, text))


def test_command_requires_all_three(tmp_path):
    problems = check_toml(tmp_path, '[database]\nkind = "command"')
    assert len(problems) == 3


def test_config_check_cli(tmp_path, capsys):
    bad = tmp_path / "c.toml"
    bad.write_text('[database]\nkind = "file"', encoding="utf-8")
    assert main(["config-check", "--path", str(bad)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert main(["config-check", "--path", str(tmp_path / "missing.toml")]) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "problems": []}


@pytest.mark.parametrize(
    "command", [["map", "--out", "out"], ["graph"], ["graph-rule-check", "--name", "x"]]
)
@pytest.mark.parametrize(
    ("text", "message"),
    [("[[rules.layers]]\nfrom = 'a'", "invalid config: 1 problems"), ("[repo", "foreman:")],
)
def test_commands_reject_bad_config(tmp_path, capsys, command, text, message):
    (tmp_path / "c.toml").write_text(text, encoding="utf-8")
    argv = [command[0], "--root", str(tmp_path), "--config", "c.toml", *command[1:]]
    assert main(argv) == 1
    err = capsys.readouterr().err
    assert message in err
    assert err.count("\n") == 1
