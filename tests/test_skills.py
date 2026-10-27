import json
import os
import re
import subprocess
import sys
from pathlib import Path

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


def _snippet(tmp_path, marker: str) -> Path:
    text = (SKILLS_DIR / "verify" / "references" / "servers.md").read_text(encoding="utf-8")
    code = next(c for c in re.findall(r"```python\n(.*?)```", text, re.DOTALL) if marker in c)
    path = tmp_path / f"{marker}.py"
    path.write_text(code, encoding="utf-8")
    return path


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
