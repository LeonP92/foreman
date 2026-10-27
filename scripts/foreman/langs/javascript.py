import posixpath
import re

from foreman.files import LANGUAGES
from foreman.langs import RepoIndex

EXTENSIONS = [ext for ext, lang in LANGUAGES.items() if lang == "javascript"]
STATIC = re.compile(r"\b(?:import|export)\s+(type\s+)?(?:[^'\";]*?\s+from\s*)?['\"]([^'\"]+)['\"]")
# TS sources are imported by their emitted JS name (`./c.js` for c.ts)
JS_TO_TS = {".js": ".ts", ".mjs": ".mts", ".cjs": ".cts", ".jsx": ".tsx"}
DYNAMIC = re.compile(r"\b(?:import|require)\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")


def _resolve(path: str, spec: str, index: RepoIndex) -> str | None:
    base = posixpath.normpath(posixpath.join(posixpath.dirname(path), spec))
    candidates = [base]
    stem, ext = posixpath.splitext(base)
    if ext in JS_TO_TS:
        candidates.append(stem + JS_TO_TS[ext])
    candidates += [base + ext for ext in EXTENSIONS]
    candidates += [f"{base}/index{ext}" for ext in EXTENSIONS]
    return next((c for c in candidates if c in index.files), None)


def imports(path: str, text: str, index: RepoIndex) -> list[tuple[str, bool]]:
    # shortcut: regex scan also matches imports in comments/strings; switch to a tokenizer if this causes false edges
    specs = [(m.group(2), bool(m.group(1))) for m in STATIC.finditer(text)]
    specs += [(m.group(1), False) for m in DYNAMIC.finditer(text)]
    found = []
    for spec, type_only in specs:
        target = spec.startswith(".") and _resolve(path, spec, index)
        if target:
            found.append((target, type_only))
    return found
