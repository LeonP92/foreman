"""Run Playwright specs against base and branch URLs from a private, pinned install."""

import base64
import json
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from foreman.render import TEMPLATES

PLAYWRIGHT_VERSION = "1.64.1"
MIN_NODE = 20
FIXTURES = "foreman-fixtures.mjs"
CONFIG = "playwright.config.mjs"
RUN_MAX_AGE = 7 * 24 * 3600


def cache_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ["LOCALAPPDATA"]) / "foreman" / "playwright"
    root = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(root) / "foreman" / "playwright"


def _tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise ValueError(f"{name} not found on PATH; install Node >= {MIN_NODE}")
    return path


def _check(args: list[str], **kwargs) -> str:
    proc = subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8", check=False, **kwargs
    )
    if proc.returncode:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or [f"exit {proc.returncode}"]
        raise OSError(f"{' '.join(args)} failed: {tail[0]}")
    return proc.stdout


def ensure() -> Path:
    node = _tool("node")
    version = _check([node, "--version"]).strip()
    if int(version.lstrip("v").split(".")[0]) < MIN_NODE:
        raise ValueError(f"Node >= {MIN_NODE} required, found {version}")
    cache = cache_dir()
    package = cache / "node_modules" / "@playwright" / "test"
    pkg_json = package / "package.json"
    installed = pkg_json.exists() and json.loads(pkg_json.read_text(encoding="utf-8"))["version"]
    if installed != PLAYWRIGHT_VERSION:
        cache.mkdir(parents=True, exist_ok=True)
        # --prefix stops npm from walking up to an ancestor project.
        _check(
            [
                _tool("npm"),
                "install",
                "--prefix",
                str(cache),
                "--no-audit",
                "--no-fund",
                f"@playwright/test@{PLAYWRIGHT_VERSION}",
            ]
        )
    cli = package / "cli.js"
    _check(
        [node, str(cli), "install", "chromium", *(["--with-deps"] if os.environ.get("CI") else [])]
    )
    return cli


def _attachment(result: dict) -> dict:
    for a in result.get("attachments", []):
        if a["name"] == "foreman":
            return json.loads(base64.b64decode(a["body"]))
    return {}


def parse_results(report: dict) -> list[dict]:
    tests = []
    suites = list(report.get("suites", []))
    while suites:
        suite = suites.pop()
        suites += suite.get("suites", [])
        for spec in suite.get("specs", []):
            for t in spec["tests"]:
                result = t["results"][-1] if t["results"] else {"status": "skipped"}
                extra = _attachment(result)
                tests.append(
                    {
                        "title": spec["title"],
                        "project": t["projectName"],
                        "status": result["status"],
                        "console_errors": extra.get("consoleErrors", []),
                        "bad_responses": extra.get("badResponses", []),
                        "screenshots": [Path(p).as_posix() for p in extra.get("screenshots", [])],
                    }
                )
    return sorted(tests, key=lambda t: (t["title"], t["project"]))


def run(spec: Path, out: Path, base_url: str, branch_url: str | None = None) -> dict:
    if "@playwright/test" in spec.read_text(encoding="utf-8"):
        raise ValueError(
            f"{spec.as_posix()}: import test/expect from './{FIXTURES}', not '@playwright/test'"
        )
    cli = ensure()
    runs = cache_dir() / "runs"
    run_dir = runs / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
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
        proc = subprocess.run(
            [_tool("node"), str(cli), "test", "-c", CONFIG],
            cwd=run_dir,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if not results.exists():
            tail = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or [
                f"exit {proc.returncode}"
            ]
            raise OSError(f"playwright produced no results: {tail[0]}")
        tests = parse_results(json.loads(results.read_text(encoding="utf-8")))
        shutil.copy2(spec, out)
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
    for old in runs.iterdir():
        if time.time() - old.stat().st_mtime > RUN_MAX_AGE:
            shutil.rmtree(old, ignore_errors=True)
    return {"tests": tests, "spec": (out / spec.name).as_posix()}
