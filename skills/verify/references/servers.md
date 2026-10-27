# Starting and stopping servers

A dev server usually starts children (a bundler, a reloader, workers). Stopping only the
process you launched leaves them running and holding the port or the worktree's files.
Start each server as the leader of a new process group, then stop the whole group.

## Helper commands

`launch`, `dotenv` and `throwaway` are foreman commands
(`python3 -I <root>/scripts/run.py <command>`), so nothing is saved next to the app;
`launch` runs each command with cwd = the worktree it is given.

## Per-server values

Before a side's first command, pick its values: a free port (bind a socket to port 0 and
read it back), a fresh `{name}` (`foreman_<base|branch>_<6 lowercase hex>`, letters,
digits and underscores only) and a fresh empty `{dir}` folder under `<temp>`. Do this for
every server whatever the database kind, so `[env]` placeholders always resolve.

## Preparing a worktree

In each worktree foreman makes, before running anything:

1. Copy each `[repo] copy` file that exists in the repo's checkout to the same path in the
   worktree, as a plain file copy. Never print, quote or summarise its contents; note any
   that are missing.
2. A copied file may point the app at the real database. Env files (`.env`, `.env.local`
   and the like) may be read only through the names-only `run.py dotenv`, never
   opened or printed otherwise; if the host blocks reading one, ask the user which
   variable names it sets. List the names each copy sets
   with `python3 -I <root>/scripts/run.py dotenv <worktree>/<file>` (`names`, and the common
   `database_locations` among them; never values). For every database-location name in
   that list (plus `env_override` and any other the repo names as one), rewrite its line in
   the worktree's copy to this server's value:
   `python3 -I <root>/scripts/run.py dotenv <worktree>/<file> NAME=<value>`. If
   the config gives no value for it (neither `[env]` nor `env_override` sets it), stop
   and say which file sets which name: the copy must decide, not the framework's
   precedence rules.
3. Run `[commands] install`, then `[commands] build`, through the launcher below.

## The environment every command gets

Every command foreman runs in a worktree (`install`, `build`, tests, `create`, `migrate`,
`seed`, `drop`, `start`) goes through the launcher, which builds its environment:

1. Start from the agent's environment, without the variables that point into the main
   checkout (the repo foreman was started in): `VIRTUAL_ENV`, `PYTHONPATH`, `NODE_PATH`,
   and any whose value is a path inside it; `PATH` keeps its other entries. Otherwise
   a worktree's commands run the main checkout's code or packages.
2. Remove every variable that names a database location: `DATABASE_URL`,
   `DATABASE_PATH`, `DB_URL` and `DB_PATH` always, plus the settings' `remove` list:
   `env_override` and any other that `.env.example`, `[env]`, `[server] env` or the repo's
   docs name as one.
3. Apply `[env]`; for the server also `[server] env` on top; then, whenever
   `env_override` is set (always for `command`, optionally for `file`), that variable
   set to this server's filled-in `url_template`, so `migrate`, `seed` and `start` reach
   the copy.

Fill in `{port}`, `{url}` (`http://127.0.0.1:{port}`), `{dir}` and `{name}` yourself. Leave
`${NAME}` as written: the launcher reads it from the environment left after step 2 as the
command starts, so secret values never land in a file or the transcript, and a reference
to a removed database variable fails instead of reaching the real database.

Write the settings for each side to `<temp>/<side>-env.json`, with `checkout` the main
checkout's absolute path:

```json
{"remove": ["SHOP_DB"], "checkout": "/home/me/shop",
 "command": {"SHOP_DB": "sqlite:////tmp/fm-1/app.db", "SECRET_KEY": "${SHOP_SECRET_KEY}"},
 "server": {"SHOP_DB": "sqlite:////tmp/fm-1/app.db", "SECRET_KEY": "${SHOP_SECRET_KEY}",
            "APP_URL": "http://127.0.0.1:50123"}}
```

## Launcher

Run a command and wait for it with
`python3 -I <root>/scripts/run.py launch <settings> <worktree> - "<command>"`; it prints the
command's output, then `{"returncode": N}`, and exits with the command's status. Start a
server with a log file instead of `-`, and `[server] start` with `{port}` filled in: it
prints `{"pid": N}` and returns while the server keeps running in its own process group,
so the whole tree can be stopped later.

Put `--env-file <path>` (repeatable) before `<settings>` to load a file of unquoted
`NAME=value` lines (an optional `export ` prefix; quotes are kept as part of the value), such
as the throwaway secrets file setup made outside the repo, into the environment before
`${NAME}` is filled in. It never prints values, and a file that sets
a removed database location is rejected with a one-line error naming the variable.

The commands are shell commands written by the repo, so the launcher runs them through
the shell. If a `${NAME}` isn't set, it stops with a one-line message naming it; ask the
user to export it or name the env file holding it rather than inventing a value.

## Stopping

- POSIX: `python3 -I -c "import os, signal; os.killpg(<pid>, signal.SIGTERM)"`. The PID
  is the group's ID because the server leads its own session. If the port still answers
  after 5 seconds, repeat with `signal.SIGKILL`.
- Windows: `taskkill /T /F /PID <pid>` stops the process and everything it started.

Confirm the port no longer answers, then `git worktree remove --force <worktree>`; on
Windows, if a file is still locked, wait a few seconds and retry once.
