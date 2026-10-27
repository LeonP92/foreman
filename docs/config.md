# Config

`.foreman/config.toml`, written by `setup`, read by every other skill. Check it with
`python3 scripts/run.py config-check` (exit 1 and a list of problems when invalid; a missing file
is fine and means defaults). Unknown tables and keys are errors.

## Keys

| Key | Meaning |
|---|---|
| `repo.base` | Branch to diff against. Default `"main"`. |
| `repo.ignore` | Globs left out of every graph and report. |
| `repo.copy` | Ignored files (`.env`, local settings) copied from your checkout into each worktree foreman makes. Never printed. |
| `commands.install` / `lint` / `typecheck` / `test` / `e2e` | Shell commands; empty means skip. |
| `commands.build` | Runs after `install` in each worktree: whatever a fresh checkout needs before it runs (an asset build). |
| `commands.test_targeted` | Test command for a subset; `{paths}` is replaced by the test files. |
| `server.start` | Command that starts the app; must contain `{port}`. |
| `server.ready_path` | URL path polled until the server answers. Default `"/"`. |
| `env` | Environment variables for every command foreman runs in a worktree (`install`, `build`, tests, database commands, the server), as a table. |
| `server.env` | Extra environment variables for the server only, applied on top of `env`. |
| `login.steps` | Plain-language instructions for the agent to sign in. |
| `database.kind` | `"none"`, `"file"` or `"command"`. Default `"none"`. |
| `database.path` | The database file. Required for `file`. |
| `database.create` | Command that creates a database. Required for `command`. |
| `database.migrate` / `seed` | Optional commands, either kind. |
| `database.drop` | Optional command that deletes a database `create` made (`command` kind). Only ever run on databases foreman created. |
| `database.env_override` | Env var that points the server at its database. Required for `command`. |
| `database.url_template` | Value for that env var. Required for `command`. |
| `rules.docs` | Repo docs that state design rules. |
| `rules.layers` | Edges that must not exist: `[{from = "glob", to = "glob"}]`. An optional `except = ["glob", …]` lists targets under `to` that `from` may still import. |
| `graph.<name>` | Import rule for a language without a built-in graph (needs an import rule; setup writes one): `extensions`, `pattern` (regex, group 1 is the import), `resolve` (candidate paths using `{dir}`, `{1}`, `{1\|path}`). |

`create`, `migrate`, `seed`, `drop` and `url_template` may use two placeholders, filled in
per server (every server gets both, whatever the database kind):

- `{dir}`: the server's own directory, for file paths (`sqlite:///{dir}/app.db`). Unrelated to `{dir}` in `[graph.*] resolve`, which is the importing file's folder.
- `{name}`: a unique database name, `foreman_<base|branch>_<6 lowercase hex>` (letters,
  digits and underscores only), for database servers (`postgresql:///{name}`).

## Environment

Foreman starts each command from your environment, removes every variable that names a
database location, then applies `[env]`, then `[server] env` (server only), then the
per-server database variable. Values in `[env]` and `[server] env` may use:

- `{port}`: the server's port; `{url}`: `http://127.0.0.1:{port}`, for apps that need
  to know their own address.
- `{dir}` and `{name}`, as above.
- `${NAME}`: the value of `NAME` in the environment foreman runs in, read when the
  command starts; foreman never prints or stores it. Never put a secret's value in the
  config: export it in your shell and reference it as `${NAME}`. A reference to a
  database location (`DATABASE_URL`, `DATABASE_PATH`, `DB_URL`, `DB_PATH` or
  `env_override`) is an error: those are removed so commands only reach their own copy.

## Example: web app with a file database

```toml
[repo]
base = "main"
ignore = ["dist/**"]
copy = [".env"]

[commands]
install = "npm ci"
build = "npm run build:css"
lint = "npm run lint"
test = "npm test"
test_targeted = "npm test -- {paths}"

[env]
DATABASE_URL = "sqlite:///data/app.db"
SECRET_KEY = "${SHOP_SECRET_KEY}"

[server]
start = "npm run dev -- --port {port}"
ready_path = "/health"
env = { APP_ENV = "test", APP_URL = "{url}" }

[login]
steps = "Open /login, sign in as demo@example.com with the password from the seed output."

[database]
kind = "file"
path = "data/app.db"
migrate = "npm run migrate"
seed = "npm run seed"

[rules]
docs = ["docs/architecture.md"]
layers = [{ from = "src/ui/**", to = "src/db/**", except = ["src/db/types.ts"] }]
```

## Example: app with a server database

```toml
[commands]
install = "uv sync"
lint = "uv run ruff check"
test = "uv run pytest"

[server]
start = "uv run uvicorn app.main:app --port {port}"

[database]
kind = "command"
create = "createdb {name}"
migrate = "uv run alembic upgrade head"
drop = "dropdb {name}"
env_override = "DATABASE_URL"
url_template = "postgresql:///{name}"

[graph.ruby]
extensions = [".rb"]
pattern = "^require_relative '(.+?)'"
resolve = ["{dir}/{1}.rb"]
```
