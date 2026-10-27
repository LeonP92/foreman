import argparse
import json
import posixpath
import sys
from pathlib import Path, PureWindowsPath

from foreman import browser, codemap, config, db, graph, render, smells
from foreman.langs import rule


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def _load(args, *, gate_graph=True) -> dict:
    cfg = config.load_or_default(args.root / args.config)
    problems = config.check(cfg if gate_graph else {**cfg, "graph": {}})
    if problems:
        raise ValueError(f"invalid config: {len(problems)} problem(s) - run config-check")
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
    cfg = _load(args, gate_graph=False)
    rules = cfg["graph"]
    if not isinstance(rules, dict):
        raise ValueError("[graph] must be a table")  # noqa: TRY004 - CLI maps bad input to ValueError
    if args.name not in rules:
        raise ValueError(f"no rule [graph.{args.name}] in {args.config}")
    problems = rule.validate(args.name, rules[args.name])
    if problems:
        lines = "".join(f"\n  {p}" for p in problems)
        raise ValueError(f"invalid rule {args.name}: {len(problems)} problem(s){lines}")
    result = rule.check(args.root, rules[args.name], cfg["repo"]["ignore"])
    return result, 0 if result["ok"] else 1


def _render(args) -> tuple[dict, int]:
    data = json.loads(args.data.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{args.data.as_posix()}: expected a JSON object")  # noqa: TRY004 - CLI maps bad input to ValueError
    return {"path": render.write(data, args.out).as_posix()}, 0


def _map(args) -> tuple[dict, int]:
    if args.dismiss:
        # re-render the last map from --out, so triage never re-runs the scan
        data = codemap.dismiss(
            json.loads((args.out / "map.json").read_text(encoding="utf-8")),
            json.loads(args.dismiss.read_text(encoding="utf-8")),
        )
    else:
        data = codemap.build(args.root, _load(args))
    if args.title:
        data["title"] = args.title
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "map.json").write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    html = render.write(data, args.out / "map.html")
    summary = {"groups": len(data["groups"]), "nodes": len(data["nodes"])}
    if not args.dismiss:
        summary["triage"], summary["not_triaged"] = smells.triage_order(
            data["smells"], data["counts"]
        )
    return {
        "html": html.as_posix(),
        **summary,
        "smells": data["smells"],
        "dropped": data["dropped"],
        "counts": data["counts"],
        "dismissed": data.get("dismissed", {}),
        "unsupported": data["unsupported"],
    }, 0


def _browser_run(args) -> tuple[dict, int]:
    ignore_console = _load(args)["verify"]["ignore_console"]
    return browser.run(args.spec, args.out, args.base, args.branch, ignore_console), 0


def _db_copy(args) -> tuple[dict, int]:
    return db.copy(args.src, args.dst), 0


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
_map_parser = _command("map", _map)
_map_parser.add_argument("--out", type=Path, required=True)
_map_parser.add_argument("--dismiss", type=Path)
_map_parser.add_argument("--title")
_config_parser = _SUBPARSERS.add_parser("config-check")
_config_parser.set_defaults(func=_config_check)
_config_parser.add_argument("--path", type=Path, default=Path(".foreman/config.toml"))
_render_parser = _SUBPARSERS.add_parser("render")
_render_parser.set_defaults(func=_render)
_render_parser.add_argument("data", type=Path)
_render_parser.add_argument("out", type=Path)
_browser_parser = _command("browser-run", _browser_run)
_browser_parser.add_argument("--spec", type=Path, required=True)
_browser_parser.add_argument("--out", type=Path, required=True)
_browser_parser.add_argument("--base", required=True)
_browser_parser.add_argument("--branch")
_db_parser = _SUBPARSERS.add_parser("db-copy")
_db_parser.set_defaults(func=_db_copy)
_db_parser.add_argument("src", type=Path)
_db_parser.add_argument("dst", type=Path)
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
