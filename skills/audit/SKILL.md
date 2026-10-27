---
name: audit
description: Sweeps the whole repo on its base branch for structural smells (cycles, layering breaks, hubs, hidden coupling, hotspots, oversized files, duplication, dead code) and draws an interactive codebase map. Use for a periodic health check of the main branch, or when asked to audit a codebase.
---

# Audit

The main-branch checkpoint. Changes nothing; reports what a person should look at first,
and hands them a map to look with.

## Before you start

- Run foreman's scripts as `python3 -I <root>/scripts/run.py <command>` (`python` or `py` on
  Windows), where `<root>` is two directories above this file. Run them from the repo's top
  folder; every command prints JSON.
- If `.foreman/config.toml` is missing or `config-check` fails, run the setup skill first.
- Rules: never commit, push, or edit product code; never point anything at real data; pass
  credentials only through files or environment variables and never print them; clean up
  every worktree, server (whole process tree), and temp file you create. Never delete or
  modify anything you didn't create in this run — including ignored files and folders —
  and never run repo-wide git maintenance (`git worktree prune`, `git gc`, branch
  deletion). End with "Not checked:" and why.

Each run writes to its own folder, `<run> = .foreman/reports/audit/<stamp>/`, where
`<stamp>` is the UTC start time as `%Y%m%dT%H%M%SZ`. Never write into an earlier run's
folder; when done, write the stamp alone to `.foreman/reports/audit/latest`.

Output: `<run>` (`map.html`, `map.json`, `triage.json`, `audit.md`, and `smoke/` if you
run the UI pass).

## Steps

1. **Check out the base.** `git worktree add --detach <temp> <base>`, where `<base>` is
   `repo.base` and `<temp>` is a new folder under the system temp directory, outside the
   repo. Audit that, not the current checkout, so uncommitted work and the current
   branch don't leak in.
2. **Map it.** Run
   `python3 -I <root>/scripts/run.py map --root <temp> --config <repo>/.foreman/config.toml --out <run>`
   (both paths absolute). It prints the map path, group and module counts, the ranked
   smells (at most 20 per kind), `dropped` (how many more each kind had), `counts` (every
   smell by kind and severity, before that cap), and `unsupported`: file extensions that
   need an import rule.
3. **Triage the candidates.** The map's smells are candidates, not findings. Take every
   `high` one, then `medium` and `low` in the map's order, up to a budget of 60 in all
   (more only if the user asks). For each, read the files involved and apply the checklist
   in [`references/triage.md`](references/triage.md): mark it CONFIRMED or DISMISSED with a
   one-line reason and evidence (`file:line`). Write a suggested next step for each
   confirmed one. Thresholds are relative to this repo's own spread, not fixed numbers.
4. **Re-render without the dismissed.** Write `<run>/triage.json` as
   `{"dismissed": [{"kind": …, "nodes": […], "reason": …}]}`, with `kind` and `nodes` as the
   map lists them, then run
   `python3 -I <root>/scripts/run.py map --out <run> --dismiss <run>/triage.json`. It
   rewrites the map without them and counts them per kind under `dismissed`; fix any
   entry it rejects and re-run.
5. **UI smoke (optional).** If the repo has a UI and `[server]` is set, see below.
6. **Write the report** and remove the worktree.

## Smells the map finds

Cycles, layering breaks, hubs, hidden coupling, hotspots, oversized files, duplication and
possibly dead code. Each kind's rule, threshold and severity are in
[`docs/smells.md`](../../docs/smells.md).

## UI smoke

Only against the base server; there is no comparison. Data: never copy the real database,
and skip `seed`. With `kind = "none"` there is nothing to set up; with `kind = "command"`,
or `"file"` with `env_override` set, the server gets an empty database at its own `{name}`
or `{dir}`, made by `create` (if set) and `migrate`. Otherwise skip the smoke pass and say
why under "Not checked:". If signing in needs seeded data, smoke only the pages reachable
without it and list the rest. Follow the verify skill for preparing the worktree (copy,
install, build) and its environment, the server on a free port, login, and stopping the
whole process tree. Pick 3–8 main pages from the repo's routes (the router files, page folders
or URL config), one test each, titled by page (`cart`, `order-history`). For each page:
it loads, no console errors, no 4xx/5xx responses, and Tab moves a visible focus through
its controls. Run
`python3 -I <root>/scripts/run.py browser-run --spec <spec> --out <run>/smoke --base http://127.0.0.1:<port>`
with no `--branch`. Each problem is a finding with steps, expected, actual and screenshot.

## Report

Write `<run>/audit.md` in three parts. Candidates come from `counts`, so they include
smells past the per-kind cap; those and any past the budget are "not triaged". The verdict
counts confirmed smells only.

1. **Glance:** the verdict, the line
   "N candidates · C confirmed · D dismissed · U not triaged (budget)", a table of confirmed
   smells by kind × severity, the map path, and languages with no import rule.
2. **Confirmed smells**, ranked by severity then the map's order and numbered: the modules,
   the evidence (`file:line`), and a suggested next step (split a file, move an import
   behind an interface, delete it).
3. **Appendix:** every dismissal (kind, modules, reason, evidence), and per kind how many
   were not triaged.

```
## Audit: main @ 3f2a9c1

Verdict: 2 high-severity smells to look at first · UI smoke 5/6 pages clean
84 candidates · 21 confirmed · 39 dismissed · 24 not triaged (budget)
| kind     | high | medium | low |
|----------|------|--------|-----|
| layering | 2    | 0      | 0   |
| cochange | 0    | 6      | 4   |
| deadcode | 0    | 0      | 9   |
map: .foreman/reports/audit/20261027T091500Z/map.html
No import rule yet: .rb (14 files) — run setup to add one.
```

Then UI smoke findings, in the review's finding format
(`<root>/skills/review/references/report.md`).

Then tell the reader how to use the map:

- The package view is ordered by dependency: a package sits above the packages it
  imports, so normal imports flow down. Anything that flows up (a cycle or a forbidden
  crossing) is outlined and labelled.
- Dense repos open in the Matrix view (rows import columns); the Graph / Matrix switch
  toggles it.
- **Edges ▾ → Problems only** hides ordinary imports and leaves cycles and forbidden
  crossings.
- Select a package or module and press **N** for its neighbourhood: only what it imports
  and what imports it. Double-click or Enter opens a package.

End with "Not checked:" (for example: languages that need an import rule, pages left out
of the smoke pass, candidates past the budget).

## Clean up

Stop any server and its process tree, then `git worktree remove --force <temp>` (on
Windows, retry once after a few seconds if a file is locked). Remove temporary files.
