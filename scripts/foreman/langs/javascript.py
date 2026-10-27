import posixpath
import re

from foreman.files import LANGUAGES
from foreman.langs import RepoIndex

EXTENSIONS = [ext for ext, lang in LANGUAGES.items() if lang == "javascript"]
STATIC = re.compile(r"\b(?:import|export)\s+(type\s+)?(?:[^'\";]*?\s+from\s*)?['\"]([^'\"]+)['\"]")
# TS sources are imported by their emitted JS name (`./c.js` for c.ts)
JS_TO_TS = {".js": ".ts", ".mjs": ".mts", ".cjs": ".cts", ".jsx": ".tsx"}
DYNAMIC = re.compile(r"\b(?:import|require)\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")


def _find(base: str, index: RepoIndex) -> str | None:
    candidates = [base]
    stem, ext = posixpath.splitext(base)
    if ext in JS_TO_TS:
        candidates.append(stem + JS_TO_TS[ext])
    candidates += [base + ext for ext in EXTENSIONS]
    candidates += [f"{base}/index{ext}" for ext in EXTENSIONS]
    return next((c for c in candidates if c in index.files), None)


def _resolve(path: str, spec: str, index: RepoIndex) -> str | None:
    if spec.startswith("."):
        return _find(posixpath.normpath(posixpath.join(posixpath.dirname(path), spec)), index)
    for alias, targets in index.js_paths:
        prefix, star, suffix = alias.partition("*")
        if star:
            fits = spec.startswith(prefix) and spec.endswith(suffix)
            fits = fits and len(spec) >= len(prefix) + len(suffix)
            middle = spec[len(prefix) : len(spec) - len(suffix)]
        else:
            fits, middle = spec == alias, ""
        for target in targets if fits else ():
            found = _find(posixpath.normpath(target.replace("*", middle)), index)
            if found:
                return found
    return None


def imports(path: str, text: str, index: RepoIndex) -> list[tuple[str, bool]]:
    # shortcut: regex scan also matches imports in comments/strings; switch to a tokenizer if this causes false edges
    specs = [(m.group(2), bool(m.group(1))) for m in STATIC.finditer(text)]
    specs += [(m.group(1), False) for m in DYNAMIC.finditer(text)]
    found = []
    for spec, type_only in specs:
        target = _resolve(path, spec, index)
        if target:
            found.append((target, type_only))
    return found
