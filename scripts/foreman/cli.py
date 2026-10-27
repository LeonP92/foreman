import argparse
import json
import posixpath
import sys
from pathlib import Path, PureWindowsPath

from foreman import codemap, config, graph, render
from foreman.langs import rule


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def _load(args) -> dict:
    cfg = config.load_or_default(args.root / args.config)
    problems = config.check(cfg)
    if problems:
        raise ValueError(f"invalid config: {len(problems)} problems — run config-check")
    return cfg


def _config_check(args) -> tuple[dict, int]:
    problems = config.check(config.load_or_default(args.path))
    return {"ok": not problems, "problems": problems}, 1 if problems else 0


def _graph(args) -> tuple[dict, int]:
    cfg = _load(args)
    # PureWindowsPath accepts both separators, so `src\a.py` and `./a.py` match repo ids
    paths = args.files and [posixpath.normpath(PureWindowsPath(p).as_posix()) for p in args.files]
    result = graph.build(args.root, paths, cfg["repo"]["ignore"], cfg["graph"])
    return dict(result), 0


def _graph_rule_check(args) -> tuple[dict, int]:
    rules = _load(args)["graph"]
    if args.name not in rules:
        raise ValueError(f"no rule [graph.{args.name}] in {args.config}")
    result = rule.check(args.root, rules[args.name])
    return result, 0 if result["ok"] else 1


def _render(args) -> tuple[dict, int]:
    data = json.loads(args.data.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{args.data.as_posix()}: expected a JSON object")  # noqa: TRY004 - CLI maps bad input to ValueError
    return {"path": render.write(data, args.out).as_posix()}, 0


def _map(args) -> tuple[dict, int]:
    data = codemap.build(args.root, _load(args))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "map.json").write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    html = render.write(data, args.out / "map.html")
    summary = {"groups": len(data["groups"]), "nodes": len(data["nodes"])}
    return {
        "html": html.as_posix(),
        **summary,
        "smells": data["smells"],
        "unsupported": data["unsupported"],
    }, 0


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
_command("map", _map).add_argument("--out", type=Path, required=True)
_config_parser = _SUBPARSERS.add_parser("config-check")
_config_parser.set_defaults(func=_config_check)
_config_parser.add_argument("--path", type=Path, default=Path(".foreman/config.toml"))
_render_parser = _SUBPARSERS.add_parser("render")
_render_parser.set_defaults(func=_render)
_render_parser.add_argument("data", type=Path)
_render_parser.add_argument("out", type=Path)
COMMANDS = frozenset(_SUBPARSERS.choices)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _PARSER.parse_args(argv)
        result, code = args.func(args)
    except (ValueError, OSError) as exc:
        print(f"foreman: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=1, sort_keys=True))
    return code
