# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - Unreleased

### Added

- Skills: `setup` (writes `.foreman/config.toml` from the repo's docs, manifests and CI),
  `review` (pre-merge gate with one ranked report), `verify` (base and branch driven side by
  side in a real browser, on copied data only), `diagram` (change diagram) and `audit`
  (codebase map with triaged structural smells).
- CLI (`scripts/run.py`, Python 3.11+ standard library only): `config-check`, `graph`,
  `graph-rule-check`, `map`, `render`, `browser-run`, `db-copy`, and the environment
  helpers `launch`, `dotenv` and `throwaway`.
- Built-in import graphs for Python, JS/TS (including tsconfig/jsconfig path aliases) and
  Go; any other language through a repo rule `setup` writes and `graph-rule-check` accepts.
- Interactive diagram and dependency-ordered codebase map: graph and matrix views,
  neighbourhood view, filter, smells and forbidden layer crossings marked, light and dark
  themes, each a single self-contained HTML file.
- Audit smells: cycles, layering breaks, hubs, hidden coupling, hotspots, oversized files
  and functions, duplication and possibly dead code, with thresholds relative to the repo.

### Notes

- Commands never reach the real database: database-location variables are removed from
  every command's environment, and the config rejects one set without `{dir}` or `{name}`.
- Playwright is pinned and installed into a private cache; Node 20+ is needed only for
  `verify` and the audit's UI smoke pass.

### Known limits

- Templates and markup files aren't graphed: the diagram skill adds template nodes and
  their edges by hand, and the map leaves them out of the import graph.
- `verify` needs a runnable server: one the repo can start locally (`[server] start`).
- Only the root `go.mod` and the root `tsconfig.json` / `jsconfig.json` are read
  (no `extends`).
