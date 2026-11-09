# Triage checklist

Every smell `map` lists is a candidate. Work through `triage` item by item. Read the files
involved (and, for `cochange` and `hotspot`, the commits: `git log --format='%h %s' -- <file>`),
then go down this list. The first type that fits makes it DISMISSED. If none fits, the burden
of proof is still on the smell: CONFIRM only when you can state a concrete cost — who is hurt
and how (a change that must touch N places, a bug class, a layer rule the repo states).
Otherwise DISMISS it as "no checklist type fits, and no concrete cost found". No case, no
finding. Either way, write one line of reason and the evidence you read as `file:line` (or a
commit for history smells).

## Known false-positive types

1. **Sweep or format commits** (`cochange`, `hotspot`). The shared commits are renames,
   formatter runs, licence headers, dependency bumps or a version string touched everywhere,
   not one change that needed both files. Count the commits that are real edits; dismiss if
   fewer than the threshold remain.
2. **Generated or vendored code** (any kind). A "generated" / "do not edit" header, a
   generator's output folder, a copied third-party library. Dismiss, and suggest adding the
   folder to `repo.ignore`.
3. **Test helpers and fixtures** (`deadcode`, `duplicate`, `hub`). Shared test setup, factories,
   fixture data and snapshots under a support folder the test detection didn't catch. Test
   code repeats itself on purpose and is loaded by the runner.
4. **Definitions modules** (`hub`, `cochange`, `hotspot`). Constants, types, enums, error
   classes or settings that many modules import and that change with each feature that adds
   one: their churn is new values appended. That is their job; dismiss unless the module also
   holds logic.
5. **Public library API** (`deadcode`). A file the package's main file re-exports or requires,
   or the README documents: users outside the repo import it. Suggest adding it to
   `[audit] entry_points`.
6. **Loaded by path or reflection** (`deadcode`). A plugin folder scanned at start-up, a class
   named in a config string, a handler a task runner or CI config names, a dynamic import.
   Cite the loader line.
7. **Framework conventions** (`deadcode`, `duplicate`, `cochange`). Migrations, plugins,
   routes or commands registered by a decorator or config, files a framework picks up by
   their folder or name. Cite the convention or the registration.
8. **Intentional duplication** (`duplicate`). Versioned migrations or API versions kept side
   by side, per-locale or per-region files, a copy kept so two releases stay independent.
   Dismiss only when the copies must not change together.
9. **A file and its own test** (`cochange`). A source file and the test that exercises it
   (under a name or folder the test detection didn't catch) change together because tests
   follow code.
10. **Type-only hubs** (`hub`). Most of the hub's edges are type-only imports (annotations,
    interfaces, `import type`): nothing runs through it, so a change doesn't ripple at runtime.
11. **Sibling implementations** (`cochange`). Two implementations of one interface or base
    class (two storage backends, two payment providers) change together when the interface
    does. Confirm only if they also share logic that should live in the base.
12. **Composition roots** (`hub`). Pages, route tables, app factories, DI or plugin
    registration: wiring everything together is their job. Dismiss unless they also hold
    logic.

## Kinds that are rarely false

`cycle` and `layering` come straight from the import graph and the team's own rules. Dismiss
one only when the import is type-only, behind a guard that never runs at import, or the rule
names an exception the config missed (then suggest the `except` glob).

## Examples (invented)

- DISMISSED · cochange `src/orders.py` + `src/invoices.py` — 6 of 7 shared commits are a
  formatter run and a rename (`a1b2c3d`, `d4e5f6a`); one real edit is below the threshold.
- DISMISSED · deadcode `plugins/export_csv.py` — loaded by name from `PLUGINS` in
  `app/settings.py:42`.
- CONFIRMED · hub `src/checkout/service.py` — imports 14 modules and holds pricing, stock and
  payment logic (`src/checkout/service.py:30-210`); split by concern.
