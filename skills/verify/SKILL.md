---
name: verify
description: Drives the app in a real browser on the base branch and on the change side by side, using copied data only, and reports what broke, with screenshots. Use when asked to verify, QA or browser-test a branch, or when a foreman review finds a user-facing change.
---

# Verify

Proves a change works by running it: the same Playwright steps against a server built
from the base branch and one built from the change, each on its own copy of the data.

## Before you start

- Run foreman's scripts as `python3 -I <root>/scripts/run.py <command>` (`python` or `py` on
  Windows), where `<root>` is two directories above this file. Run them from the repo's top
  folder; every command prints JSON.
- If `.foreman/config.toml` is missing or `config-check` fails, run the setup skill first.
- Rules: never commit, push, or edit product code; never point anything at real data; pass
  credentials only through files or environment variables and never print them; clean up
  every worktree, server (whole process tree), and temp file you create; end with
  "Not checked:" and why.

Output: `.foreman/reports/<branch>/verify/`, where `<branch>` has each `/` replaced by
`-`. Needs Node 20 or newer; `browser-run` installs its own Playwright.

## 1. Test list first

Find the main flow, in this order, and say which source you used: what the user passed
(a ticket, a sentence); the PR description via `gh pr view <branch>` if `gh` is installed
and signed in; the branch's commit messages (`git log <base>..<branch>`); the diff alone.

Write the list before touching a browser: the main flow plus 2–3 edge cases it implies
(invalid input, data created before the change, a user with less access). Give each item a
short lowercase name, like `apply-coupon` or `expired-coupon`; it becomes the test title
and the screenshot name.

## 2. Can the data be isolated?

Read `[database]`:

- `none`: no data to prepare.
- `file`: works when `path` is inside the repo. Each worktree gets its own copy.
- `command`: works when `create`, `env_override` and `url_template` give each server its
  own database.

Otherwise stop before starting anything. Say why, and what config would make it possible.
Never point a server at a database you didn't copy or create.

## 3. Worktrees and data

1. Add two worktrees outside the repo: `git worktree add --detach <temp>/base <base>` and
   the same for the branch. Run `[commands] install` in each.
2. Build both databases with the **base** code, so "existing data" is genuinely pre-change:
   - `file`: `python3 -I <root>/scripts/run.py db-copy <repo>/<path> <temp>/base/<path>`
     (if the original doesn't exist, start empty). In the base worktree run `migrate`,
     `seed`, and create the records the test list needs. Then copy that file to the branch
     worktree with `db-copy` the same way.
   - `command`: for each server pick a unique `{dir}` (for example
     `foreman_<timestamp>_base`), fill it into `create` and `url_template`, and run
     `create`, `migrate`, `seed` and your record set-up from the **base** worktree with
     `env_override` set to that server's value.
3. Migrate the branch's database with the **branch** code: run `migrate` in the branch
   worktree (with its `env_override` for `command`).

Record what data you created; the report says what changed.

## 4. Servers

For each worktree: pick a free port (for example, bind a socket to port 0 and read the
port back), run `[server] start` with `{port}` filled in, `[server] env` and, for
`command` databases, `env_override` set to that server's database. Start each server as
the leader of its own process group (on Windows, note its PID) so you can stop the whole
tree later. Poll `http://127.0.0.1:<port><ready_path>` until it answers; if it never
does, report the server's last output lines and stop.

## 5. One Playwright spec

Write one spec, for example `.foreman/reports/<branch>/verify/verify.spec.mjs`:

```js
import { test, expect } from "./foreman-fixtures.mjs";

test.beforeEach(async ({ page }) => {
  // [login] steps; the password comes from the environment, never from this file
  await page.goto("/login");
  await page.getByLabel("Email").fill("demo@example.com");
  await page.getByLabel("Password").fill(process.env.SHOP_DEMO_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
});

test("apply-coupon", async ({ page }) => {
  await page.goto("/cart");
  await page.getByLabel("Coupon").fill("SPRING10");
  await page.getByLabel("Coupon").press("Enter");
  await expect(page.getByText("10% off")).toBeVisible();
});
```

- Import `test` and `expect` only from `./foreman-fixtures.mjs`; `browser-run` rejects a
  spec that imports `@playwright/test`. The fixtures record console errors and 4xx/5xx
  responses and take a full-page screenshot of every test.
- Use paths, not full URLs: each project gets its own base URL.
- On every changed form, add steps that Tab through it (each field takes focus visibly, in
  a sensible order) and press Enter in a text field (it submits, or doesn't if the form
  says so).

Run it:
`python3 -I <root>/scripts/run.py browser-run --spec <spec> --out .foreman/reports/<branch>/verify --base http://127.0.0.1:<base port> --branch http://127.0.0.1:<branch port>`.
Set any credential the spec reads in the environment of that command, loaded from a
file; never type it into the spec, the command line or the transcript.

The result lists each test per project (`base`, `branch`) with status, console errors, bad
responses and screenshots named `<item>-base.png` and `<item>-branch.png`. If the spec
itself fails to load, fix it and re-run.

## 6. Read the results

- Base fails, branch passes: the change does what it says.
- Both pass on the main flow: base already behaves correctly. Say so plainly; the change
  may be unnecessary, or the test doesn't reach the change.
- Branch fails, or shows console errors or bad responses base doesn't: a finding.

Each browser finding: item name, steps to reproduce, expected, actual, and both screenshot
paths. Look at the screenshots, not only the statuses: layout breaks don't fail tests.

## 7. Clean up

Stop both servers and their whole process trees (POSIX: signal the process group; Windows:
`taskkill /T /F /PID <pid>`) before removing anything. Then
`git worktree remove --force <worktree>` for each; on Windows, if a file is still locked,
wait a few seconds and retry once. Remove temporary files and `{dir}` folders; list any
`command` databases you created so the user can drop them. The user's real data must be
untouched.

## Finish

Report: the test list and its source, the data you set up, a table of item → base / branch
result, findings in the review's format (`<root>/skills/review/references/report.md`), and
the output folder. End with "Not checked:" (for example: mobile sizes, other browsers,
flows outside the list).
