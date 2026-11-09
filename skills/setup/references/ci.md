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

1. The file lives at a stable private path outside the repo and outside any run's temp
   folder, reused across runs: `<user config dir>/foreman/secrets/<repo name>-<8 hex>.env`,
   where the user config dir is `%APPDATA%` on Windows, else `$XDG_CONFIG_HOME` or
   `~/.config`, and the 8 hex are the start of the SHA-256 of the repo's absolute path.
2. Run `python3 -I <root>/scripts/run.py throwaway <repo> SHOP_SECRET_KEY ...`. It
   creates the file only if it is missing, readable by the user only (mode 0600), appends a
   line only for each name it doesn't hold yet, and prints the file's `path` and the names
   it `added`, never the values. With no names it only prints the path. Runs in parallel are
   safe: each holds a lock file next to it while adding names, so no name is added twice.
   The file is shared by every run on this repo and never removed by cleanup.
3. Reference each one as `${NAME}` in `[env]`. Keep the file's path out of the config (it
   is a machine path): tell the user where it is; verify passes it to its launcher with
   `--env-file <file>`.

Never write a generated value into the config, the repo or the transcript, and never use
one for anything but a local copy of the app.
