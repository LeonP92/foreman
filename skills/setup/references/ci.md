# Reading CI

CI is the one place that proves what a fresh checkout needs before its tests pass. Read
every workflow that runs the tests (`.github/workflows/*.yml` or the repo's equivalent),
including the `env:` blocks at workflow, job and step level.

## What to take

- **Steps before the tests.** Anything CI runs after installing and before testing (an
  asset build, code generation, compiling translations) goes into `[commands] build`,
  chained with `&&` in CI's order. Skip steps that only set up CI itself (checkout,
  caching, installing the language).
- **Plain `env:` values** (`APP_ENV: test`, `LOG_LEVEL: warning`) go into `[env]` as
  written. A value that names a database location becomes the per-server value instead
  (see "Databases" in the skill), never a copy of CI's.
- **Secret references** (`${{ secrets.SHOP_SECRET_KEY }}`) never carry a value. Write
  them as `${NAME}` in `[env]` and tell the user to export `NAME` in their shell.

Show the user each proposed value beside the workflow line it came from.

## Required secrets with no value

Some secrets only need to exist locally (a signing key, a session secret): any random value
works. When the app refuses to start without one and the user has none, offer a throwaway:

1. Pick a file outside the repo, for example `~/.config/foreman/<repo name>.env`.
2. Generate the values into it with the script below, saved outside the repo as
   `<temp>/throwaway.py`: `python3 -I <temp>/throwaway.py <file> SHOP_SECRET_KEY ...`.
   It creates the file readable by the user only (mode 0600), appends one line per name
   and prints the names, never the values.
3. Reference each one as `${NAME}` in `[env]`. Keep the file's path out of the config
   (it is a machine path): tell the user where it is; verify passes it to its launcher
   with `--env-file <file>`.

Never write a generated value into the config, the repo or the transcript, and never use
one for anything but a local copy of the app.

```python
import os, secrets, sys

# throwaway.py <file> NAME ...: append NAME=<random> lines to a user-only file.
path, *names = sys.argv[1:]
os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
os.chmod(path, 0o600)
with os.fdopen(fd, "a", encoding="utf-8") as f:
    f.writelines(f"{name}={secrets.token_urlsafe(32)}\n" for name in names)
print("\n".join(names))
```
