# Config

`.foreman/config.toml`, written by `setup`, read by every other skill. Check it with
`python3 scripts/run.py config-check` (exit 1 and a list of problems when invalid; a missing file
is fine and means defaults). Unknown tables and keys are errors.

## Keys

| Key | Meaning |
|---|---|
| `repo.base` | Branch to diff against. Default `"main"`. |
| `repo.ignore` | Globs left out of every graph and report. |
| `commands.install` / `lint` / `typecheck` / `test` / `e2e` | Shell commands; empty means skip. |
| `commands.test_targeted` | Test command for a subset; `{paths}` is replaced by the test files. |
| `server.start` | Command that starts the app; must contain `{port}`. |
| `server.ready_path` | URL path polled until the server answers. Default `"/"`. |
| `server.env` | Extra environment variables for the server, as a table. |
| `login.steps` | Plain-language instructions for the agent to sign in. |
| `database.kind` | `"none"`, `"file"` or `"command"`. Default `"none"`. |
| `database.path` | The database file. Required for `file`. |
| `database.create` | Command that creates a database. Required for `command`. |
| `database.migrate` / `seed` | Optional commands, either kind. |
| `database.drop` | Optional command that deletes a database `create` made (`command` kind). Only ever run on databases foreman created. |
| `database.env_override` | Env var that points the server at its database. Required for `command`. |
| `database.url_template` | Value for that env var. Required for `command`. |
| `rules.docs` | Repo docs that state design rules. |
| `rules.layers` | Edges that must not exist: `[{from = "glob", to = "glob"}]`. |
| `graph.<name>` | Import rule for a language without a built-in graph (needs an import rule; setup writes one): `extensions`, `pattern` (regex, group 1 is the import), `resolve` (candidate paths using `{dir}`, `{1}`, `{1\|path}`). |

`create`, `migrate`, `seed`, `drop` and `url_template` may use two placeholders, filled in
per server:

- `{dir}`: the server's own directory, for file paths (`sqlite:///{dir}/app.db`).
- `{name}`: a unique database name, `foreman_<base|branch>_<6 lowercase hex>` (letters,
  digits and underscores only), for database servers (`postgresql:///{name}`).

## Example: web app with a file database

```toml
[repo]
base = "main"
ignore = ["dist/**"]

[commands]
install = "npm ci"
lint = "npm run lint"
test = "npm test"
test_targeted = "npm test -- {paths}"

[server]
start = "npm run dev -- --port {port}"
ready_path = "/health"
env = { APP_ENV = "test" }

[login]
steps = "Open /login, sign in as demo@example.com with the password from the seed output."

[database]
kind = "file"
path = "data/app.db"
migrate = "npm run migrate"
seed = "npm run seed"

[rules]
docs = ["docs/architecture.md"]
layers = [{ from = "src/ui/**", to = "src/db/**" }]
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
