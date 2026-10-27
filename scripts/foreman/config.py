import tomllib
from pathlib import Path

from foreman.langs import rule

DEFAULTS = {
    "repo": {"base": "main", "ignore": []},
    "commands": {
        "install": "",
        "lint": "",
        "typecheck": "",
        "test": "",
        "test_targeted": "",
        "e2e": "",
    },
    "server": {"start": "", "ready_path": "/", "env": {}},
    "login": {"steps": ""},
    "database": {
        "kind": "none",
        "path": "",
        "create": "",
        "migrate": "",
        "seed": "",
        "env_override": "",
        "url_template": "",
    },
    "rules": {"docs": [], "layers": []},
    "graph": {},
}
DB_KINDS = ("none", "file", "command")
DB_REQUIRED = {"file": ("path",), "command": ("create", "env_override", "url_template")}


def load_or_default(path: Path) -> dict:
    data = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return {**data, **{key: {**value, **data.get(key, {})} for key, value in DEFAULTS.items()}}


def check(data: dict) -> list[str]:
    problems = []
    for table, values in data.items():
        if table not in DEFAULTS:
            problems.append(f"unknown table [{table}]")
        elif table == "graph":
            for name, r in values.items():
                problems += [f"[graph.{name}]: {e}" for e in rule.validate(name, r)]
        else:
            problems += [f"unknown key {table}.{k}" for k in values if k not in DEFAULTS[table]]
    start = data.get("server", {}).get("start", "")
    if start and "{port}" not in start:
        problems.append("server.start must contain {port}")
    database = data.get("database", {})
    kind = database.get("kind", "none")
    if kind not in DB_KINDS:
        problems.append(f"database.kind must be one of {', '.join(DB_KINDS)}")
    problems += [
        f"database.{key} is required when kind is {kind!r}"
        for key in DB_REQUIRED.get(kind, ())
        if not database.get(key)
    ]
    for entry in data.get("rules", {}).get("layers", []):
        if not (isinstance(entry, dict) and entry.get("from") and entry.get("to")):
            problems.append(f"rules.layers entry needs both 'from' and 'to': {entry!r}")
    return problems
