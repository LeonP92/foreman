# Starting and stopping servers

A dev server usually starts children (a bundler, a reloader, workers). Stopping only the
process you launched leaves them running and holding the port or the worktree's files.
Start each server as the leader of a new process group, then stop the whole group.

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
   and the like) may be read only through the names-only helper `dotenv.py` below, never
   opened or printed otherwise; if the host blocks reading one, ask the user which
   variable names it sets. List the names each copy sets
   with `python3 -I <temp>/dotenv.py <worktree>/<file>` (names only, never values). For
   every database-location name in that list, rewrite its line in the worktree's copy to
   this server's value: `python3 -I <temp>/dotenv.py <worktree>/<file> NAME=<value>`. If
   the config gives no value for it (neither `[env]` nor `env_override` sets it), stop
   and say which file sets which name: the copy must decide, not the framework's
   precedence rules.
3. Run `[commands] install`, then `[commands] build`, through the launcher below.

```python
import re, sys

# dotenv.py <file>: the names it sets. dotenv.py <file> NAME=value ...: rewrite those lines.
LINE = re.compile(r"^(export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=[^\r\n]*", re.M)
path, *pairs = sys.argv[1:]
text = open(path, encoding="utf-8", newline="").read()
if not pairs:
    print("\n".join(sorted({m[2] for m in LINE.finditer(text)})))
else:
    values = dict(pair.split("=", 1) for pair in pairs)
    text = LINE.sub(
        lambda m: f"{m[1] or ''}{m[2]}={values[m[2]]}" if m[2] in values else m[0], text
    )
    open(path, "w", encoding="utf-8", newline="").write(text)
```

## The environment every command gets

Every command foreman runs in a worktree (`install`, `build`, tests, `create`, `migrate`,
`seed`, `drop`, `start`) goes through the launcher, which builds its environment:

1. Start from the agent's environment.
2. Remove every variable that names a database location: `DATABASE_URL`,
   `DATABASE_PATH`, `DB_URL`, `DB_PATH`, `env_override`, and any other that
   `.env.example`, `[env]`, `[server] env` or the repo's docs name as one.
3. Apply `[env]`; for the server also `[server] env` on top; then, for `command`
   databases, `env_override` set to this server's filled-in `url_template`.

Fill in `{port}`, `{url}` (`http://127.0.0.1:{port}`), `{dir}` and `{name}` yourself. Leave
`${NAME}` as written: the launcher reads it from the environment left after step 2 as the
command starts, so secret values never land in a file or the transcript, and a reference
to a removed database variable fails instead of reaching the real database.

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

Put `--env-file <path>` (repeatable) before `<settings>` to load a file of `NAME=value`
lines, such as the throwaway secrets file setup made outside the repo, into the
environment before `${NAME}` is filled in. It never prints values, and a file that sets
a removed database location is rejected with a one-line error naming the variable.

```python
import json, os, re, subprocess, sys

args, env_files = sys.argv[1:], []
while args[0] == "--env-file":
    env_files.append(args[1])
    args = args[2:]
SETTINGS, CWD, LOG, COMMAND = args
settings = json.load(open(SETTINGS, encoding="utf-8"))
values = settings["command" if LOG == "-" else "server"]
base = {k: v for k, v in os.environ.items() if k not in settings["remove"]}
for path in env_files:
    text = open(path, encoding="utf-8").read()
    for name, value in re.findall(r"^(?:export\s+)?([A-Za-z_]\w*)=([^\r\n]*)", text, re.M):
        if name in settings["remove"]:
            sys.exit(f"launch: {path} sets {name}, a removed database location")
        base[name] = value


def lookup(m):
    if m[1] not in base:
        sys.exit(f"launch: ${{{m[1]}}} is not set, or names a removed database location")
    return base[m[1]]


env = {**base, **{key: re.sub(r"\$\{(\w+)\}", lookup, value) for key, value in values.items()}}

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
`${NAME}` isn't set, the launcher stops with a one-line message naming it; ask the user
to export it or name the env file holding it rather than inventing a value.

## Stopping

- POSIX: `python3 -I -c "import os, signal; os.killpg(<pid>, signal.SIGTERM)"`. The PID
  is the group's ID because the server leads its own session. If the port still answers
  after 5 seconds, repeat with `signal.SIGKILL`.
- Windows: `taskkill /T /F /PID <pid>` stops the process and everything it started.

Confirm the port no longer answers, then `git worktree remove --force <worktree>`; on
Windows, if a file is still locked, wait a few seconds and retry once.
