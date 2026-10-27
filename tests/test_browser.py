import json
import subprocess
from pathlib import Path

import pytest
from foreman import browser
from foreman.browser import parse_results, run
from foreman.cli import main

SITE = Path(__file__).parent / "browser_site"
SPEC = SITE / "total.spec.mjs"


def test_parse_results_maps_projects_errors_and_screenshots():
    report = json.loads(
        (Path(__file__).parent / "data" / "playwright_results.json").read_text(encoding="utf-8")
    )
    assert parse_results(report) == [
        {
            "title": "total shows 3",
            "project": "base",
            "status": "failed",
            "console_errors": [
                "Failed to load resource: the server responded with a status of 404 (File not found)"
            ],
            "bad_responses": ["404 http://127.0.0.1:50001/missing.js"],
            "screenshots": ["/out/total-shows-3-base.png"],
            "error": "Error: expect(locator).toHaveText(expected) failed\n"
            "Locator:  locator('#total')\n"
            'Expected: "3"\n'
            'Received: "2"\n'
            "Timeout:  1000ms",
            "location": "total.spec.mjs:5:40",
        },
        {
            "title": "total shows 3",
            "project": "branch",
            "status": "passed",
            "console_errors": [],
            "bad_responses": [],
            "screenshots": ["/out/total-shows-3-branch.png"],
        },
    ]


def test_node_too_old_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(browser.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        browser.subprocess,
        "run",
        lambda args, **kw: subprocess.CompletedProcess(args, 0, "v18.19.0\n", ""),
    )
    with pytest.raises(ValueError, match=r"Node >= 20 required, found v18\.19\.0"):
        browser.ensure()


@pytest.mark.parametrize(
    "line",
    [
        'import { test } from "@playwright/test";',
        "  import { test, expect } from '@playwright/test';",
        'const pw = await import("@playwright/test");',
        "const { test } = require('@playwright/test');",
        'import {\n  test,\n  expect,\n} from "@playwright/test";',
        'export { test, expect } from "@playwright/test";',
    ],
)
def test_spec_importing_playwright_directly_is_rejected(tmp_path, line):
    spec = tmp_path / "x.spec.mjs"
    spec.write_text(line + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="foreman-fixtures"):
        run(spec, tmp_path / "out", "http://127.0.0.1:1")


def test_spec_mentioning_playwright_in_a_comment_is_accepted(tmp_path, monkeypatch):
    def past_check():
        raise RuntimeError("past the import check")

    monkeypatch.setattr(browser, "ensure", past_check)
    spec = tmp_path / "x.spec.mjs"
    spec.write_text(
        "// wraps \"@playwright/test\"; never import from '@playwright/test' here\n"
        'import { test } from "./foreman-fixtures.mjs";\n',
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="past the import check"):
        run(spec, tmp_path / "out", "http://127.0.0.1:1")


def test_load_errors_are_reported_not_read_as_clean():
    report = {
        "suites": [],
        "errors": [{"message": "SyntaxError: Unexpected token '}'\n  at x.mjs:3"}],
    }
    with pytest.raises(
        ValueError, match=r"^spec failed to load: SyntaxError: Unexpected token '}'$"
    ):
        parse_results(report)


def test_spec_with_no_tests_is_an_error():
    with pytest.raises(ValueError, match="spec ran no tests"):
        parse_results({"suites": [], "errors": []})


def test_unreadable_node_version_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(browser.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        browser.subprocess,
        "run",
        lambda args, **kw: subprocess.CompletedProcess(args, 0, "node\n", ""),
    )
    with pytest.raises(ValueError, match="cannot read the Node version from 'node'"):
        browser.ensure()


def test_corrupt_cached_package_is_reinstalled(tmp_path, monkeypatch):
    package = tmp_path / "node_modules" / "@playwright" / "test"
    package.mkdir(parents=True)
    (package / "package.json").write_text("{not json", encoding="utf-8")
    calls = []
    monkeypatch.setattr(browser, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(browser.shutil, "which", lambda name: name)
    monkeypatch.setattr(
        browser.subprocess,
        "run",
        lambda args, **kw: (
            calls.append(args) or subprocess.CompletedProcess(args, 0, "v24.1.0", "")
        ),
    )
    browser.ensure()
    assert [c[:2] for c in calls][1] == ["npm", "install"]


def test_timeout_is_a_one_line_os_error(monkeypatch):
    def hang(args, **kw):
        raise subprocess.TimeoutExpired(args, kw["timeout"])

    monkeypatch.setattr(browser.subprocess, "run", hang)
    with pytest.raises(OSError, match=r"^npm install timed out after 600 s$"):
        browser._check(["npm", "install"], browser.INSTALL_TIMEOUT)


def test_back_to_back_run_names_differ():
    assert browser.run_name() != browser.run_name()


@pytest.mark.browser
def test_run_base_vs_branch(tmp_path, serve):
    r = run(SPEC, tmp_path, serve(SITE / "base"), serve(SITE / "branch"))
    assert {t["project"]: t["status"] for t in r["tests"]} == {"base": "failed", "branch": "passed"}
    assert any("404" in b for t in r["tests"] if t["project"] == "base" for b in t["bad_responses"])
    assert (tmp_path / "total-shows-3-branch.png").exists()
    assert r["spec"] == (tmp_path / "total.spec.mjs").as_posix()
    assert (tmp_path / "total.spec.mjs").exists()


@pytest.mark.browser
def test_single_url_runs_one_project(tmp_path, serve):
    # Two titles share a slug; the spec already sits in out/ and must survive the run.
    spec = tmp_path / "total.spec.mjs"
    spec.write_text(
        SPEC.read_text(encoding="utf-8").replace('"total shows 3"', '"total shows 3!"')
        + SPEC.read_text(encoding="utf-8").split("\n", 1)[1],
        encoding="utf-8",
    )
    r = run(spec, tmp_path, serve(SITE / "branch"))
    assert [(t["project"], t["status"]) for t in r["tests"]] == [("app", "passed")] * 2
    assert (tmp_path / "total-shows-3-app.png").exists()
    assert (tmp_path / "total-shows-3-2-app.png").exists()
    assert "total shows 3!" in spec.read_text(encoding="utf-8")


@pytest.mark.browser
def test_spec_that_fails_to_load_exits_1(tmp_path, serve, capsys):
    spec = tmp_path / "broken.spec.mjs"
    spec.write_text(
        'import { test } from "./foreman-fixtures.mjs";\ntest("x", () => {\n', encoding="utf-8"
    )
    url = serve(SITE / "branch")
    assert (
        main(["browser-run", "--spec", str(spec), "--out", str(tmp_path / "out"), "--base", url])
        == 1
    )
    assert capsys.readouterr().err.startswith("foreman: spec failed to load: ")
