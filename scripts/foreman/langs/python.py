import ast
import posixpath

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


def _bases(path: str, level: int, module: str | None) -> list[str]:
    parts = module.split(".") if module else []
    if level == 0:
        return ["/".join(parts), posixpath.join("src", *parts)]
    package = posixpath.dirname(path)
    for _ in range(level - 1):
        package = posixpath.dirname(package)
    return [posixpath.join(package, *parts)]


def _targets(path: str, node: ast.AST, index: RepoIndex) -> list[str]:
    if isinstance(node, ast.Import):
        found = [
            _module_file(base, index)
            for alias in node.names
            for base in _bases(path, 0, alias.name)
        ]
        return [f for f in found if f]
    if not isinstance(node, ast.ImportFrom):
        return []
    found = []
    for base in _bases(path, node.level, node.module):
        # `from pkg import name` names a submodule when one exists, else something in pkg
        for alias in node.names:
            found.append(
                _module_file(posixpath.join(base, alias.name), index) or _module_file(base, index)
            )
    return [f for f in found if f]


def imports(path: str, text: str, index: RepoIndex) -> list[tuple[str, bool]]:
    tree = ast.parse(text, filename=path)
    typed = _type_checking_nodes(tree)
    return [
        (target, id(node) in typed)
        for node in ast.walk(tree)
        for target in _targets(path, node, index)
    ]
