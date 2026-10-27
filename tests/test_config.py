import json
import re
from pathlib import Path

import pytest
from foreman import config
from foreman.cli import main

VALID = """
[repo]
base = "develop"
copy = [".env"]
[commands]
build = "make assets"
[env]
APP_URL = "{url}"
SECRET_KEY = "${SHOP_SECRET_KEY}"
[server]
start = "run --port {port}"
env = { CACHE_DIR = "{dir}/cache", DB = "db-{name}-{port}" }
[database]
kind = "command"
create = "mkdb {name}"
drop = "rmdb {name}"
env_override = "DB_URL"
url_template = "db://{name}"
[[rules.layers]]
from = "core/**"
to = "apps/**"
except = ["apps/plugins/**"]
[verify]
ignore_console = ["^Event stream reconnecting"]
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
        ("[[rules.layers]]\nfrom = 'a/**'", "rules.layers entry needs"),
        ('[graph.python]\nextensions = [".py"]', "[graph.python]: missing key"),
        ("[verify]\nignore_console = ['(']", "verify.ignore_console: '(' does not compile"),
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
    [("[[rules.layers]]\nfrom = 'a'", "invalid config: 1 problem(s)"), ("[repo", "foreman:")],
)
def test_commands_reject_bad_config(tmp_path, capsys, command, text, message):
    (tmp_path / "c.toml").write_text(text, encoding="utf-8")
    argv = [command[0], "--root", str(tmp_path), "--config", "c.toml", *command[1:]]
    assert main(argv) == 1
    err = capsys.readouterr().err
    assert message in err
    assert err.count("\n") == 1


WRONG_TYPES = [
    ('repo = "x"', "[repo] must be a table"),
    ("graph = 1", "[graph] must be a table"),
    ("[graph]\nx = 1", "[graph.x]: must be a table"),
    ("[server]\nstart = 1", "server.start must be a string"),
    ("[server]\nready_path = 1", "server.ready_path must be a string"),
    ("[server]\nenv = 1", "server.env must be a table of strings"),
    ("[server.env]\nA = 1", "server.env must be a table of strings"),
    ("env = 1", "[env] must be a table of strings"),
    ("[env]\nA = 1", "[env] must be a table of strings"),
    ("[repo]\ncopy = 1", "repo.copy must be a list of strings"),
    ("[commands]\nbuild = 1", "commands.build must be a string"),
    ("[repo]\nbase = 1", "repo.base must be a string"),
    ("[repo]\nignore = 1", "repo.ignore must be a list of strings"),
    ("[repo]\nignore = [1]", "repo.ignore must be a list of strings"),
    ("[commands]\ntest = 1", "commands.test must be a string"),
    ("[login]\nsteps = 1", "login.steps must be a string"),
    ('[database]\nkind = ["a"]', "database.kind must be a string"),
    ("[database]\npath = 1", "database.path must be a string"),
    ("[database]\ndrop = 1", "database.drop must be a string"),
    ("[rules]\ndocs = 1", "rules.docs must be a list of strings"),
    ("[verify]\nignore_console = 'x'", "verify.ignore_console must be a list of strings"),
    ("[rules]\nlayers = 1", "rules.layers must be a list of tables"),
    ("[rules]\nlayers = [1]", "rules.layers entry needs"),
    ("[[rules.layers]]\nfrom = 1\nto = 'a'", "rules.layers entry needs"),
    ("[[rules.layers]]\nfrom = 'a'\nto = 'b'\nexcept = 'c'", "rules.layers except must be"),
    ("[[rules.layers]]\nfrom = 'a'\nto = 'b'\nexcept = [1]", "rules.layers except must be"),
    ("[[rules.layers]]\nfrom = 'a'\nto = 'b'\nunless = []", "rules.layers unknown key 'unless'"),
]


@pytest.mark.parametrize(("text", "expected"), WRONG_TYPES)
def test_wrong_types_are_problems(tmp_path, text, expected):
    assert any(expected in p for p in check_toml(tmp_path, text))


def test_unknown_rule_key_is_a_problem(tmp_path):
    text = '[graph.ruby]\nextensions = [".rb"]\npattern = "(x)"\nresolve = ["a"]\nextra = 1'
    assert check_toml(tmp_path, text) == ["[graph.ruby]: unknown key 'extra'"]


def test_doc_examples_are_valid(tmp_path):
    doc = Path(__file__).parent.parent / "docs" / "config.md"
    blocks = re.findall(r"```toml\n(.*?)```", doc.read_text(encoding="utf-8"), re.DOTALL)
    assert len(blocks) == 2
    assert [check_toml(tmp_path, block) for block in blocks] == [[], []]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('[env]\nA = "{host}"', "env.A: unknown placeholder {host}"),
        ('[server.env]\nA = "x{ports}"', "server.env.A: unknown placeholder {ports}"),
        ('[env]\nA = "${1X}"', "env.A: ${1X} is not an environment variable name"),
        ('[env]\nA = "${}"', "env.A: ${} is not an environment variable name"),
    ],
)
def test_env_placeholder_problems(tmp_path, text, expected):
    assert check_toml(tmp_path, text) == [expected]


@pytest.mark.parametrize(
    "text",
    [
        '[env]\nA = "${DATABASE_URL}"',
        (
            '[database]\nkind = "command"\ncreate = "c"\nenv_override = "SHOP_DB"\n'
            'url_template = "u"\n[server.env]\nA = "${SHOP_DB}"'
        ),
    ],
)
def test_env_may_not_read_a_database_location(tmp_path, text):
    problems = check_toml(tmp_path, text)
    assert len(problems) == 1
    assert "names a database location" in problems[0]
