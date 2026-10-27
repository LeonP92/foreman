import tomllib
from pathlib import Path

DEFAULTS = {"repo": {"base": "main", "ignore": []}, "graph": {}}


def load_or_default(path: Path) -> dict:
    data = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return {**data, **{key: {**value, **data.get(key, {})} for key, value in DEFAULTS.items()}}
