# Writing the spec

## Exploring first

To learn the running app (labels, routes, what a page shows) before writing the final
spec, write a throwaway spec (`explore.spec.mjs` in the same output folder) and run it
through `browser-run` like the real one; its screenshots and results stay in the reports
folder. If you use a browser tool instead, run it from a folder outside the repo and
afterwards remove only the files it created there.

A console error that shows on every base page you explored (say, a page that streams
events and logs "Event stream reconnecting" on load) is known noise, not a finding. Offer
the user an anchored regex for it in `[verify] ignore_console` (`^Event stream
reconnecting`); add it only with a yes. `browser-run` then lists it under
`ignored_console_errors`.

## Pitfalls

- **No serial mode.** Never `test.describe.configure({ mode: "serial" })`. An expected
  failure on base would skip every later item on base, and the comparison is lost. Keep
  each item an independent `test`.
- **Visibility, not absence.** For content shown or hidden by CSS or JavaScript (a
  collapsed panel, a toggled banner), assert `toBeVisible()` / `toBeHidden()`. Hidden
  text is still in the page, so `not.toHaveText` or a text-count check passes or fails for
  the wrong reason.
- **Shared data, in order.** Items run in the order written, against one database per
  side. An item that creates, edits or deletes data changes what later items see: put it
  last, give it its own records, or have it restore what it changed.
