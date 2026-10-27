# Report format

Glance first. The top block answers "can this merge, and if not, what first?" in under a
minute. Everything below it is there to drill into, never required reading.

## Top block

- **Verdict:** `ship` or `fix N first`, where N is the number of Must fix findings (plus
  any Should fix you judge blocks the merge; say why).
- **Findings:** counts by severity, `M must / S should / N nice`.
- **Tests:** passed / run, or which command failed.
- **Browser:** items passing on branch / items run, and how many bugs base reproduced;
  or "n/a, no user-facing change".
- **Smells:** count from the diagram.
- **Links:** diagram path, and the map path if there is one.

Then 2–3 sentences on what the change does.

## Findings

One numbered list across all steps, grouped **Must fix**, then **Should fix**, then
**Nice to have**, most severe first within each group. Numbering continues across the
groups, so every finding has its own number to reply with. Each finding has:

- a bold title with its severity, and the location in brackets;
- **Problem:** one sentence;
- **Case:** the concrete input, sequence or load where it goes wrong;
- **Fix:** the smallest change;
- **If skipped:** what happens.

Browser findings replace Case with **Steps**, **Expected**, **Actual** and **Screenshots**.
Design findings add **Rule:** the rule and where it is written.

## Below the findings

1. **Tests:** a table of command → result, with the failure lines of anything that failed.
2. **Browser:** the test list and where it came from, the data set up, a table of
   item → base / branch, and the output folder.
3. **Diagram:** the path, and the smells with their evidence.
4. **Not checked:** one line per gap and why.

## Example (invented)

```
## Review: feature/coupon-limits (PR #12)

Verdict: fix 1 first · 1 must / 1 should / 0 nice · tests 412/412 ·
browser 2/2 pass on branch (base reproduced 1 bug) · 1 smell ·
diagram: .foreman/reports/feature-coupon-limits/diagram/diagram.html

Coupons can now carry a usage limit. Checkout counts uses and refuses a coupon once
the limit is reached; the admin form gains a "Max uses" field.

### Must fix
1. **Must fix — refunds skip the new limit** (`billing/refund.py:88`)
   Problem: a refund restores the coupon's use count without checking the limit.
   Case: a coupon limited to 1 use is applied, refunded, then applied twice more.
   Fix: call `limits.uses_left()` before restoring the count in `refund_order()`.
   If skipped: limited coupons can be used without limit through refunds.

### Should fix
2. **Should fix — browser: totals overflow on mobile** (Checkout, steps 1–3)
   Steps: open /cart at 375 px wide, apply SPRING10, scroll to the total.
   Expected: the discount line fits the card. Actual: the total runs off the right edge.
   Screenshots: apply-coupon-base.png, apply-coupon-branch.png
   Fix: let the discount label wrap in `cart/summary.html`.
   If skipped: mobile buyers can't see what they'll pay.

### Tests
| Command | Result |
|---|---|
| `make test-file FILES=tests/test_coupons.py` | 18 passed |
| `make lint` | ok |
| `make test` | 412 passed |

### Browser (source: PR description)
| Item | Base | Branch |
|---|---|---|
| apply-coupon | fail (no limit) | pass |
| expired-coupon | pass | pass |

### Diagram
.foreman/reports/feature-coupon-limits/diagram/diagram.html
- twin (medium): the limit check in `checkout/coupons.py` and the SQL in
  `reports/usage.sql`; no parity test.

Not checked: other browsers; mobile layout beyond the checkout page.
```
