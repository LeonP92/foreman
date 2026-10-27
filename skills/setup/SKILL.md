---
name: setup
description: Learns how a repo is built, tested, served, logged into and seeded, and records it in .foreman/config.toml. Use on first use of foreman in a repo, when another foreman skill finds the config missing or invalid, or when the repo's commands have changed.
---

# Setup

Foreman knows nothing about a repo until this skill runs. It reads what the repo already
says about itself, asks the user only for what is missing, and writes
`.foreman/config.toml`. The schema is in `<root>/docs/config.md`; read it before drafting.

## Before you start

- Run foreman's scripts as `python3 -I <root>/scripts/run.py <command>` (`python` or `py` on
  Windows), where `<root>` is two directories above this file. Run them from the repo's top
  folder; every command prints JSON.
- Rules: never commit, push, or edit product code; never point anything at real data; pass
  credentials only through files or environment variables and never print them; clean up
  every worktree, server (whole process tree), and temp file you create. Never delete or
  modify anything you didn't create in this run — including ignored files and folders.
  End with "Not checked:" and why.

## 1. Read the repo, in this order

1. `AGENTS.md`, `CLAUDE.md`, then `README*` and `CONTRIBUTING*`, and any doc they point to
   for building, testing or architecture.
2. Manifests: `pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`, `Gemfile`,
   `pom.xml`, and the like.
3. Task runners: `Makefile`, `justfile`, npm scripts, wrapper scripts in `bin/` and
   `scripts/`.
4. CI workflows (`.github/workflows/*` or the repo's equivalent). CI shows the commands
   that really run.
5. `.env.example`-style files, to learn variable names. Never open `.env` or any file
   holding real secrets.
6. The default branch: `git symbolic-ref refs/remotes/origin/HEAD` (the part after
   `origin/`). If that fails, use the branch that CI runs on.

Prefer the command the repo already wraps (`make test`, `./run tests`) over the raw tool
it calls.

## 2. Draft the config

Fill each table from what you read:

- `[repo]` `base`, and `ignore` globs for generated or vendored code the file listing would
  otherwise pick up.
- `[commands]` install, lint, typecheck, test, e2e, and `test_targeted` with `{paths}` where
  the test runner accepts file paths. Leave a command empty when the repo has none.
- `[server]` the dev-server command with `{port}` in place of the port, a `ready_path` that
  answers once the app is up, and any `env` it needs (never secrets).
- `[login]` plain steps a browser can follow to sign in locally: a dev-login link, a seeded
  user, a test account. Name where a password comes from; never write the password.
- `[database]` see "Databases" below.
- `[rules]` the docs that state design rules, and `layers`: translate every layering rule
  the docs state ("the UI never imports the database layer") into
  `{from = "<glob>", to = "<glob>"}` pairs. Show the user each rule beside the sentence it
  came from. Add no rule the repo doesn't state.

### Databases

Foreman only ever runs servers against databases it copied or created.

- `kind = "file"` when the app uses a file inside the repo (SQLite and similar). `path` is
  that file, relative to the repo.
- `kind = "command"` when the app uses a database server. It needs `create` (a command that
  makes a new, empty database), `env_override` (the variable the app reads its database
  location from) and `url_template` (that variable's value). Write `{name}` where a
  database name goes (`createdb {name}`, `postgresql:///{name}`) or `{dir}` where a
  per-server folder goes (`sqlite:///{dir}/app.db`); foreman fills both in per server.
  Use it only if they really give each server its own database.
- `kind = "none"` when the app has no database.
- Add `migrate` and `seed` when the repo has them, and for `command` a `drop` that deletes
  a database `create` made (`dropdb {name}`).

If the database can't be isolated this way (a shared remote database, a hard-coded path
outside the repo), say so: verify will refuse to run until it can.

## 3. Ask, then write

Ask the user only for what you could not find, one question at a time, each with your best
guess. Then write `.foreman/config.toml` (without any `[graph.*]` rule yet) and run
`python3 -I <root>/scripts/run.py config-check`. Fix each problem it lists and re-run until
it reports `"ok": true`.

If `.foreman/reports/` isn't ignored yet, ask the user whether to add it to `.gitignore`
or, to keep it local, `.git/info/exclude`; change neither without a yes. Don't commit: the user decides whether to commit the config (committing
it lets teammates share it).

## 4. Languages without a built-in graph

Only once `config-check` passes, run `python3 -I <root>/scripts/run.py graph`. Python,
JavaScript/TypeScript and Go are built in. Each extension listed under `unsupported` needs
an import rule; write one at a time:

1. Read 3–5 files with that extension and note how they import each other.
2. Append `[graph.<language>]` to `.foreman/config.toml` with `extensions`, a `pattern`
   (regex; group 1 is the imported name) and `resolve` (candidate paths using `{dir}`,
   `{1}`, `{1|path}`).
3. Run `python3 -I <root>/scripts/run.py graph-rule-check --name <language>`. It reports how
   many imports matched and resolved, with examples that didn't. Adjust and re-run.
4. After 3 tries without a rule that resolves most imports, remove it and tell the user
   these files need an import rule; the map will list them under "No import rule yet".

Ignore extensions that aren't source code the repo owns (generated files, fixtures); add
them to `repo.ignore` instead. When every extension is done, run `config-check` once more
and fix anything it lists.

## When a config already exists

Re-read the same sources. Flag entries that look stale: a command or script that no longer
exists, a path that moved, a rule doc that is gone, a new language under `unsupported`.
Show each with what you found instead, and ask before changing anything.

## Finish

Tell the user what you found and where each value came from, what you guessed, and what
you asked. End with "Not checked:" (for example: commands you didn't run, login steps not
tried in a browser).
