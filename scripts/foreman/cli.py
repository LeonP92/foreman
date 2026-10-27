import argparse
import json
import posixpath
import sys
from pathlib import Path, PureWindowsPath

from foreman import config, graph
from foreman.langs import rule


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def _load(args) -> dict:
    return config.load_or_default(args.root / args.config)


def _graph(args) -> tuple[dict, int]:
    cfg = _load(args)
    rules = cfg["graph"]
    for name, r in rules.items():
        errors = rule.validate(name, r)
        if errors:
            raise ValueError(f"rule {name!r}: {'; '.join(errors)}")
    # PureWindowsPath accepts both separators, so `src\a.py` and `./a.py` match repo ids
    paths = args.files and [posixpath.normpath(PureWindowsPath(p).as_posix()) for p in args.files]
    result = graph.build(args.root, paths, cfg["repo"]["ignore"], rules)
    return dict(result), 0


def _graph_rule_check(args) -> tuple[dict, int]:
    rules = _load(args)["graph"]
    if args.name not in rules:
        raise ValueError(f"no rule [graph.{args.name}] in {args.config}")
    errors = rule.validate(args.name, rules[args.name])
    if errors:
        raise ValueError(f"rule {args.name!r}: {'; '.join(errors)}")
    result = rule.check(args.root, rules[args.name])
    return result, 0 if result["ok"] else 1


def _command(name, func):
    sub = _SUBPARSERS.add_parser(name)
    sub.set_defaults(func=func)
    sub.add_argument("--root", type=Path, default=Path())
    sub.add_argument("--config", type=Path, default=Path(".foreman/config.toml"))
    return sub


_PARSER = _Parser(prog="foreman")
_SUBPARSERS = _PARSER.add_subparsers(dest="command", required=True)
_command("graph", _graph).add_argument("--files", nargs="+")
_command("graph-rule-check", _graph_rule_check).add_argument("--name", required=True)
COMMANDS = frozenset(_SUBPARSERS.choices)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _PARSER.parse_args(argv)
        result, code = args.func(args)
    except ValueError as exc:
        print(f"foreman: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=1, sort_keys=True))
    return code
