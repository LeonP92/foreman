---
name: diagram
description: Draws an interactive dependency diagram of the modules a branch changes and their direct neighbours, with forbidden layer crossings and structural smells marked. Use when asked to diagram, map or visualise a change, or as part of a foreman review.
---

# Diagram

The diagram is a fixed HTML template filled from one JSON file. You write only the data;
`render` validates it and writes the HTML. Never write or edit the HTML yourself.

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

Output: `.foreman/reports/<branch>/diagram/data.json` and `diagram.html`, where `<branch>`
has each `/` replaced by `-`.

## Steps

1. **Changed files.** The branch is the one the user named, else the current one; the base
   is `BASE = git merge-base <repo.base> <branch>`, never the tip of `repo.base` (if
   `BASE` equals the branch tip: nothing to review, or already merged and `BASE^` is the
   base, as the review skill decides). List files with `git diff --name-only BASE
   <branch>`. If the branch isn't checked out, add a temporary worktree (`git worktree add --detach <temp> <branch>`,
   with `<temp>` under the system temp directory, outside the repo) rather than switching
   branches.
2. **Import edges, from the code.** Run
   `python3 -I <root>/scripts/run.py graph --files <changed files>` (for a worktree add
   `--root <worktree> --config <repo>/.foreman/config.toml`). It returns the changed files
   plus everything one import away, the edges between them, cycles through them, and
   `unsupported` extensions. Never add an import edge from memory.
   - Check `missing`: paths it couldn't find. Deleted or ignored files belong there;
     anything else is a typo or several paths passed as one argument (pass each
     separately). Fix and re-run until only those are left.
   - Run the same command on a worktree at `BASE`. A cycle in both is pre-existing; say
     so in `notes`. Say in `notes` which cycles are type-only (`type_only` edges).
   - Files of a language with no import rule: read their imports directly and say so in
     `notes` ("`.rb` imports read by hand; needs an import rule — setup writes one").
3. **Call and implements edges, from reading the diff.** `call` for who calls or renders
   the new or changed code, `impl` for subclassing or satisfying an interface. Templates,
   prompts and config are nodes too; connect them with `call` edges labelled by the
   relation (`renders`, `loads`).
4. **Forbidden edges.** An edge is `forbidden` only when it matches a pair in the repo's
   `[rules] layers` and its target isn't in that pair's `except`. Name the rule and the doc it comes from in `notes`. No rule, no
   forbidden edge.
5. **Nodes.** Every changed module, class or interface, plus unchanged ones exactly one hop
   from a changed node. Drop everything else, including tests. Every node needs an edge.
6. **Smells.** See below.
7. **Render.** Write `data.json`, then run
   `python3 -I <root>/scripts/run.py render <dir>/data.json <dir>/diagram.html`. It lists
   every problem at once; fix them all and re-run until it prints the path.
8. **Check it.** If a browser is available, open the file, click a changed node and confirm
   its summary shows; click a smell and confirm its nodes light up. Report the path.

Remove any worktree you added.

## The data file

```json
{
  "title": "`feature/coupon-limits` vs `main`",
  "notes": "Import edges from foreman graph. Cycle cart ↔ pricing exists on main too.",
  "lanes": ["checkout", "billing", "unchanged · one hop"],
  "nodes": [
    {"id": "checkout/coupons.py", "label": "checkout/coupons.py", "sub": "apply_coupon",
     "lane": "checkout", "status": "changed",
     "summary": {"changed": [{"old": "apply_coupon(cart, code) -> Cart",
                              "new": "apply_coupon(cart, code, *, now: datetime) -> Cart"}]}},
    {"id": "billing/limits.py", "label": "billing/limits.py", "sub": "NEW",
     "lane": "billing", "status": "added",
     "summary": {"added": ["`uses_left(coupon: Coupon) -> int`"]}},
    {"id": "checkout/cart.py", "label": "checkout/cart.py", "lane": "unchanged · one hop",
     "status": "affected", "summary": {"affected": ["calls `apply_coupon` with `now`"]}}
  ],
  "edges": [
    {"from": "checkout/coupons.py", "to": "billing/limits.py", "kind": "import"},
    {"from": "checkout/cart.py", "to": "checkout/coupons.py", "kind": "call",
     "label": "apply_coupon"}
  ],
  "smells": []
}
```

| Field | Values |
|---|---|
| `status` | `added`, `changed`, `removed`, `affected` (unchanged, one hop from a changed node) |
| `summary` | keys `added`, `removed`, `changed`, `affected`; each a list of strings (backticks become code) or `{"old", "new", "note"?}` pairs. Required unless `affected`. |
| edge `kind` | `import`, `call`, `impl`, `cycle`, `forbidden` |
| `lane` | must be listed in `lanes`; every lane needs a node |

Use the graph's file paths as node ids. A cycle's edges are `cycle` instead of `import`,
not both. Summaries hold full signatures copied from the code: every parameter and the
return type, never `...`, never bodies, never HTML. If an edge lands on a package's
`__init__` file that only re-exports a name, point it at the module that defines it.

## Smells

Smells are structural problems you can only see as a graph. Walk the graph once per kind.
Each smell has `kind`, `severity`, `nodes`, `title`, `evidence`, and an optional
`suggestion`. No concrete evidence (names, counts, the test that does or doesn't guard
it), no smell; an empty list is a fine answer.

| `kind` | Nodes | Use when | Evidence must say |
|---|---|---|---|
| `scatter` | 3 or more | One concept (a field, a rule, a flag) had to change in many modules. | which concept, and whether the spread is inherent or avoidable |
| `twin` | exactly 2 | Two implementations of one rule must change together (server and client validation, code and a SQL filter). | both implementations, and whether a parity test guards them |
| `hub` | exactly 1 | A changed node with many neighbours; `render` requires 5 or more in the graph. | the neighbour count and why it matters here |

Severity: `high` when it already caused or will likely cause a bug (twins with no parity
test, a hub crossing layers); `medium` when the next change here will pay for it; `low`
when inherent or already guarded.

Cycles and forbidden crossings are edges, not smells. Line-level problems (a bug, a stale
comment, naming) belong in the review report, never on the diagram.

## Finish

Report the diagram path and a one-line count of nodes, edges and smells. End with
"Not checked:" (for example: files read by hand instead of graphed, call edges inferred
from the diff only).
