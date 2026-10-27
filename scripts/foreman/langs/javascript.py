import posixpath
import re

from foreman.files import LANGUAGES
from foreman.langs import RepoIndex

EXTENSIONS = [ext for ext, lang in LANGUAGES.items() if lang == "javascript"]
STATIC = re.compile(r"\b(?:import|export)\s+(type\s+)?(?:[^'\";]*?\s+from\s*)?['\"]([^'\"]+)['\"]")
DYNAMIC = re.compile(r"\b(?:import|require)\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")


def _resolve(path: str, spec: str, index: RepoIndex) -> str | None:
    base = posixpath.normpath(posixpath.join(posixpath.dirname(path), spec))
    candidates = [base]
    candidates += [base + ext for ext in EXTENSIONS]
    candidates += [f"{base}/index{ext}" for ext in EXTENSIONS]
    return next((c for c in candidates if c in index.files), None)


def imports(path: str, text: str, index: RepoIndex) -> list[tuple[str, bool]]:
    specs = [(m.group(2), bool(m.group(1))) for m in STATIC.finditer(text)]
    specs += [(m.group(1), False) for m in DYNAMIC.finditer(text)]
    found = []
    for spec, type_only in specs:
        target = spec.startswith(".") and _resolve(path, spec, index)
        if target:
            found.append((target, type_only))
    return found
