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
  every worktree, server (whole process tree), and temp file you create. Never delete or
  modify anything you didn't create in this run — including ignored files and folders.
  End with "Not checked:" and why.

Output: `.foreman/reports/<branch>/verify/`, where `<branch>` has each `/` replaced by
`-`. Needs Node 20 or newer; `browser-run` installs its own Playwright.

## 1. Test list first

Find the main flow, in this order, and say which source you used: what the user passed
(a ticket, a sentence); the PR description via `gh pr view <branch>` if `gh` is installed
and signed in; the branch's commit messages (`git log BASE..<branch>`, `BASE` as in
step 3); the diff alone.

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

**Guard the real file.** For `file`, before any command runs, record the size and
modification time of the real database (`[database] path` in the repo) and of its `-wal`
and `-shm` files (or that they don't exist). Check them again after migrate and seed, and
after the browser run. If anything changed, stop at once: clean up, and report a Must fix
finding that foreman's isolation failed (what ran just before, the old and new values).
Do not continue the run.

Every command runs through the launcher in `references/servers.md`, with an explicit
environment that can't reach the real database.

## 3. Worktrees and data

1. The base is `BASE = git merge-base <repo.base> <branch>`, never the tip of
   `repo.base`; if `BASE` equals the branch tip, there is nothing to review, or it was
   already merged and `BASE^` is the base, as the review skill decides. Make a temp folder
   under the system temp directory, outside the repo, and add two worktrees there:
   `git worktree add --detach <temp>/base <BASE>` and the same for the branch. Pick each
   server's port, `{name}` and `{dir}`, and prepare each worktree (copy `[repo] copy`
   files and fix their database lines, `install`, `build`), as `references/servers.md`
   says.
2. Build both databases with the **base** code, so "existing data" is genuinely pre-change
   (phase 1 records):
   - `file`: `python3 -I <root>/scripts/run.py db-copy <repo>/<path> <temp>/base/<path>`
     (if the original doesn't exist, start empty). In the base worktree run `migrate`,
     `seed`, and create the records the test list needs. Then copy that file to the branch
     worktree with `db-copy` the same way.
   - `command`: run `create`, `migrate`, `seed` and your record set-up from the **base**
     worktree with that server's settings.
3. Migrate the branch's database with the **branch** code: run `migrate` in the branch
   worktree.
4. Records you only discover you need while exploring (step 4) are phase 2: write them
   once as set-up statements or a script and apply exactly the same ones to both copies,
   after both are migrated.

Record what data you created and which phase each record came from; the report says.

## 4. Servers

For each worktree, start `[server] start` with its `{port}` through the launcher, which
puts it in its own process group so the whole tree can be stopped later. Poll `http://127.0.0.1:<port><ready_path>` until it answers; if it never does, report the
server's last output lines and stop.

## 5. One Playwright spec

Write one spec, for example `.foreman/reports/<branch>/verify/verify.spec.mjs`:

```js
import { test, expect } from "./foreman-fixtures.mjs";

test.beforeEach(async ({ page }) => {
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
Set any credential the spec reads (the `[login]` password) in that command's environment,
loaded from a file; never type it into the spec, the command line or the transcript.

The result lists each test per project (`base`, `branch`) with status, the error's first
lines and location when it failed, console errors, bad responses and screenshots named
`<item>-base.png` and `<item>-branch.png`. If the spec fails to load, fix it and re-run.

## 6. Read the results

- Base fails, branch passes: the change does what it says.
- Both pass on the main flow: base already behaves correctly. Say so plainly; the change
  may be unnecessary, or the test doesn't reach the change.
- Branch fails, or shows console errors or bad responses base doesn't: a finding.

Each browser finding: item name, steps to reproduce, expected, actual, and both screenshot
paths. Look at the screenshots, not only the statuses: layout breaks don't fail tests.

## 7. Clean up

Stop both servers (whole process trees), then remove the worktrees, temp files and
`{dir}` folders, as `references/servers.md` shows. Run `drop` for each `command` database
you created (if `drop` is empty, list the names under "Not checked:"); never drop one you
didn't create. The user's real data must be untouched.

## Finish

Report: the test list and its source, the data you set up, a table of item → base / branch
result, findings in the review's format (`<root>/skills/review/references/report.md`), and
the output folder. End with "Not checked:" (for example: mobile sizes, other browsers,
flows outside the list).
