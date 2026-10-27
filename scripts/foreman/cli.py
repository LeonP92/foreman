import argparse
import sys

COMMANDS: tuple[str, ...] = ()


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="foreman")
    parser.add_subparsers(dest="command")
    try:
        args = parser.parse_args(argv)
    except ValueError as exc:
        print(f"foreman: {exc}", file=sys.stderr)
        return 1
    if args.command is None:
        parser.print_usage()
        return 1
    return 0
