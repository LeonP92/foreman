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
        text = " ".join(skill_text(skill).split())
        for phrase in ["git merge-base", "nothing to review", "already merged", "BASE^"]:
            assert phrase in text, (skill, phrase)


def test_every_skill_forbids_touching_what_it_did_not_create():
    rule = "Never delete or modify anything you didn't create in this run"
    git = "never run repo-wide git maintenance (`git worktree prune`, `git gc`, branch deletion)"
    for skill in SKILLS:
        text = " ".join(skill_text(skill).split())
        assert rule in text, skill
        assert git in text, skill


def test_review_flags_gone_or_squash_merged_branches():
    text = " ".join(skill_text("review").split())
    report = " ".join(
        (SKILLS_DIR / "review" / "references" / "report.md").read_text(encoding="utf-8").split()
    )
    for phrase in [
        "git ls-remote --heads",
        "`git rev-parse --abbrev-ref <branch>@{upstream}` succeeds",
        "`refs/remotes/<remote>/<branch>` exists",
        "never pushed gets no header",
        "every line of `git cherry <repo.base> <branch>` starts with `-`",
        "`git log --format='%h %s' BASE..<repo.base>`",
        "`#N` PR number",
        "never fetch",
        "continues on the given tip",
    ]:
        assert phrase in text, phrase
    for phrase in ["branch deleted on remote", "appears squash-merged as <sha>"]:
        assert phrase in text, phrase
        assert phrase in report, phrase


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
        '`[graph] skip = [".sh", …]`',
        "`unmatched_examples`",
        "`external`",
        "`external_examples`",
    ]:
        assert phrase in text, phrase


def test_verify_builds_data_instead_of_skipping():
    verify = " ".join(skill_text("verify").split())
    data = " ".join(
        (SKILLS_DIR / "verify" / "references" / "data.md").read_text(encoding="utf-8").split()
    )
    for phrase in [
        'Never skip an item for "no matching data"',
        "references/data.md",
        "existing-data-survives",
        "--env-file",
    ]:
        assert phrase in verify, phrase
    for phrase in [
        "Phase a",
        "Phase b",
        "403",
        "on **both** sides",
        "Never grant anything in real data",
        "querying the branch **copy**",
    ]:
        assert phrase in data, phrase


def test_env_files_are_read_only_through_the_names_helper():
    rule = "may be read only through the names-only `run.py dotenv`"
    ask = "ask the user which variable names it sets"
    for text in [
        skill_text("setup"),
        (SKILLS_DIR / "verify" / "references" / "servers.md").read_text(encoding="utf-8"),
    ]:
        text = " ".join(text.split())
        assert rule in text
        assert ask in text
    assert "Never open `.env`" not in all_skill_text()


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


def test_known_console_noise_is_explained_where_it_is_offered():
    assert "ignore_console" in skill_text("setup")
    assert "ignored_console_errors" in skill_text("verify")


def test_diagram_decides_hubs_before_grouping():
    text = " ".join(skill_text("diagram").split())
    for phrase in [
        "on the ungrouped graph",
        "never group a hub's direct neighbours",
        "ungrouped neighbour count",
    ]:
        assert phrase in text, phrase


def test_every_change_run_keeps_its_own_report_folder():
    for skill in ["review", "verify", "diagram"]:
        text = " ".join(skill_text(skill).split())
        for phrase in [
            "`<run> = .foreman/reports/<branch>/<stamp>/`",
            "`%Y%m%dT%H%M%SZ`",
            "Never write into an earlier run's folder",
            "`.foreman/reports/<branch>/latest`",
        ]:
            assert phrase in text, (skill, phrase)
    assert ".foreman/reports/<branch>/verify" not in all_skill_text()


def test_review_runs_targeted_tests_per_suite():
    text = " ".join(skill_text("review").split())
    assert "separately per suite" in text
    assert "one row per command" in text


def test_exploration_output_is_kept():
    specs = (SKILLS_DIR / "verify" / "references" / "specs.md").read_text(encoding="utf-8")
    assert "--out <run>/explore" in specs
    assert "`<run>/explore/`" in skill_text("verify")


def test_file_databases_can_use_a_per_server_url():
    servers = " ".join(
        (SKILLS_DIR / "verify" / "references" / "servers.md").read_text(encoding="utf-8").split()
    )
    assert "always for `command`, optionally for `file`" in servers
    assert "when `env_override` is set" in " ".join(skill_text("verify").split())


def test_diagram_keeps_standalone_changed_files():
    text = " ".join(skill_text("diagram").split())
    assert "Every `affected` node needs an edge" in text
    assert "standalone node in its lane" in text


def test_every_audit_run_keeps_its_own_report_folder():
    text = " ".join(skill_text("audit").split())
    for phrase in [
        "`<run> = .foreman/reports/audit/<stamp>/`",
        "`%Y%m%dT%H%M%SZ`",
        "Never write into an earlier run's folder",
        "`.foreman/reports/audit/latest`",
        "--out <run>/smoke",
    ]:
        assert phrase in text, phrase


def test_skills_call_helper_commands_instead_of_embedding_scripts():
    text = all_skill_text()
    for command in ["launch", "dotenv", "throwaway"]:
        assert f"run.py {command} " in text, command
    assert "```python" not in text
    assert "foreman-bin" not in text


def test_throwaway_secrets_survive_cleanup():
    ci = " ".join(
        (SKILLS_DIR / "setup" / "references" / "ci.md").read_text(encoding="utf-8").split()
    )
    verify = " ".join(skill_text("verify").split())
    for text in (ci, verify):
        assert "never removed by cleanup" in text
    assert "lock file" in ci


def test_review_verifies_user_visible_changes_and_reads_squash_merges_from_gh():
    text = " ".join(skill_text("review").split())
    for phrase in [
        "even if no template or route file changed",
        "a local stub the repo provides",
        "a tiny local fake server",
        "gh pr list --head <branch> --state merged --json number,mergeCommit",
        "runs once, in full, and the report says so",
    ]:
        assert phrase in text, phrase


def test_run_folders_strip_the_remote_prefix():
    for skill in ["review", "verify", "diagram"]:
        assert "(`origin/foo` → `foo`)" in " ".join(skill_text(skill).split()), skill


def test_audit_smoke_never_copies_real_data():
    text = " ".join(skill_text("audit").split())
    for phrase in ["never copy the real database", "skip `seed`", '`kind = "none"`']:
        assert phrase in text, phrase


def test_audit_triages_candidates_before_reporting():
    text = " ".join(skill_text("audit").split())
    for phrase in [
        "references/triage.md",
        "60",
        "CONFIRMED",
        "DISMISSED",
        "map --out <run> --dismiss <run>/triage.json",
        "candidates · C confirmed · D dismissed · U not triaged (budget)",
        "counts confirmed smells only",
        "every high item first (never capped), then medium and low items round-robin across kinds",
        "one item per file (or file pair/set)",
        "`not_triaged`",
        "CONFIRM only when you can state a concrete cost",
        "no checklist type fits, and no concrete cost found",
    ]:
        assert phrase in text, phrase
    triage = " ".join(
        (SKILLS_DIR / "audit" / "references" / "triage.md")
        .read_text(encoding="utf-8")
        .lower()
        .split()
    )
    for phrase in [
        "sweep",
        "generated",
        "vendored",
        "fixtures",
        "definitions",
        "public",
        "reflection",
        "migrations",
        "per-locale",
        "file:line",
        "concrete cost",
        "its own test",
        "type-only",
        "sibling implementations",
        "composition roots",
        "hotspot",
    ]:
        assert phrase in triage, phrase
