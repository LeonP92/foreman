<img src=".claude-plugin/icon.png" alt="" width="72">

# foreman

![CI](https://github.com/LeonP92/foreman/actions/workflows/ci.yml/badge.svg)

Human-on-the-loop review for AI coding agents: hard-tests every change and maps architecture and code smells at a glance.

Agents write more code than a person can read line by line. foreman keeps you on the loop
without that: evidence (the repo's tests, plus, for user-facing changes, the app driven in a
real browser on the base branch and on your change), the design at a glance (a one-page
overview of each reviewed change, its dependency diagram, and a codebase map with smells
marked), and a short ranked list of what needs your judgement.

![A review's Overview view: summary, network view and sequence view of a change](docs/overview.png)

![The same page's Graph view: a dependency diagram with a node focused and its details open](docs/diagram.png)

![A dependency-ordered codebase map with a forbidden crossing and a cycle highlighted](docs/map.png)

## Install

Claude Code:

```
/plugin marketplace add LeonP92/foreman
/plugin install foreman@foreman
```

Codex:

```
codex plugin marketplace add LeonP92/foreman
codex plugin add foreman@foreman
```

## Commands

| Command | What it does |
|---|---|
| `/foreman:setup` | Learns how the repo is built, tested, served and seeded; writes `.foreman/config.toml`. |
| `/foreman:review` | Pre-merge gate for a branch: design findings, tests, browser check for user-facing changes, one ranked report, and a diagram page that opens on a design overview. |
| `/foreman:verify` | Drives the app in a real browser on base and change side by side, on copied data only. |
| `/foreman:diagram` | Interactive dependency diagram of the modules a branch changes and their neighbours. |
| `/foreman:audit` | Sweeps the base branch for structural smells and draws a dependency-ordered codebase map. |

A review writes into `.foreman/reports/<branch>/<stamp>/`: `review.md` (the ranked report),
`diagram/diagram.html` and, when the change is user-facing, `verify/`. The diagram page opens
on an **Overview** of the design (summary, network and sequence views when they apply, key
decisions, what changed and known limits), with **Graph** and **Matrix** one click away. It is
a single self-contained HTML file (the first two screenshots above).

Config reference: [docs/config.md](docs/config.md). Smell catalogue: [docs/smells.md](docs/smells.md).

## Requirements

Python 3.11+ and git. Node 20+ only for `verify` and the UI smoke pass.

## Languages

Python, JS/TS and Go are graphed out of the box. Any other language gets an import rule
that `setup` writes after reading a few of your files.

## License

[MIT](LICENSE). Inspired by [ponytail](https://github.com/DietrichGebert/ponytail) (MIT); credit for ideas only.
