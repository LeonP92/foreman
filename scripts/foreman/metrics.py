import ast
import math
from collections.abc import Sequence
from pathlib import Path

from foreman.files import list_files, read_text
from foreman.graph import NON_SOURCE_EXTENSIONS


def source_texts(root: Path, ignore: Sequence[str] = ()) -> dict[str, str]:
    texts = {}
    for path in list_files(root, ignore):
        if Path(path).suffix in NON_SOURCE_EXTENSIONS:
            continue
        text = read_text(root / path)
        if text is not None:
            texts[path] = text
    return texts


def percentiles(values: Sequence[int]) -> dict[str, int]:
    ordered = sorted(values)

    def rank(p: float) -> int:
        return ordered[math.ceil(p * len(ordered)) - 1] if ordered else 0

    return {"median": rank(0.5), "p75": rank(0.75), "p90": rank(0.9), "p95": rank(0.95)}


def _functions(path: str, text: str) -> list[dict]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    found = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                name = prefix + child.name
                if not isinstance(child, ast.ClassDef):
                    assert child.end_lineno is not None
                    lines = child.end_lineno - child.lineno + 1
                    found.append(
                        {"path": path, "name": name, "start": child.lineno, "lines": lines}
                    )
                visit(child, name + ".")
            else:
                visit(child, prefix)

    visit(tree, "")
    return found


def measure(root: Path, ignore: Sequence[str] = ()) -> dict:
    files = []
    functions = []
    for path, text in source_texts(root, ignore).items():
        files.append({"path": path, "lines": sum(1 for ln in text.split("\n") if ln.strip())})
        if path.endswith(".py"):
            functions.extend(_functions(path, text))
    return {
        "files": files,
        "functions": functions,
        "stats": {
            "file_lines": percentiles([f["lines"] for f in files]),
            "function_lines": percentiles([f["lines"] for f in functions]),
        },
    }
