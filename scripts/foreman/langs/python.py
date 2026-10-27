import ast
import posixpath

from foreman.files import read_text
from foreman.langs import RepoIndex


def _type_checking_nodes(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test):
            ids.update(id(n) for stmt in node.body for n in ast.walk(stmt))
    return ids


def _module_file(base: str, index: RepoIndex) -> str | None:
    for candidate in (f"{base}.py", f"{base}/__init__.py"):
        if candidate in index.files:
            return candidate
    return None


def _bases(path: str, level: int, module: str | None, index: RepoIndex) -> list[str]:
    parts = module.split(".") if module else []
    if level == 0:
        # in a monorepo several roots can hold the same package: the importer's own root wins
        mine = [r for r in index.python_roots if not r or path.startswith(r + "/")]
        roots = sorted(mine, key=len, reverse=True) + [
            r for r in index.python_roots if r not in mine
        ]
        return [posixpath.join(root, *parts) for root in roots]
    package = posixpath.dirname(path)
    for _ in range(level - 1):
        package = posixpath.dirname(package)
    return [posixpath.join(package, *parts)]


def _first(bases: list[str], name: str | None, index: RepoIndex) -> str | None:
    for base in bases:
        # `from pkg import name` names a submodule when one exists, else something in pkg
        found = (name and _module_file(posixpath.join(base, name), index)) or _module_file(
            base, index
        )
        if found:
            return found
    return None


def _reexports(init: str, index: RepoIndex) -> dict[str, str]:
    """Name -> submodule file for each `from .sub import Name` at the top of a package `__init__.py`."""
    if init in index.python_reexports:
        return index.python_reexports[init]
    found = index.python_reexports[init] = {}
    try:
        tree = ast.parse(read_text(index.root / init) or "")
    except SyntaxError:
        return found
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            bases = _bases(init, node.level, node.module, index)
            for a in node.names:
                target = _first(bases, a.name, index)
                if target and target != init:
                    found[a.asname or a.name] = target
    return found


def _targets(path: str, node: ast.AST, index: RepoIndex) -> list[str]:
    if isinstance(node, ast.Import):
        found = [_first(_bases(path, 0, a.name, index), None, index) for a in node.names]
    elif isinstance(node, ast.ImportFrom):
        bases = _bases(path, node.level, node.module, index)
        found = []
        for a in node.names:
            target = _first(bases, a.name, index)
            found.append(target)
            # one level only: the package's own re-export, not what that submodule re-exports
            if target and target.endswith("__init__.py"):
                found.append(_reexports(target, index).get(a.name))
    else:
        return []
    return [f for f in found if f]


def imports(path: str, text: str, index: RepoIndex) -> list[tuple[str, bool]]:
    tree = ast.parse(text, filename=path)
    typed = _type_checking_nodes(tree)
    return [
        (target, id(node) in typed)
        for node in ast.walk(tree)
        for target in _targets(path, node, index)
    ]
