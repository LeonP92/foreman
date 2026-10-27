import re
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
        assert "git merge-base" in skill_text(skill), skill


def test_every_skill_forbids_touching_what_it_did_not_create():
    rule = "Never delete or modify anything you didn't create in this run"
    for skill in SKILLS:
        assert rule in " ".join(skill_text(skill).split()), skill
