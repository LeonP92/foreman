# Overview

The first view of the review's diagram page (`Overview | Graph | Matrix`): what a person
reads to understand the change's design without opening the diff. What it does, how the
pieces talk, why it was built this way, and what it leaves out. You write only
`<run>/diagram/overview.json`; `render ... --overview` validates it together with the
diagram's `data.json` and writes both into `diagram.html`. Never write or edit the HTML
yourself.

Write it last, from what steps 1–6 found. Plain English for someone who knows the product
but not this code; no findings (those stay in `review.md`).

## What goes in

- **Header** (always): `title` says what the change does for a user, not the branch name.
  `branch`, `base` and `head` are the branch name and the two short SHAs from the report;
  `stats` counts commits (`git rev-list --count BASE..<branch>`) and added / removed lines
  (`git diff --shortstat BASE <branch>`).
- **Summary** (always): one paragraph, then 3–6 bullets of the parts that matter.
- **Network view** (optional): only when the change involves systems talking to each other
  (a browser, a server, a database, an outside service). Zones are where things run ("User's
  device", "Our cloud", a third-party provider), listed left to right as they should appear;
  nodes are what runs there. A change inside one process gets no network view.
- **Sequence view** (optional): only when the order of calls is the point, 2–5 participants.
  A step one participant takes alone (a check, a write) is a message to itself.
- **Component view** (always, nothing to write): a button that switches to the Graph view.
  Never redraw the modules in the network view.
- **Key design decisions** (always): each says why, against the alternative it beat. "Uses a
  module" is not a decision; "rules in their own module, because three callers need them"
  is.
- **Cards** (optional): 1–3 short lists worth their own box, such as the checks performed or
  what was tested.
- **What changed** (always): one row per area (a module, a folder, config, a migration).
- **Known limits / not done** (always): be honest. What the change doesn't handle, what
  wasn't checked, what a reviewer might assume works and doesn't. Never empty.

## The data file

```json
{
  "title": "Coupon usage limits",
  "branch": "coupon-limits",
  "base": "a1b2c3d",
  "head": "d4e5f6a",
  "stats": {"commits": 4, "added": 210, "removed": 31},
  "summary": "Coupons can carry a usage limit; checkout refuses a coupon once it is used up.",
  "bullets": ["`limits.uses_left()` counts uses", "the admin form gains Max uses", "refunds restore a use"],
  "network": {
    "caption": "The browser only talks to the shop.",
    "zones": [{"id": "device", "label": "Shopper's device", "role": "neutral"},
              {"id": "cloud", "label": "Our cloud", "role": "blue"}],
    "nodes": [{"id": "browser", "zone": "device", "title": "Browser"},
              {"id": "web", "zone": "cloud", "title": "Shop web app", "subtitle": "checkout",
               "lines": ["counts coupon uses"]},
              {"id": "db", "zone": "cloud", "title": "Database"}],
    "edges": [{"from": "browser", "to": "web", "label": "HTTPS", "both": true},
              {"from": "web", "to": "db", "label": "uses per coupon"}]
  },
  "sequence": {
    "caption": "Applying a coupon that has one use left.",
    "participants": [{"id": "web", "label": "Shop web app"}, {"id": "db", "label": "Database"}],
    "messages": [{"from": "web", "to": "db", "label": "count uses", "notes": ["one query"]},
                 {"from": "web", "to": "web", "label": "refuse if used up", "role": "red"}]
  },
  "decisions": [{"decision": "Count uses in the database", "why": "Two servers share it; a memory count would let both accept the last use."}],
  "cards": [{"title": "Tested", "bullets": ["limit of 1, used twice", "refund then reuse"]}],
  "changes": [{"area": "`billing/limits.py`", "change": "New: `uses_left()`."}],
  "limits": ["Uses are not counted per customer, only per coupon."]
}
```

| Field | Values |
|---|---|
| `role` (zones, messages) | `neutral`, `blue`, `green`, `purple`, `amber`, `red`; a message's role highlights it (default `neutral`) |
| network `zones` | 1–5, each with at least one node; drawn as columns in the order given |
| network edge `style` | `solid` (default, a direct call) or `dashed` (goes through the browser: redirects, forms another site serves) |
| network edge `both` | `true` for a two-way link; arrowheads at both ends |
| network edges in one zone | nodes listed next to each other get a short line between them (one edge per such pair); others run down the side of the zone |
| `sequence.participants` | 2–5 |
| `cards` | 1–3, each with at least one bullet |

All text is plain: backticks become code, everything else is shown as written (never
HTML). The page lays the views out itself, so there are no coordinates. Keep node lines and
edge labels short (a few words); long text wraps and makes the figure tall.
