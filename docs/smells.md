# Smells

foreman reports two families. Diagram smells are judged by the agent for one change and
must carry evidence. Audit smells are computed by `python3 scripts/run.py map` from the
import graph, git history, file sizes and duplicate scan. Audit thresholds are relative to
the repo's own spread (percentiles) with a fixed floor, so a small repo isn't flagged for
being small. Each audit kind except `cycle` and `layering` lists at most 20 smells, ranked by
severity then size; `map` reports how many more each kind had under `dropped`, and `counts`
gives every smell by kind and severity. Test files (the paths `cochange` treats as tests,
below) are never `hub`, `hotspot`, `oversize` or `duplicate` smells and don't count as hub
neighbours. Files with a config, data or infra extension (`.tf`, `.tfvars`, `.yml`, `.json`
and the like) are never in any smell, even when a `[graph.*]` rule covers them.

## Diagram smells

Severity is the agent's call: `high` when it already caused or will likely cause a bug,
`medium` when the next change here pays for it, `low` when inherent or already guarded.

**scatter** — one concept (a field, a rule, a flag) had to change in 3 or more modules.
Spread like this is where a change silently misses a spot.

**twin** — exactly 2 implementations of one rule that must change together, such as server
and client validation. Twins drift; the evidence says whether a parity test guards them.

**hub** — one changed node with at least 5 neighbours (`HUB_MIN_NEIGHBOURS`) in the graph;
`render` rejects fewer. Diagram `hub` is measured within the change; audit `hub` below is
measured against the whole repo, so the two can disagree.

## Audit smells

**cycle** — modules that import each other at runtime. Severity `high` when the loop spans
two or more top-level directories, otherwise `medium`. Cycles make modules impossible to
test, load or change alone.

**layering** — an import that a `[rules] layers` pair forbids (for example `src/ui/**`
importing `src/db/**`), unless its target matches the pair's `except` globs. Always
`high`: it breaks a boundary the team chose.

**hub** — a module that imports at least `max(hub_fanout_floor = 5, repo p95)` others and
whose neighbours (importers plus imports) number at least `max(hub_floor = 8, repo p95)`,
counting non-test modules only. A module many import that depends on little (a stable
definitions module) is never a hub. `medium`, or `low` for an entry point (see deadcode).
`conftest.py` and a package `__init__.py` that only re-exports (imports, `__all__`) are never
hubs. A change to a hub reaches everything around it, so it is the riskiest place to edit.

**cochange** — two files that changed in the same commits but don't import each other:
hidden coupling. Needs at least `cochange_min_both = 5` shared commits and confidence of at
least `cochange_min_conf = 0.6`; `medium` from `cochange_medium_conf = 0.8`, else `low`. A
test and the file it tests (`tests/…/test_x.py`, `x_test.go`, `x.test.ts`, `x.spec.ts`,
`__tests__/x.ts` against `x.<ext>` anywhere) are ignored, and so are two tests. Only source
files take part: config and infra files (`.yml`, `.tf`) don't. A Python import through a
package that re-exports a name counts as importing the submodule it comes from. A commit
touching more files than the larger of `bulk_commit_min_files = 10` and
`bulk_commit_share = 0.2` of the repo's source files (a format or rename sweep) counts for
neither `cochange` nor `hotspot`.

**hotspot** — a large file that changes often. Changed in at least
`max(hotspot_min_churn = 5, repo p90)` commits and at least the repo's p75 in lines. Always
`medium`. Files that are both big and busy hold most of a repo's defects.

**oversize** — a file or function far above the repo's norm, always `low`. A file must exceed
the repo p95 and be at least `oversize_file_median_ratio = 3` times the median and at least
`oversize_file_floor = 300` lines. A function must exceed the repo p95 and be at least
`oversize_function_floor = 60` lines (function sizes are measured for Python only).

**duplicate** — near-identical blocks of at least `duplicate_min_lines = 12` lines (blank and
comment lines don't count) in different places. All blocks shared by the same files are one
smell, sized by their total lines. `medium` when that total is at least
`duplicate_medium_lines = 20` lines or a block is repeated in at least
`duplicate_medium_locations = 3` places, else `low`. Duplicates get fixed in one copy and not
the others.

**deadcode** — a module nothing imports that isn't a test, a known entry point (manifest
scripts, `main`, `cli`, a shebang, an `if __name__ == "__main__"` block, `package main`), a
file a framework loads by path (migrations, `[audit] entry_points`) or a config file, and
whose name (`widget.js` or `widget`) appears in no other tracked file: a template's
`<script src>`, a config, a manifest or a doc that names it counts as a user. Always `low`,
and only a candidate: dynamic loading can hide its users.

## Known limits

Templates and markup files aren't part of the import graph in v0.1, so a template that
only gets rendered can't take part in `cycle`, `layering`, `hub` or `deadcode`. The
diagram skill adds template nodes by hand; full template graphing is planned.
