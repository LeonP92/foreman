import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from foreman.cli import COMMANDS

SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
SKILLS = ["setup", "review", "verify", "diagram", "audit"]


def all_skill_text() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(SKILLS_DIR.rglob("*.md")))


def frontmatter(skill: str) -> dict[str, str]:
    text = (SKILLS_DIR / skill / "SKILL.md").read_text(encoding="utf-8")
    head = text.split("---\n")[1]
    return dict(line.split(": ", 1) for line in head.strip().splitlines())


def test_each_skill_has_matching_frontmatter():
    for skill in SKILLS:
        meta = frontmatter(skill)
        assert meta["name"] == skill
        assert 0 < len(meta["description"]) <= 300


def test_skills_only_reference_real_cli_commands():
    used = set(re.findall(r"run\.py ([a-z][\w-]*)", all_skill_text()))
    assert used
    assert used <= set(COMMANDS)


def test_skills_are_agent_neutral():
    text = all_skill_text()
    for term in ["mcp__", "${CLAUDE_", "Bash tool", "Read tool", "TodoWrite", "subagent_type"]:
        assert term not in text


def skill_text(skill: str) -> str:
    return (SKILLS_DIR / skill / "SKILL.md").read_text(encoding="utf-8")


def test_change_skills_compare_against_the_merge_base():
    for skill in ["review", "verify", "diagram"]:
        text = " ".join(skill_text(skill).split())
        for phrase in ["git merge-base", "nothing to review", "already merged", "BASE^"]:
            assert phrase in text, (skill, phrase)


def test_every_skill_forbids_touching_what_it_did_not_create():
    rule = "Never delete or modify anything you didn't create in this run"
    for skill in SKILLS:
        assert rule in " ".join(skill_text(skill).split()), skill


def _snippet(tmp_path, marker: str, ref: str = "verify/references/servers.md") -> Path:
    text = (SKILLS_DIR / ref).read_text(encoding="utf-8")
    code = next(c for c in re.findall(r"```python\n(.*?)```", text, re.DOTALL) if marker in c)
    path = tmp_path / f"{marker}.py"
    path.write_text(code, encoding="utf-8")
    return path


def test_verify_spec_guidance_covers_known_pitfalls():
    text = " ".join(
        (SKILLS_DIR / "verify" / "references" / "specs.md").read_text(encoding="utf-8").split()
    )
    for phrase in [
        'Never `test.describe.configure({ mode: "serial" })`',
        "`toBeVisible()` / `toBeHidden()`",
        "one database per side",
        "through `browser-run`",
        "remove only the files it created",
    ]:
        assert phrase in text, phrase
    assert "references/specs.md" in skill_text("verify")


def test_setup_reads_ci_and_stops_on_import_free_languages():
    text = " ".join(skill_text("setup").split())
    for phrase in [
        "`env:` blocks",
        "references/ci.md",
        "no import statements",
        "stop after the first try",
    ]:
        assert phrase in text, phrase


def _py(*args, env=None):
    return subprocess.run(
        [sys.executable, "-I", *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=env,
    )


def test_dotenv_helper_lists_names_and_rewrites_lines(tmp_path):
    helper = _snippet(tmp_path, "dotenv.py")
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "SECRET_KEY=s3cret\r\nexport DATABASE_URL=sqlite:///real.db\r\n", encoding="utf-8"
    )
    listed = _py(helper, dotenv)
    assert listed.stdout.split() == ["DATABASE_URL", "SECRET_KEY"]
    assert "s3cret" not in listed.stdout
    _py(helper, dotenv, "DATABASE_URL=sqlite:///copy.db")
    assert dotenv.read_bytes() == b"SECRET_KEY=s3cret\r\nexport DATABASE_URL=sqlite:///copy.db\r\n"


def test_launcher_reads_references_after_removing_database_variables(tmp_path):
    launcher = _snippet(tmp_path, "launch")
    settings = tmp_path / "s.json"
    settings.write_text(
        json.dumps({"remove": ["DATABASE_URL"], "command": {"A": "${SHOP_KEY}"}, "server": {}}),
        encoding="utf-8",
    )
    env = {**os.environ, "SHOP_KEY": "k", "DATABASE_URL": "sqlite:///real.db"}
    show = f"\"{sys.executable}\" -c \"import os; print(os.environ.get('A'), 'DATABASE_URL' in os.environ)\""
    ran = _py(launcher, settings, tmp_path, "-", show, env=env)
    assert ran.stdout.split() == ["k", "False"]
    settings.write_text(
        json.dumps({"remove": ["DATABASE_URL"], "command": {"A": "${DATABASE_URL}"}, "server": {}}),
        encoding="utf-8",
    )
    failed = _py(launcher, settings, tmp_path, "-", show, env=env)
    assert failed.returncode == 1
    assert failed.stderr.strip().splitlines() == [
        "launch: ${DATABASE_URL} is not set, or names a removed database location"
    ]


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_throwaway_secrets_go_to_a_user_only_file_and_are_not_printed(tmp_path):
    helper = _snippet(tmp_path, "throwaway.py", "setup/references/ci.md")
    out = tmp_path / "cfg" / "shop.env"
    ran = _py(helper, out, "SHOP_SECRET_KEY", "SHOP_SIGNING_KEY")
    assert ran.stdout.split() == ["SHOP_SECRET_KEY", "SHOP_SIGNING_KEY"]
    lines = out.read_text(encoding="utf-8").splitlines()
    assert [line.split("=", 1)[0] for line in lines] == ["SHOP_SECRET_KEY", "SHOP_SIGNING_KEY"]
    assert all(line.split("=", 1)[1] not in ran.stdout for line in lines)
    assert out.stat().st_mode & 0o777 == 0o600


def test_diagram_groups_large_neighbourhoods():
    text = " ".join(skill_text("diagram").split())
    for phrase in [
        "more than 20 unchanged one-hop neighbours",
        "per package directory",
        "labelled with the count",
    ]:
        assert phrase in text, phrase


def test_verdict_counts_only_must_fix():
    text = " ".join(
        (SKILLS_DIR / "review" / "references" / "report.md").read_text(encoding="utf-8").split()
    )
    assert "N is exactly the number of Must fix findings" in text
    assert "never change the verdict" in text
