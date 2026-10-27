# Simplicity

The cheapest code to review, run and maintain is code that doesn't exist. Look for what
the change could do without.

## Read wider than the diff

A line is only simple or not in context. Before judging, read what the changed code calls
and what calls it. A helper that looks fine in the diff may duplicate one two folders over;
a check that looks missing may already happen in the caller.

## For every addition, ask in order

1. **Does it need to exist?** An option nobody sets, a branch for a case that can't
   happen, a layer with one caller that only passes calls through, code kept "for later".
   The fix is to delete it.
2. **Does the repo already have it?** A helper, component or query that does the same job.
   The fix is to use the existing one and delete the new one.
3. **Does the standard library or an installed dependency do it?** Hand-written date
   maths, retry loops, parsing, or validation the framework already provides. The fix is
   to call the library.

Only when all three answers are no is the new code the right shape; then ask whether it
could be shorter and still as clear.

## Prefer fixes that delete

Between two fixes, suggest the one that removes more code. Merging two near-identical
functions, inlining a single-use wrapper, or dropping a parameter every caller passes the
same value for usually beats adding a guard or an abstraction.

## Not findings

- **A marked shortcut.** Code with a comment stating its limit and when to revisit it
  (for example, "loads every order into memory; fine below 10k orders") is a decision,
  not a finding. It becomes one only when the limit is already crossed, and the finding
  shows that it is.
- **Defensive code at a real boundary.** Validating user input, handling a network error,
  or anything that prevents data loss stays.
- **Taste.** Naming you'd do differently, a loop that could be a comprehension. If you
  can't show what goes wrong, leave it.

## Writing the finding

Name what to delete or replace and what replaces it, in one line:
"`checkout/discounts.py:40` `percent_of()` repeats `money.percent()`; call that and delete
40–58." The concrete case for a simplicity finding is the cost: the second copy that will
drift, the option no caller passes, the lines a reader has to get through.
