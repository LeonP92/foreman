---
name: review
description: The pre-merge gate for a branch: simplicity and design findings, the repo's tests, a real-browser check of user-facing changes, and a dependency diagram, in one ranked report a person can absorb in a minute. Use before merging, or when asked to review a branch or PR.
---

# Review

A person should not need to read the diff. They read the top of your report, see whether
the change works and what needs their judgement, and drill in only if they want to.

## Before you start

- Run foreman's scripts as `python3 -I <root>/scripts/run.py <command>` (`python` or `py` on
  Windows), where `<root>` is two directories above this file. Run them from the repo's top
  folder; every command prints JSON.
- If `.foreman/config.toml` is missing or `config-check` fails, run the setup skill first.
- Rules: never commit, push, or edit product code; never point anything at real data; pass
  credentials only through files or environment variables and never print them; clean up
  every worktree, server (whole process tree), and temp file you create. Never delete or
  modify anything you didn't create in this run — including ignored files and folders.
  End with "Not checked:" and why.

The branch is the one the user named, else the current one. You review what the branch
has committed against `BASE = git merge-base <repo.base> <branch>`, never the tip of
`repo.base`: a branch already merged (or squash-merged) would otherwise be compared with
itself. If `BASE` equals the branch tip, check `git rev-list --first-parent <repo.base>`:
if the tip is on it, the branch has no commits of its own and there is nothing to review
(say so and stop); otherwise it was already merged (say so in the report and use `BASE^`,
the merge-base's first parent, as `BASE`). Diff with
`git diff BASE <branch>`; anything run on the base (tests in step 4, verify, the diagram)
uses a worktree at `BASE`. The report names both SHAs. If the branch isn't checked out,
or the working tree has uncommitted changes, work in a temporary worktree of the branch
(`git worktree add --detach <temp> <branch>`, with `<temp>` under the system temp
directory, outside the repo). Prepare every worktree you add (copy `[repo] copy` files,
then `install`, `build`) and run every command in it through the launcher, as
`<root>/skills/verify/references/servers.md` says. Report:
`.foreman/reports/<branch>/review.md`, where `<branch>` has each `/` replaced by `-`.

## Steps

1. **Understand.** Start from the diff, then open what it reaches: whoever calls the
   changed functions, the tests that exercise them, the interfaces they implement. Read
   the repo's instructions (`AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING*`) and every doc they
   or `[rules] docs` say applies to the touched areas. Write 2–3 sentences on what the change does.
2. **Simplicity.** Apply `references/simplicity.md`.
3. **Design.** Check the change against the repo's stated rules: layering, what a package
   may export, compliance rules (audit logging, data retention), security rules (CSRF,
   permission checks), naming. Each finding names the rule and where it is written
   (`docs/architecture.md`, "Layers"). A repo with no stated rules gets only checks that
   hold everywhere: no new import cycle, no secret in code, no user input reaching SQL,
   HTML or a shell unescaped, no new route without the access check its neighbours have.
4. **Tests.** First the tests that cover the changed code (`test_targeted` with `{paths}`
   filled in, or `test` if empty), then the full checks: `lint`, `typecheck`, `test`,
   `e2e`, skipping empty ones. Record each command and its result. On a failure, keep the
   lines that show why, and run that test on the base too: a failure on both is
   pre-existing; report it, but not as this change's fault.
5. **Verify.** If the diff touches anything a user sees (templates, components, styles,
   routes that return HTML or redirect, form handling), follow the verify skill. Otherwise
   write "n/a, no user-facing change".
6. **Diagram.** Follow the diagram skill.

Then write the report as `references/report.md` describes, and show the user its top
block and findings. Findings from all six steps share one numbered list, so a reply can
pick them out by number. Do not fix anything.

## What makes a finding

- A location (`file:line`, or page and steps).
- The problem in one sentence.
- A concrete case where it goes wrong: an input, a sequence of actions, a load. If you
  can't write one down, drop the finding.
- The smallest fix, and what happens if it's skipped.

Severity:
- **Must fix**: wrong results, an opening for an attacker, lost or corrupted data, or a
  failure under the traffic the repo is built for.
- **Should fix**: a page that works on base and breaks on the branch, untested logic that
  can break, logic repeated in two places, code nothing needs, a slowdown someone will
  notice.
- **Nice to have**: everything else worth a sentence.

Leave out personal preference, worries you can't back with a case, and anything the
repo's linter already catches.

## Finish

Remove any worktree you added, and confirm verify cleaned up its servers. End the report
with "Not checked:" and why.
