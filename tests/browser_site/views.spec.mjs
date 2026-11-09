import { test, expect } from "./foreman-fixtures.mjs";

const card = (page, id) => page.locator(`.card[data-id="${id}"]`);
const top = async (page, id) => (await card(page, id).boundingBox()).y;
const opacity = (page, id) => card(page, id).evaluate(el => Number(getComputedStyle(el).opacity));

test("diagram focus pulls neighbours up and fades the rest", async ({ page }) => {
  await page.goto("/diagram.html");
  // checkout lane: cart, order, discounts; refunds links to discounts (last) but not to cart_view.
  const first = await top(page, "cart"), last = await top(page, "discounts");
  await card(page, "refunds").click();
  await expect.poll(() => top(page, "discounts")).toBe(first);
  await expect.poll(() => opacity(page, "cart_view")).toBeLessThanOrEqual(0.2);
  await page.locator("#canvas").click({ position: { x: 5, y: 5 } });
  await expect.poll(() => top(page, "discounts")).toBe(last);
  await expect.poll(() => opacity(page, "cart_view")).toBe(1);
});

test("diagram header and card sub-lines keep their full text on hover", async ({ page }) => {
  await page.goto("/diagram.html");
  await expect(page.locator("#notes")).toHaveAttribute("title", "Import edges from the Python import graph; cart.js imports read directly.");
  await expect(card(page, "cart").locator(".card-sub")).toHaveAttribute("title", "Cart");
});

test("diagram filter enter focuses the first match", async ({ page }) => {
  await page.goto("/diagram.html");
  await page.locator("#filter").fill("checkout/");
  await page.locator("#filter").press("Enter");
  await expect(card(page, "cart")).toHaveClass(/selected/);
});

test("map enter on a group drills in and focuses the breadcrumb", async ({ page }) => {
  await page.goto("/map.html");
  await page.locator(".card.group", { hasText: "app" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#crumb-all")).toBeFocused();
});

const group = (page, label) => page.locator(".card.group", { has: page.locator(".card-label", { hasText: new RegExp(`^${label}$`) }) });
const left = async locator => (await locator.boundingBox()).x;

test("map with more than 30 package edges opens as a matrix", async ({ page }) => {
  await page.goto("/dense.html");
  await expect(page.locator("#matrix")).toBeVisible();
  await expect(page.locator('#seg [data-mode="matrix"]')).toHaveAttribute("aria-pressed", "true");
});

test("map with few package edges opens as a graph", async ({ page }) => {
  await page.goto("/layered.html");
  await expect(page.locator("#matrix")).toHaveCount(0);
  await expect(page.locator(".card.group")).toHaveCount(3);
});

test("problems only hides import edges", async ({ page }) => {
  await page.goto("/layered.html");
  await page.locator("#edges").click();
  await page.locator('[data-set="problems"]').click();
  // display, not visibility: a straight vertical edge has an empty bounding box
  await expect(page.locator("path.edge.import")).toHaveCSS("display", "none");
  await expect(page.locator("path.edge.forbidden")).not.toHaveCSS("display", "none");
  await expect(page.locator("path.edge.cycle")).not.toHaveCSS("display", "none");
});

test("map neighbourhood puts dependents left and dependencies right", async ({ page }) => {
  await page.goto("/layered.html");
  await group(page, "svc").click();
  await page.keyboard.press("n");
  await expect(page.locator(".ego-bar")).toBeVisible();
  await expect.poll(async () => (await left(group(page, "app"))) < (await left(group(page, "svc")))).toBe(true);
  await expect.poll(async () => (await left(group(page, "svc"))) < (await left(group(page, "lib")))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(page.locator(".ego-bar")).toBeHidden();
  await expect(group(page, "svc")).toHaveClass(/selected/);
  await expect(page.locator(".layer-label")).toHaveCount(3);
});

test("diagram neighbourhood puts dependents left and dependencies right", async ({ page }) => {
  await page.goto("/diagram.html");
  await card(page, "gateway").click();
  await page.locator("[data-ego]").click();
  await expect(card(page, "cart_view")).toBeHidden();
  await expect.poll(async () => (await left(card(page, "refunds"))) < (await left(card(page, "gateway")))).toBe(true);
  await expect.poll(async () => (await left(card(page, "gateway"))) < (await left(card(page, "receipts")))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(card(page, "cart_view")).toBeVisible();
  await expect(card(page, "gateway")).toHaveClass(/selected/);
});

test("map label follows its arc after the drawer closes", async ({ page }) => {
  await page.goto("/wide.html");
  // Distance from the label to the midpoint of its edge.
  const offset = () => page.evaluate(() => {
    const path = document.querySelector("path.edge.cycle"), text = document.querySelector("text.edge-label");
    const mid = path.getPointAtLength(path.getTotalLength() / 2);
    return Math.hypot(Number(text.getAttribute("x")) - mid.x, Number(text.getAttribute("y")) + 6 - mid.y);
  });
  const top = async label => (await group(page, label).boundingBox()).y;
  await group(page, "y").click();
  await expect.poll(async () => (await top("z")) > (await top("x"))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(page.locator("#drawer")).not.toHaveClass(/open/);
  await expect.poll(offset).toBeLessThan(1);
});

test("map renders when storage is unavailable", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", { get() { throw new DOMException("denied", "SecurityError"); } });
  });
  await page.goto("/layered.html");
  await expect(page.locator(".card.group")).toHaveCount(3);
  await page.locator("#theme").click();
  await page.locator('#seg [data-mode="matrix"]').click();
  await expect(page.locator("#matrix")).toBeVisible();
});

test("diagram switch toggles to matrix and back", async ({ page }) => {
  await page.goto("/diagram.html");
  await expect(page.locator('#seg [data-mode="graph"]')).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#matrix")).toBeHidden();
  await page.locator('#seg [data-mode="matrix"]').click();
  await expect(page.locator("#matrix")).toBeVisible();
  await expect(card(page, "cart")).toBeHidden();
  // lanes in order, importers before what they import within a lane
  expect(await page.locator("#matrix .mx-row").evaluateAll(rows => rows.map(r => r.dataset.g))).toEqual(
    ["cart_view", "cart_js", "order", "cart", "discounts", "refunds", "gateway", "receipts"]);
  await expect(page.locator("#matrix button.cell.twin")).toHaveCount(1);
  await page.locator('#matrix button.cell[data-a="order"][data-b="cart"]').click();
  await expect(page.locator("#drawer")).toHaveClass(/open/);
  await expect(page.locator('#matrix .mx-row[data-g="order"]')).toHaveClass(/on/);
  await page.locator('#seg [data-mode="graph"]').click();
  await expect(page.locator("#matrix")).toBeHidden();
  await expect(card(page, "cart")).toBeVisible();
});

test("diagram with more than 30 edges opens as a matrix", async ({ page }) => {
  await page.goto("/dense-diagram.html");
  await expect(page.locator("#matrix")).toBeVisible();
  await expect(page.locator('#seg [data-mode="matrix"]')).toHaveAttribute("aria-pressed", "true");
});

test("map smell chips split severities and count dropped and dismissed", async ({ page }) => {
  await page.goto("/capped.html");
  // each note sits on the chip of its own kind and severity
  await expect(page.locator("button.chip")).toHaveText([
    "high · layering1(+3 more)(+2 dismissed)",
    "medium · hub1(+1 dismissed)",
    "low · hub1(+2 more)",
  ]);
  await expect(page.locator(".chip", { hasText: "smells" })).toHaveText("8 smells(+7 dismissed)");
  // every low deadcode smell was dismissed: a count-0 chip still says so
  await expect(page.locator(".chip", { hasText: "deadcode" })).toHaveText("low · deadcode0(+4 dismissed)");
});

test("map double-click on a group drills in", async ({ page }) => {
  // the drawer opening on the first click wraps the row, moving z away from the pointer
  await page.goto("/wide.html");
  await group(page, "z").dblclick();
  await expect(page.locator("#crumbs")).toContainText("z");
  await expect(page.locator("#crumb-all")).toBeVisible();
});

test("map filter enter focuses the first match so N opens its neighbourhood", async ({ page }) => {
  await page.goto("/layered.html");
  await page.locator("#filter").fill("svc");
  await page.locator("#filter").press("Enter");
  await expect(group(page, "svc")).toBeFocused();
  await page.keyboard.press("n");
  await expect(page.locator(".ego-bar")).toBeVisible();
  await expect(page.locator("#filter")).toHaveValue("svc");
});

test("diagram with an overview opens on it and its component view switches to the graph", async ({ page }) => {
  await page.goto("/overview.html");
  await expect(page.locator('#seg [data-mode="overview"]')).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#overview")).toBeVisible();
  await expect(page.locator("#filter")).toBeHidden();
  await expect(page.locator("[popovertarget=legend]")).toBeHidden();
  await page.locator('[data-view="graph"]').click();
  await expect(page.locator('#seg [data-mode="graph"]')).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#overview")).toBeHidden();
  await expect(card(page, "cart")).toBeVisible();
  await expect(page.locator("#filter")).toBeVisible();
});

test("diagram without an overview offers no overview view", async ({ page }) => {
  await page.goto("/diagram.html");
  await expect(page.locator('#seg [data-mode="overview"]')).toBeHidden();
  await expect(page.locator('#seg [data-mode="graph"]')).toHaveAttribute("aria-pressed", "true");
});

test("diagram edges never pass behind a card they don't connect", async ({ page }) => {
  for (const url of ["/diagram.html", "/lanes.html"]) {
    await page.goto(url);
    await page.waitForTimeout(400);  // cards slide into place
    const hits = await page.evaluate(() => {
      const cards = [...document.querySelectorAll(".card")].map(c => ({ id: c.dataset.id, r: c.getBoundingClientRect() }));
      const out = new Set();
      for (const p of document.querySelectorAll("path.edge[data-a]")) {
        const m = p.getScreenCTM();
        for (let s = 0; s <= p.getTotalLength(); s += 2) {
          const { x, y } = p.getPointAtLength(s).matrixTransform(m);
          for (const { id, r } of cards)
            if (id !== p.dataset.a && id !== p.dataset.b && x > r.left + 1 && x < r.right - 1 && y > r.top + 1 && y < r.bottom - 1)
              out.add(`${p.dataset.a} -> ${p.dataset.b} behind ${id}`);
        }
      }
      return [...out];
    });
    expect(hits, url).toEqual([]);
  }
});

test("diagram long labels keep their file name", async ({ page }) => {
  await page.goto("/lanes.html");
  const label = card(page, "b1").locator(".card-label");
  // the front goes first, whole folders at a time; the file name always stays
  await expect(label).toHaveText(/^…\/([\w-]+\/)*discounts\.py$/);
  await expect(label).toHaveAttribute("title", "shop/services/orders/pricing/discounts.py");
});

test("diagram shows a renamed file's old path", async ({ page }) => {
  await page.goto("/lanes.html");
  await card(page, "c1").click();
  await expect(page.locator("#drawer .diff .old")).toHaveText("shop/billing/old_invoices.py");
});

test("diagram never cuts a file name or a group's folder and count", async ({ page }) => {
  await page.goto("/lanes.html");
  const label = card(page, "n1").locator(".card-label");
  await expect(label).toHaveText(/invoice_reconciliation_helpers\.py$/);
  // shrunk or wrapped, never clipped, and still inside its card beside the NEW badge
  expect(await label.evaluate(e => e.scrollWidth <= e.clientWidth && e.scrollHeight <= e.clientHeight)).toBe(true);
  const [l, c, b] = [await label.boundingBox(), await card(page, "n1").boundingBox(), await card(page, "n1").locator(".badge").boundingBox()];
  expect(l.y >= c.y && l.y + l.height <= c.y + c.height && l.x + l.width <= b.x).toBe(true);
  await expect(card(page, "g1").locator(".card-label")).toHaveText(/(^|\/)services\/ — 7 modules$/);
});

test("diagram with a wide overview network scrolls it instead of shrinking it", async ({ page }) => {
  await page.goto("/overview-wide.html");
  const fig = page.locator("#overview figure").first();
  const [drawn, full, scrolls] = await fig.evaluate(f => {
    const svg = f.querySelector("svg");
    return [svg.getBoundingClientRect().width, svg.viewBox.baseVal.width, f.scrollWidth > f.clientWidth];
  });
  expect(drawn / full).toBeGreaterThanOrEqual(0.95 - 0.005);
  expect(scrolls).toBe(true);
});
