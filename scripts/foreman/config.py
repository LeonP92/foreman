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
        "drop": "",
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
    # a non-table value is left as is for check() to report
    return {
        **data,
        **{
            key: {**default, **data[key]}
            if isinstance(data.get(key), dict)
            else data.get(key, default)
            for key, default in DEFAULTS.items()
        },
    }


def _type_problem(name: str, value, default) -> str | None:
    if isinstance(default, str):
        return None if isinstance(value, str) else f"{name} must be a string"
    if isinstance(default, list):
        ok = isinstance(value, list) and all(isinstance(v, str) for v in value)
        return None if ok else f"{name} must be a list of strings"
    ok = isinstance(value, dict) and all(isinstance(v, str) for v in value.values())
    return None if ok else f"{name} must be a table of strings"


def check(data: dict) -> list[str]:
    problems = []
    for table, values in data.items():
        if table not in DEFAULTS:
            problems.append(f"unknown table [{table}]")
        elif not isinstance(values, dict):
            problems.append(f"[{table}] must be a table")
        elif table == "graph":
            for name, r in values.items():
                problems += [f"[graph.{name}]: {e}" for e in rule.validate(name, r)]
        else:
            for key, value in values.items():
                if key not in DEFAULTS[table]:
                    problems.append(f"unknown key {table}.{key}")
                elif (table, key) != ("rules", "layers"):
                    found = _type_problem(f"{table}.{key}", value, DEFAULTS[table][key])
                    problems += [found] if found else []
    problems += _semantic_problems(data)
    return problems


def _semantic_problems(data: dict) -> list[str]:
    problems = []
    start = _get(data, "server", "start")
    if start and isinstance(start, str) and "{port}" not in start:
        problems.append("server.start must contain {port}")
    kind = _get(data, "database", "kind", "none")
    if not isinstance(kind, str):
        return problems
    if kind not in DB_KINDS:
        problems.append(f"database.kind must be one of {', '.join(DB_KINDS)}")
    problems += [
        f"database.{key} is required when kind is {kind!r}"
        for key in DB_REQUIRED.get(kind, ())
        if not _get(data, "database", key)
    ]
    layers = _get(data, "rules", "layers", [])
    if not isinstance(layers, list):
        return [*problems, "rules.layers must be a list of tables"]
    for entry in layers:
        pair = (entry.get("from"), entry.get("to")) if isinstance(entry, dict) else ()
        if not (len(pair) == 2 and all(isinstance(g, str) and g for g in pair)):
            problems.append(f"rules.layers entry needs string 'from' and 'to': {entry!r}")
    return problems


def _get(data: dict, table: str, key: str, default=""):
    values = data.get(table)
    return values.get(key, default) if isinstance(values, dict) else default
