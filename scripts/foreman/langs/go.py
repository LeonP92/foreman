import re

from foreman.langs import RepoIndex

BLOCK = re.compile(r"^import\s*\(([^)]*)\)", re.MULTILINE)
SINGLE = re.compile(r"^import\s+(?:[\w.]+\s+)?\"([^\"]+)\"", re.MULTILINE)
QUOTED = re.compile(r"\"([^\"]+)\"")


def imports(path: str, text: str, index: RepoIndex) -> list[tuple[str, bool]]:
    if index.go_module is None:
        return []
    # shortcut: regex scan also matches imports in comments/strings; switch to a tokenizer if this causes false edges
    specs = [s for block in BLOCK.findall(text) for s in QUOTED.findall(block)]
    specs += SINGLE.findall(text)
    found = []
    for spec in specs:
        if spec == index.go_module:
            package = "."
        elif spec.startswith(index.go_module + "/"):
            package = spec[len(index.go_module) + 1 :]
        else:
            continue
        if package in index.go_packages:
            found.append((package, False))
    return found
