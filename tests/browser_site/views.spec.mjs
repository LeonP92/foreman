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
  await expect(page.locator("path.edge.import").first()).toBeHidden();
  await expect(page.locator("path.edge.forbidden")).toBeVisible();
});

test("map neighbourhood puts dependents left and dependencies right", async ({ page }) => {
  await page.goto("/layered.html");
  await group(page, "svc").click();
  await page.keyboard.press("n");
  await expect(page.locator(".ego-bar")).toBeVisible();
  await expect.poll(async () => (await left(group(page, "app"))) < (await left(group(page, "svc")))).toBe(true);
  await expect.poll(async () => (await left(group(page, "svc"))) < (await left(group(page, "core")))).toBe(true);
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
