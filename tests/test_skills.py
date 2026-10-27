import json
import os
import re
import subprocess
import sys
import time
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


def _settings(command: dict, tmp_path: Path) -> dict:
    return {
        "remove": ["DATABASE_URL"],
        "checkout": str(tmp_path / "main"),
        "command": command,
        "server": {},
    }


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
    helper = _snippet(tmp_path, "foreman_dotenv.py")
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
    launcher = _snippet(tmp_path, "foreman_launch.py")
    settings = tmp_path / "s.json"
    settings.write_text(
        json.dumps(_settings({"A": "${SHOP_KEY}"}, tmp_path)),
        encoding="utf-8",
    )
    env = {**os.environ, "SHOP_KEY": "k", "DATABASE_URL": "sqlite:///real.db"}
    show = f"\"{sys.executable}\" -c \"import os; print(os.environ.get('A'), 'DATABASE_URL' in os.environ)\""
    ran = _py(launcher, settings, tmp_path, "-", show, env=env)
    assert ran.stdout.split() == ["k", "False"]
    settings.write_text(
        json.dumps(_settings({"A": "${DATABASE_URL}"}, tmp_path)),
        encoding="utf-8",
    )
    failed = _py(launcher, settings, tmp_path, "-", show, env=env)
    assert failed.returncode == 1
    assert failed.stderr.strip().splitlines() == [
        "launch: ${DATABASE_URL} is not set, or names a removed database location"
    ]


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_throwaway_secrets_go_to_a_stable_user_only_file_and_are_not_printed(tmp_path):
    helper = _snippet(tmp_path, "foreman_throwaway.py", "setup/references/ci.md")
    repo = tmp_path / "shop"
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "cfg")}
    only_path = _py(helper, repo, env=env).stdout.split()
    assert len(only_path) == 1
    out = Path(only_path[0])
    assert re.fullmatch(r"shop-[0-9a-f]{8}\.env", out.name)
    assert out.parent == tmp_path / "cfg" / "foreman" / "secrets"
    assert not out.exists()
    ran = _py(helper, repo, "SHOP_SECRET_KEY", "SHOP_SIGNING_KEY", env=env)
    assert ran.stdout.split() == [out.as_posix(), "SHOP_SECRET_KEY", "SHOP_SIGNING_KEY"]
    again = _py(helper, repo, "SHOP_SECRET_KEY", "SHOP_OTHER_KEY", env=env)
    assert again.stdout.split() == [out.as_posix(), "SHOP_OTHER_KEY"]
    lines = out.read_text(encoding="utf-8").splitlines()
    assert [line.split("=", 1)[0] for line in lines] == [
        "SHOP_SECRET_KEY",
        "SHOP_SIGNING_KEY",
        "SHOP_OTHER_KEY",
    ]
    assert all(line.split("=", 1)[1] not in ran.stdout + again.stdout for line in lines)
    assert out.stat().st_mode & 0o777 == 0o600


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
    rule = "may be read only through the names-only helper `foreman_dotenv.py`"
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


def test_launcher_loads_env_files_but_never_a_database_location(tmp_path):
    launcher = _snippet(tmp_path, "foreman_launch.py")
    settings = tmp_path / "s.json"
    settings.write_text(
        json.dumps(_settings({"A": "${SHOP_KEY}"}, tmp_path)),
        encoding="utf-8",
    )
    secrets_file = tmp_path / "shop.env"
    secrets_file.write_text("SHOP_KEY=from-file\r\n", encoding="utf-8")
    show = f'"{sys.executable}" -c "import os; print(os.environ.get(\'A\'))"'
    env = {k: v for k, v in os.environ.items() if k != "SHOP_KEY"}
    ran = _py(launcher, "--env-file", secrets_file, settings, tmp_path, "-", show, env=env)
    assert ran.stdout.split() == ["from-file"]
    secrets_file.write_text("SHOP_KEY=k\nDATABASE_URL=sqlite:///real.db\n", encoding="utf-8")
    failed = _py(launcher, "--env-file", secrets_file, settings, tmp_path, "-", show, env=env)
    assert failed.returncode == 1
    assert failed.stderr.strip().splitlines() == [
        f"launch: {secrets_file} sets DATABASE_URL, a removed database location"
    ]
    assert "real.db" not in failed.stderr


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


def test_launcher_drops_variables_pointing_into_the_main_checkout(tmp_path):
    launcher = _snippet(tmp_path, "foreman_launch.py")
    settings = tmp_path / "s.json"
    settings.write_text(json.dumps(_settings({}, tmp_path)), encoding="utf-8")
    main = tmp_path / "main"
    env = {
        **os.environ,
        "VIRTUAL_ENV": "/elsewhere/venv",
        "PYTHONPATH": "/elsewhere/lib",
        "NODE_PATH": "/elsewhere/node",
        "SHOP_CACHE": str(main / "cache"),
        "SHOP_DOTTED": f"{tmp_path}{os.sep}x{os.sep}..{os.sep}main{os.sep}.{os.sep}logs",
        "SHOP_NEIGHBOUR": str(tmp_path / "main-other"),
        "PATH": os.pathsep.join([str(main / ".venv" / "bin"), os.environ["PATH"]]),
    }
    names = [
        "VIRTUAL_ENV",
        "PYTHONPATH",
        "NODE_PATH",
        "SHOP_CACHE",
        "SHOP_DOTTED",
        "SHOP_NEIGHBOUR",
    ]
    show = (
        f'"{sys.executable}" -c "import os; '
        f"print(*[n for n in {names!r} if n in os.environ], str(os.environ['PATH']).startswith({str(main)!r}))\""
    )
    ran = _py(launcher, settings, tmp_path, "-", show, env=env)
    assert ran.stdout.split() == ["SHOP_NEIGHBOUR", "False"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_throwaway_secrets_wait_for_the_lock(tmp_path):
    helper = _snippet(tmp_path, "foreman_throwaway.py", "setup/references/ci.md")
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "cfg")}
    repo = tmp_path / "shop"
    path = Path(_py(helper, repo, "SHOP_A", env=env).stdout.split()[0])
    lock = path.with_suffix(".lock")
    lock.touch()
    proc = subprocess.Popen(
        [sys.executable, "-I", str(helper), str(repo), "SHOP_A", "SHOP_B"],
        env=env,
        stdout=subprocess.PIPE,
        encoding="utf-8",
    )
    time.sleep(0.5)
    assert proc.poll() is None
    assert path.read_text(encoding="utf-8").count("SHOP_B") == 0
    lock.unlink()
    assert proc.communicate(timeout=10)[0].split() == [path.as_posix(), "SHOP_B"]
    names = [line.split("=", 1)[0] for line in path.read_text(encoding="utf-8").splitlines()]
    assert names == ["SHOP_A", "SHOP_B"]
    assert not lock.exists()


def test_helpers_live_apart_under_collision_free_names():
    text = " ".join(all_skill_text().split())
    for name in ["foreman_dotenv.py", "foreman_launch.py", "foreman_throwaway.py"]:
        assert f"<temp>/foreman-bin/{name}" in text, name
    for old in ["<temp>/dotenv.py", "<temp>/launch.py", "<temp>/throwaway.py"]:
        assert old not in text, old
    servers = " ".join(
        (SKILLS_DIR / "verify" / "references" / "servers.md").read_text(encoding="utf-8").split()
    )
    assert "cwd = the worktree, never the helper dir" in servers
    for var in ["`VIRTUAL_ENV`", "`PYTHONPATH`", "`NODE_PATH`", "main checkout"]:
        assert var in servers, var


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
    ]:
        assert phrase in triage, phrase
