# Simplicity

Every line a change adds is a line someone has to read, test and keep working. This pass
looks for lines the change could have done without.

## Look past the changed lines

Judge new code against its surroundings, not on its own. Open the functions it calls and
the places that call it. A new helper can look reasonable and still repeat one that lives
elsewhere in the repo; a check that seems to be missing may already run one level up.

## Three questions, in this order

For each thing the change adds (a function, a class, an option, a branch, a file):

1. **Is anything using it?** Look for a setting no caller changes, a branch for input that
   can't arrive, a wrapper whose only job is to forward a call, code parked for a future
   feature. Suggest removing it.
2. **Is it already in the repo?** Search for a helper, component or query doing the same
   job. Suggest switching to that one and removing the new copy.
3. **Is it already in the language or a dependency the repo installs?** Date arithmetic,
   retries, parsing, form validation the framework handles. Suggest calling that instead.

If all three come back empty, the addition earns its place; the only remaining question is
whether a shorter version would read just as well.

## Smaller is the better fix

When two fixes would both work, recommend the one that leaves less code behind: fold two
near-copies into one, inline a wrapper used once, drop a parameter every caller sets the
same way. Adding a guard or a new layer is the last resort, not the first.

## Leave these alone

- **Limits the author wrote down.** If a comment names the shortcut and its ceiling
  ("keeps all orders in memory; revisit past 10k orders"), the author chose it on
  purpose. Raise it only when the repo is already past that ceiling, and show that it is.
- **Checks where outside input enters.** Validating what users send, handling a failed
  network call, protecting stored data: these stay even when they look verbose.
- **Preferences.** A different name, a loop you'd write as a comprehension. Unless you can
  point to something that breaks or misleads, skip it.

## Writing it up

One line says what goes and what takes its place:
"`checkout/discounts.py:40` `percent_of()` repeats `money.percent()`; call that and delete
40–58." For simplicity findings the concrete case is the cost you can point at: the copy
that will fall out of step, the option nobody passes, the lines a reader must wade through.
