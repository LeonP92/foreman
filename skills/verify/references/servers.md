# Starting and stopping servers

A dev server usually starts children (a bundler, a reloader, workers). Stopping only the
process you launched leaves them running and holding the port or the worktree's files.
Start each server as the leader of a new process group, then stop the whole group.

## The environment every command gets

Build one environment per server and pass it explicitly to every command foreman runs for
that server (`install`, `create`, `migrate`, `seed`, `start`):

1. Start from the current environment.
2. Remove every variable that `.env.example`, `[server] env` or the repo's docs name as a
   database location (`DATABASE_URL`, `DB_PATH`, and the like), and `env_override`.
3. Add `[server] env`, and for `command` databases set `env_override` to this server's
   filled-in `url_template`.

That way a variable left in your shell can't point a server at the real database.

## Launcher

Save this outside the repo (for example `<temp>/launch.py`), fill in the four values, and
run it with `python3 -I` once per server. It prints the server's PID and returns while the
server keeps running.

```python
import json, os, subprocess

CWD = "<worktree>"
COMMAND = "<[server] start with {port} filled in>"
LOG = "<temp>/base-server.log"
ENV = json.load(open("<temp>/base-env.json", encoding="utf-8"))  # the environment above

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
    env=ENV,
    stdout=log,
    stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL,
    **group,
)
print(proc.pid)
```

`shell=True` is deliberate: `[server] start` is a shell command written by the repo. Write
the environment file with permissions only you can read if it holds credentials, and
delete it when you clean up.

## Stopping

- POSIX: `python3 -I -c "import os, signal; os.killpg(<pid>, signal.SIGTERM)"`. The PID
  is the group's ID because the server leads its own session. If the port still answers
  after 5 seconds, repeat with `signal.SIGKILL`.
- Windows: `taskkill /T /F /PID <pid>` stops the process and everything it started.

Confirm the port no longer answers before removing the worktree.
