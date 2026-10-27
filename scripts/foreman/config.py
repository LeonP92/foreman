import re
import tomllib
from pathlib import Path

from foreman.langs import rule

DEFAULTS = {
    "repo": {"base": "main", "ignore": [], "copy": []},
    "commands": {
        "install": "",
        "build": "",
        "lint": "",
        "typecheck": "",
        "test": "",
        "test_targeted": "",
        "e2e": "",
    },
    "env": {},
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
ENV_PLACEHOLDERS = ("port", "url", "dir", "name")
# Common names for where an app finds its database; verify removes them before any command runs.
DB_LOCATION_VARS = ("DATABASE_URL", "DATABASE_PATH", "DB_URL", "DB_PATH")
# {placeholder} filled in per server, or ${NAME} read from the agent's environment at run time
_ENV_REFERENCE = re.compile(r"(\$?)\{([^{}]*)\}")


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
        elif table == "env":
            found = _type_problem("[env]", values, {})
            problems += [found] if found else _env_problems("env", values, data)
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
                    if found:
                        problems.append(found)
                    elif (table, key) == ("server", "env"):
                        problems += _env_problems("server.env", value, data)
    problems += _semantic_problems(data)
    return problems


def _env_problems(prefix: str, env: dict, data: dict) -> list[str]:
    problems = []
    db_vars = {*DB_LOCATION_VARS, _get(data, "database", "env_override")}
    for key, value in env.items():
        for dollar, name in _ENV_REFERENCE.findall(value):
            if dollar and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                problems.append(f"{prefix}.{key}: ${{{name}}} is not an environment variable name")
            elif dollar and name in db_vars:
                problems.append(
                    f"{prefix}.{key}: ${{{name}}} names a database location; commands must use"
                    " their own copy, so build the value from {dir} or {name} instead"
                )
            elif not dollar and name not in ENV_PLACEHOLDERS:
                problems.append(f"{prefix}.{key}: unknown placeholder {{{name}}}")
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
