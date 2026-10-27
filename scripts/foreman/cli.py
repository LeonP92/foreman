import argparse
import sys


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


_PARSER = _Parser(prog="foreman")
_SUBPARSERS = _PARSER.add_subparsers(dest="command", required=True)
COMMANDS = frozenset(_SUBPARSERS.choices)


def main(argv: list[str] | None = None) -> int:
    try:
        _PARSER.parse_args(argv)
    except ValueError as exc:
        print(f"foreman: {exc}", file=sys.stderr)
        return 1
    return 0
