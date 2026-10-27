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

Output: `<run>` (`map.html`, `map.json`, `audit.md`, and `smoke/` if you
run the UI pass).

## Steps

1. **Check out the base.** `git worktree add --detach <temp> <base>`, where `<base>` is
   `repo.base` and `<temp>` is a new folder under the system temp directory, outside the
   repo. Audit that, not the current checkout, so uncommitted work and the current
   branch don't leak in.
2. **Map it.** Run
   `python3 -I <root>/scripts/run.py map --root <temp> --config <repo>/.foreman/config.toml --out <run>`
   (both paths absolute). It prints the map path, group and module counts, the ranked
   smells, and `unsupported`: file extensions that need an import rule.
3. **Read the top smells.** For the highest-ranked ones, open the files named in the
   evidence and confirm the smell is real. Drop any that aren't (say why under
   "Not checked" or in a line below the list), and write a suggested next step for each
   one you keep. Thresholds are relative to this repo's own spread, not fixed numbers.
4. **UI smoke (optional).** If the repo has a UI and `[server]` is set, see below.
5. **Write the report** and remove the worktree.

## Smells the map finds

Cycles, layering breaks, hubs, hidden coupling, hotspots, oversized files, duplication and
possibly dead code. Each kind's rule, threshold and severity are in
[`docs/smells.md`](../../docs/smells.md).

## UI smoke

Only against the base server; there is no comparison. Follow the verify skill for data
(copies only, refuse if `[database]` can't isolate), preparing the worktree (copy, install,
build) and its environment, the server on a free port, login, and stopping the whole
process tree. Pick 3–8 main pages from the repo's routes (the router files, page folders
or URL config), one test each, titled by page (`cart`, `order-history`). For each page:
it loads, no console errors, no 4xx/5xx responses, and Tab moves a visible focus through
its controls. Run
`python3 -I <root>/scripts/run.py browser-run --spec <spec> --out <run>/smoke --base http://127.0.0.1:<port>`
with no `--branch`. Each problem is a finding with steps, expected, actual and screenshot.

## Report

Write `<run>/audit.md`, glance first:

```
## Audit: main @ 3f2a9c1

Verdict: 2 high-severity smells to look at first · 9 smells (2 high / 4 medium / 3 low:
3 cochange, 2 cycle, 2 oversize, 1 hub, 1 deadcode) · UI smoke 5/6 pages clean ·
map: .foreman/reports/audit/20261027T091500Z/map.html
No import rule yet: .rb (14 files) — run setup to add one.
```

Then the smells, ranked, numbered: kind and severity, the modules, the evidence, and a
suggested next step (split a file, merge two twins, move an import behind an interface,
confirm and delete). Then UI smoke findings, in the review's finding format
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
of the smoke pass, smells you didn't open).

## Clean up

Stop any server and its process tree, then `git worktree remove --force <temp>` (on
Windows, retry once after a few seconds if a file is locked). Remove temporary files.
