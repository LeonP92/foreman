import json
import subprocess
from pathlib import Path

import pytest
from foreman import browser
from foreman.browser import parse_results, run

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


def test_spec_importing_playwright_directly_is_rejected(tmp_path):
    spec = tmp_path / "x.spec.mjs"
    spec.write_text('import { test } from "@playwright/test";\n', encoding="utf-8")
    with pytest.raises(ValueError, match="foreman-fixtures"):
        run(spec, tmp_path / "out", "http://127.0.0.1:1")


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
    r = run(SPEC, tmp_path, serve(SITE / "branch"))
    assert [(t["project"], t["status"]) for t in r["tests"]] == [("app", "passed")]
    assert (tmp_path / "total-shows-3-app.png").exists()
