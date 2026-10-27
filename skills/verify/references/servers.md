# Starting and stopping servers

A dev server usually starts children (a bundler, a reloader, workers). Stopping only the
process you launched leaves them running and holding the port or the worktree's files.
Start each server as the leader of a new process group, then stop the whole group.

## Preparing a worktree

In each worktree foreman makes, before running anything:

1. Copy each `[repo] copy` file that exists in the repo's checkout to the same path in the
   worktree, as a plain file copy. Never print, quote or summarise its contents; note any
   that are missing.
2. Run `[commands] install`, then `[commands] build`, through the launcher below.

## The environment every command gets

Every command foreman runs in a worktree (`install`, `build`, tests, `create`, `migrate`,
`seed`, `drop`, `start`) goes through the launcher, which builds its environment:

1. Start from the agent's environment.
2. Remove every variable that `.env.example`, `[env]`, `[server] env` or the repo's docs
   name as a database location (`DATABASE_URL`, `DB_PATH`, and the like), and
   `env_override`.
3. Apply `[env]`; for the server also `[server] env` on top; then, for `command`
   databases, `env_override` set to this server's filled-in `url_template`.

Fill in `{port}`, `{url}` (`http://127.0.0.1:{port}`), `{dir}` and `{name}` yourself; pick
each server's port before its first command. Leave `${NAME}` as written: the launcher
reads it from its own environment as the command starts, so secret values never land in
a file or the transcript. A variable left in your shell can't point anything at the real
database, and a copied `.env` loses to the explicit environment in most frameworks, so
make sure `[env]` or `env_override` sets every database-location variable the app reads.

Write the settings for each side to `<temp>/<side>-env.json`:

```json
{"remove": ["DATABASE_URL"],
 "command": {"DATABASE_URL": "sqlite:///data/app.db", "SECRET_KEY": "${SHOP_SECRET_KEY}"},
 "server": {"DATABASE_URL": "sqlite:///data/app.db", "SECRET_KEY": "${SHOP_SECRET_KEY}",
            "APP_URL": "http://127.0.0.1:50123"}}
```

## Launcher

Save this outside the repo (for example `<temp>/launch.py`). Run a command and wait for
it with `python3 -I <temp>/launch.py <settings> <worktree> - "<command>"`; it exits with
the command's status. Start a server with a log file instead of `-`, and `[server] start`
with `{port}` filled in: it prints the server's PID and returns while the server keeps
running in its own process group, so the whole tree can be stopped later.

```python
import json, os, re, subprocess, sys

SETTINGS, CWD, LOG, COMMAND = sys.argv[1:5]
settings = json.load(open(SETTINGS, encoding="utf-8"))
values = settings["command" if LOG == "-" else "server"]
env = {k: v for k, v in os.environ.items() if k not in settings["remove"]}
for key, value in values.items():
    env[key] = re.sub(r"\$\{(\w+)\}", lambda m: os.environ[m[1]], value)

if LOG == "-":
    sys.exit(subprocess.run(COMMAND, shell=True, cwd=CWD, env=env).returncode)
group = (
    {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    if os.name == "nt"
    else {"start_new_session": True}
)
log = open(LOG, "w", encoding="utf-8")
proc = subprocess.Popen(
    COMMAND,
    shell=True,
    cwd=CWD,
    env=env,
    stdout=log,
    stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL,
    **group,
)
print(proc.pid)
```

`shell=True` is deliberate: the commands are shell commands written by the repo. If a
`${NAME}` isn't set, the launcher stops with a `KeyError` naming it; ask the user to
export it rather than inventing a value.

## Stopping

- POSIX: `python3 -I -c "import os, signal; os.killpg(<pid>, signal.SIGTERM)"`. The PID
  is the group's ID because the server leads its own session. If the port still answers
  after 5 seconds, repeat with `signal.SIGKILL`.
- Windows: `taskkill /T /F /PID <pid>` stops the process and everything it started.

Confirm the port no longer answers, then `git worktree remove --force <worktree>`; on
Windows, if a file is still locked, wait a few seconds and retry once.
