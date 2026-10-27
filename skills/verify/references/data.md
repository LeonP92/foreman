# Building the data each item needs

Never skip a test item because the copies have no matching data: create the records it
needs in the copies. Only if that is truly impossible (the state comes from an outside
service you can't reach, say) list the item under "Not checked:" with the reason.

## Phase a: pre-change data, with the base code

Build both databases with the **base** code, so "existing data" is genuinely pre-change:

- `file`: `python3 -I <root>/scripts/run.py db-copy <repo>/<path> <base copy>`, where a
  side's copy is where the skill's step 2 puts it (`db-copy` creates its folders; if the
  original doesn't exist, start empty). In the base worktree run `migrate`, `seed`, and
  create the records the test list needs. Then copy that file to the branch side with
  `db-copy` the same way.
- `command`: run `create`, `migrate`, `seed` and your record set-up from the **base**
  worktree with that server's settings.

Then run `migrate` in the branch worktree, with the **branch** code.

## Phase b: state found while exploring

Records you only discover you need while exploring are phase b: write them once as set-up
statements or a script and apply exactly the same ones to both copies, after both are
migrated.

If the test user gets 403 on a page an item needs, on **both** sides, grant that
permission in both copies as a phase b record (a role, a group membership) and say so in
the report. Never grant anything in real data.

## When the diff adds a migration

Always add an item `existing-data-survives`: the rows that were there before the change
survive it, or are backfilled as the migration says. In phase a, seed representative
pre-change rows of every kind the migration touches (including empty and old-style
values) with the base code; migrate the branch copy with the branch code; then check those
rows, through the app where a page shows them, otherwise by querying the branch **copy**
read-only. Never query or migrate the real database.

## Report

List every record you created, its phase, and why; and any permission you granted.
