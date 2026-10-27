"""Run Playwright specs against base and branch URLs from a private, pinned install."""

import base64
import json
import os
import re
import secrets
import shutil
import subprocess
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath

from foreman.render import TEMPLATES

PLAYWRIGHT_VERSION = "1.64.1"
MIN_NODE = 20
FIXTURES = "foreman-fixtures.mjs"
CONFIG = "playwright.config.mjs"
RUN_MAX_AGE = 7 * 24 * 3600
INSTALL_TIMEOUT = 600
# globalTimeout in playwright.config.mjs is 10 minutes; this leaves room for startup and teardown.
TEST_TIMEOUT = 660
_DIRECT_IMPORT = re.compile(
    r"""^\s*(?:import|export)\s[^;]*?\bfrom\s*['"]@playwright/test['"]"""
    r"""|import\(['"]@playwright/test['"]\)"""
    r"""|require\(['"]@playwright/test['"]\)""",
    re.MULTILINE,
)
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
ERROR_LINES = 5


def cache_dir() -> Path:
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(root) / "foreman" / "playwright"
    root = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(root) / "foreman" / "playwright"


def _tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise ValueError(f"{name} not found on PATH; install Node >= {MIN_NODE}")
    return path


def _run(args: list[str], timeout: int, **kwargs) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=timeout,
            **kwargs,
        )
    except subprocess.TimeoutExpired:
        raise OSError(f"{' '.join(args)} timed out after {timeout} s") from None


def _last_line(proc: subprocess.CompletedProcess) -> str:
    return ((proc.stderr or proc.stdout).strip().splitlines() or [f"exit {proc.returncode}"])[-1]


def _check(args: list[str], timeout: int = 30) -> str:
    proc = _run(args, timeout)
    if proc.returncode:
        raise OSError(f"{' '.join(args)} failed: {_last_line(proc)}")
    return proc.stdout


def _installed_version(pkg_json: Path) -> str | None:
    try:
        return json.loads(pkg_json.read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError, TypeError):
        return None  # missing or corrupt: reinstall


def ensure() -> Path:
    node = _tool("node")
    version = _check([node, "--version"]).strip()
    major = re.match(r"v?(\d+)\.", version)
    if not major:
        raise ValueError(f"cannot read the Node version from {version!r}")
    if int(major[1]) < MIN_NODE:
        raise ValueError(f"Node >= {MIN_NODE} required, found {version}")
    cache = cache_dir()
    package = cache / "node_modules" / "@playwright" / "test"
    if _installed_version(package / "package.json") != PLAYWRIGHT_VERSION:
        cache.mkdir(parents=True, exist_ok=True)
        # --prefix stops npm from walking up to an ancestor project. npm may be a .cmd shim run by
        # cmd.exe on Windows; that is safe here because every argument is fixed.
        _check(
            [
                _tool("npm"),
                "install",
                "--prefix",
                str(cache),
                "--no-audit",
                "--no-fund",
                f"@playwright/test@{PLAYWRIGHT_VERSION}",
            ],
            INSTALL_TIMEOUT,
        )
    cli = package / "cli.js"
    _check(
        [node, str(cli), "install", "chromium", *(["--with-deps"] if os.environ.get("CI") else [])],
        INSTALL_TIMEOUT,
    )
    return cli


def _attachments(result: dict, name: str) -> list:
    return [
        json.loads(base64.b64decode(a["body"]))
        for a in result.get("attachments", [])
        if a["name"] == name
    ]


def _failure(error: dict) -> dict:
    lines = [line for line in _ANSI.sub("", error.get("message", "")).splitlines() if line.strip()]
    failure = {"error": "\n".join(lines[:ERROR_LINES])}
    if loc := error.get("location"):
        # the run dir is temporary; the spec is kept in --out under the same name
        failure["location"] = f"{PureWindowsPath(loc['file']).name}:{loc['line']}:{loc['column']}"
    return failure


def parse_results(report: dict, ignore_console: Sequence[str] = ()) -> list[dict]:
    if report.get("errors"):
        message = _ANSI.sub("", report["errors"][0]["message"])
        raise ValueError(f"spec failed to load: {message.splitlines()[0]}")
    tests = []
    suites = list(report.get("suites", []))
    while suites:
        suite = suites.pop()
        suites += suite.get("suites", [])
        for spec in suite.get("specs", []):
            for t in spec["tests"]:
                result = t["results"][-1] if t["results"] else {"status": "skipped"}
                extra = (_attachments(result, "foreman") or [{}])[0]
                console = extra.get("consoleErrors", [])
                noise = [m for m in console if any(re.search(p, m) for p in ignore_console)]
                tests.append(
                    {
                        "title": spec["title"],
                        "project": t["projectName"],
                        "status": result["status"],
                        "console_errors": [m for m in console if m not in noise],
                        "ignored_console_errors": noise,
                        "bad_responses": extra.get("badResponses", []),
                        "screenshots": [
                            Path(p).as_posix() for p in _attachments(result, "foreman-screenshot")
                        ],
                        # what the spec printed (console.log), so exploration specs can report
                        "stdout": [
                            line
                            for chunk in result.get("stdout", [])
                            for line in _ANSI.sub("", chunk.get("text", "")).splitlines()
                            if line.strip()
                        ],
                        **(_failure(result["error"]) if "error" in result else {}),
                    }
                )
    if not tests:
        raise ValueError("spec ran no tests")
    return sorted(tests, key=lambda t: (t["title"], t["project"]))


def run_name() -> str:
    # pid + random suffix keeps runs started in the same second apart.
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{os.getpid()}-{secrets.token_hex(2)}"


def run(
    spec: Path,
    out: Path,
    base_url: str,
    branch_url: str | None = None,
    ignore_console: Sequence[str] = (),
) -> dict:
    if _DIRECT_IMPORT.search(spec.read_text(encoding="utf-8")):
        raise ValueError(
            f"{spec.as_posix()}: import test/expect from './{FIXTURES}', not '@playwright/test'"
        )
    cli = ensure()
    runs = cache_dir() / "runs"
    run_dir = runs / run_name()
    run_dir.mkdir(parents=True)
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    results = out / "results.json"
    results.unlink(missing_ok=True)
    try:
        for src in (spec, TEMPLATES / FIXTURES, TEMPLATES / CONFIG):
            shutil.copy2(src, run_dir)
        env = {**os.environ, "FOREMAN_BASE_URL": base_url, "FOREMAN_OUT": str(out)}
        if branch_url:
            env["FOREMAN_BRANCH_URL"] = branch_url
        proc = _run(
            [_tool("node"), str(cli), "test", "-c", CONFIG], TEST_TIMEOUT, cwd=run_dir, env=env
        )
        if not results.exists():
            raise OSError(f"playwright produced no results: {_last_line(proc)}")
        tests = parse_results(json.loads(results.read_text(encoding="utf-8")), ignore_console)
        kept = out / spec.name
        if not (kept.exists() and os.path.samefile(spec, kept)):
            shutil.copy2(spec, out)
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
    for old in runs.iterdir():
        if time.time() - old.stat().st_mtime > RUN_MAX_AGE:
            shutil.rmtree(old, ignore_errors=True)
    return {"tests": tests, "spec": (out / spec.name).as_posix()}
